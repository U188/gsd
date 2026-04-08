from __future__ import annotations

import base64
import json
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional, Sequence
try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python 3.8 fallback
    from backports.zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Shanghai")
FindConfigFn = Callable[[], Optional[Path]]

APP_SCOPE_PRESETS: dict[str, dict[str, Any]] = {
    "openclaw-lark-tenant-baseline": {
        "description": "OpenClaw Lark/Feishu 插件常用 tenant 应用权限基线",
        "scopes": [
            "contact:contact.base:readonly",
            "contact:user.basic_profile:readonly",
            "docx:document:readonly",
            "im:chat:read",
            "im:chat:update",
            "im:message.group_at_msg:readonly",
            "im:message.p2p_msg:readonly",
            "im:message.pins:read",
            "im:message.pins:write_only",
            "im:message.reactions:read",
            "im:message.reactions:write_only",
            "im:message:readonly",
            "im:message:recall",
            "im:message:send_as_bot",
            "im:message:send_multi_users",
            "im:message:send_sys_msg",
            "im:message:update",
            "im:resource",
            "application:application:self_manage",
            "cardkit:card:write",
            "cardkit:card:read",
        ],
        "notes": [
            "适合从零配置 OpenClaw Lark/Feishu 插件时作为 tenant 应用权限导入基线。",
        ],
    },
    "group-open-reply": {
        "description": "在已能 @ 机器人回复的前提下，增量补齐“群里不 @ 也回复”所需敏感权限",
        "scopes": [
            "im:message.group_msg:readonly",
        ],
        "notes": [
            "这是敏感权限，通常仍需要在飞书开放平台确认并申请开通。",
            "只改 OpenClaw requireMention=false 不够，飞书后台也必须给应用开这条权限。",
        ],
    },
}

DEFAULT_BOT_AUTH_COMMANDS: tuple[str, ...] = (
    "/auth",
    "/feishu auth",
)


def unix_ts() -> int:
    return int(datetime.now(TZ).timestamp())


def _ensure_state_dir(state_dir: Path) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(state_dir, 0o700)
    except OSError:
        pass


def _load_json_file(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _save_json_file(state_dir: Path, path: Path, payload: dict[str, Any]) -> None:
    _ensure_state_dir(state_dir)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _remove_file(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _resolve_user_path(raw_path: str) -> Path:
    text = str(raw_path or "").strip()
    if text.startswith("~/") or text == "~":
        return Path.home() / text[2:] if text != "~" else Path.home()
    return Path(text).expanduser()


def _json_pointer_get(payload: Any, pointer: str) -> Any:
    if pointer in {"", "/"}:
        return payload
    current = payload
    for token in str(pointer or "").split("/")[1:]:
        key = token.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _resolve_secret_ref(secret: Any, *, config_payload: dict[str, Any], openclaw_dir: Path) -> str:
    if isinstance(secret, str):
        return secret.strip()
    if not isinstance(secret, dict):
        return ""
    source = str(secret.get("source") or "").strip()
    provider = str(secret.get("provider") or "").strip()
    secret_id = str(secret.get("id") or "").strip()
    if source == "env":
        value = str(os.environ.get(secret_id) or "").strip()
        if value:
            return value
        env_path = openclaw_dir / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if not line.startswith(f"{secret_id}="):
                    continue
                _, _, raw_value = line.partition("=")
                return raw_value.strip()
        return ""
    if source == "file":
        providers = ((config_payload.get("secrets") or {}).get("providers") or {})
        provider_payload = providers.get(provider) if isinstance(providers, dict) else None
        if not isinstance(provider_payload, dict):
            return ""
        if str(provider_payload.get("source") or "").strip() != "file":
            return ""
        file_path = _resolve_user_path(str(provider_payload.get("path") or ""))
        if not file_path.exists():
            return ""
        try:
            file_payload = json.loads(file_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return ""
        if str(provider_payload.get("mode") or "").strip() == "singleValue":
            return str(file_payload or "").strip()
        return str(_json_pointer_get(file_payload, secret_id) or "").strip()
    if source == "exec":
        try:
            result = subprocess.run(
                [
                    "openclaw",
                    "config",
                    "resolve-secret",
                    "--source",
                    source,
                    "--provider",
                    provider,
                    "--id",
                    secret_id,
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            return ""
        return str(result.stdout or "").strip()
    return ""


def _load_openclaw_config_with_path(config_paths: Sequence[Path]) -> tuple[Path, dict[str, Any]]:
    explicit = os.environ.get("OPENCLAW_CONFIG", "").strip()
    candidates = [Path(explicit).expanduser()] if explicit else []
    explicit_home = os.environ.get("OPENCLAW_HOME", "").strip()
    if explicit_home:
        candidates.append(Path(explicit_home).expanduser() / "openclaw.json")
    candidates.extend(config_paths)
    for candidate in candidates:
        if not candidate.exists():
            continue
        payload = json.loads(candidate.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return candidate, payload
    raise SystemExit(
        "openclaw.json not found; set OPENCLAW_CONFIG or OPENCLAW_HOME, "
        "or keep a config in repo-local ./openclaw.json / ./.openclaw/openclaw.json "
        "or a user-global OpenClaw config directory"
    )


def get_channel_app_info(find_openclaw_config_path: FindConfigFn) -> dict[str, str]:
    path = find_openclaw_config_path()
    if not path:
        raise SystemExit("openclaw.json not found for auth-link generation")
    payload = json.loads(path.read_text(encoding="utf-8"))
    channels = payload.get("channels") or {}
    feishu_cfg = channels.get("feishu") if isinstance(channels, dict) and isinstance(channels.get("feishu"), dict) else channels
    app_id = str((feishu_cfg or {}).get("appId") or "").strip()
    brand = str((feishu_cfg or {}).get("domain") or "feishu").strip() or "feishu"
    if not app_id:
        raise SystemExit(f"appId missing in {path}")
    open_domain = "https://open.larksuite.com" if brand == "lark" else "https://open.feishu.cn"
    return {
        "config_path": str(path),
        "app_id": app_id,
        "brand": brand,
        "open_domain": open_domain,
    }


def build_auth_link(find_openclaw_config_path: FindConfigFn, *, scopes: list[str], token_type: str = "user") -> dict[str, Any]:
    info = get_channel_app_info(find_openclaw_config_path)
    scope_q = ",".join([s for s in scopes if s])
    auth_url = f"{info['open_domain']}/app/{info['app_id']}/auth?q={urllib.parse.quote(scope_q)}&op_from=pm&token_type={token_type}"
    permission_url = f"{info['open_domain']}/app/{info['app_id']}/permission"
    return {
        **info,
        "mode": "app-scope",
        "scopes": scopes,
        "token_type": token_type,
        "auth_url": auth_url,
        "permission_url": permission_url,
    }


def list_app_scope_presets() -> dict[str, dict[str, Any]]:
    return {
        name: {
            "description": str(item.get("description") or "").strip(),
            "scopes": [str(scope).strip() for scope in (item.get("scopes") or []) if str(scope).strip()],
            "notes": [str(note).strip() for note in (item.get("notes") or []) if str(note).strip()],
        }
        for name, item in APP_SCOPE_PRESETS.items()
    }


def build_permission_bundle(
    find_openclaw_config_path: FindConfigFn,
    *,
    preset_names: Sequence[str],
    scopes: Sequence[str],
    token_type: str = "tenant",
) -> dict[str, Any]:
    resolved_presets: list[dict[str, Any]] = []
    merged_scopes: list[str] = []
    notes: list[str] = []
    seen: set[str] = set()
    seen_notes: set[str] = set()

    for raw_name in preset_names:
        name = str(raw_name or "").strip()
        if not name:
            continue
        preset = APP_SCOPE_PRESETS.get(name)
        if not isinstance(preset, dict):
            available = ", ".join(sorted(APP_SCOPE_PRESETS.keys()))
            raise SystemExit(f"unknown permission preset: {name}. available: {available}")
        preset_scopes = [str(scope).strip() for scope in (preset.get("scopes") or []) if str(scope).strip()]
        for scope in preset_scopes:
            if scope in seen:
                continue
            seen.add(scope)
            merged_scopes.append(scope)
        resolved_presets.append(
            {
                "name": name,
                "description": str(preset.get("description") or "").strip(),
                "scopes": preset_scopes,
            }
        )
        for note in (preset.get("notes") or []):
            text = str(note or "").strip()
            if text and text not in seen_notes:
                seen_notes.add(text)
                notes.append(text)

    for raw_scope in scopes:
        scope = str(raw_scope or "").strip()
        if not scope or scope in seen:
            continue
        seen.add(scope)
        merged_scopes.append(scope)

    if not merged_scopes:
        raise SystemExit("provide --preset and/or --scope so permission-bundle has scopes to export")

    base = build_auth_link(find_openclaw_config_path, scopes=merged_scopes, token_type=token_type)
    return {
        **base,
        "mode": "permission-bundle",
        "token_type": token_type,
        "preset_names": [item["name"] for item in resolved_presets],
        "presets": resolved_presets,
        "scopes": merged_scopes,
        "import_payload": {
            "scopes": {
                token_type: merged_scopes,
            }
        },
        "notes": notes,
        "manual_steps": [
            "打开 permission_url 对应的飞书开放平台权限管理页面。",
            "使用 import_payload 里的 JSON 通过“批量导入/导出权限”导入。",
            "在飞书开放平台确认新增权限并提交开通/发布。",
        ],
    }


def request_user_oauth_link(find_openclaw_config_path: FindConfigFn, *, scopes: list[str]) -> dict[str, Any]:
    info = get_channel_app_info(find_openclaw_config_path)
    path = Path(info["config_path"])
    payload = json.loads(path.read_text(encoding="utf-8"))
    channels = payload.get("channels") or {}
    feishu_cfg = channels.get("feishu") if isinstance(channels, dict) and isinstance(channels.get("feishu"), dict) else channels
    app_secret = _resolve_secret_ref((feishu_cfg or {}).get("appSecret"), config_payload=payload, openclaw_dir=path.parent)
    if not app_secret:
        raise SystemExit(f"appSecret missing in {path}")
    brand = info["brand"]
    device_auth_url = "https://accounts.larksuite.com/oauth/v1/device_authorization" if brand == "lark" else "https://accounts.feishu.cn/oauth/v1/device_authorization"
    effective_scopes = list(scopes)
    if "offline_access" not in effective_scopes:
        effective_scopes.append("offline_access")
    basic_auth = base64.b64encode(f"{info['app_id']}:{app_secret}".encode("utf-8")).decode("ascii")
    body = urllib.parse.urlencode({"client_id": info["app_id"], "scope": " ".join(effective_scopes)}).encode("utf-8")
    req = urllib.request.Request(
        device_auth_url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {basic_auth}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")
        raise SystemExit(f"device authorization failed: HTTP {exc.code} {raw[:500]}") from exc
    data = json.loads(raw)
    verification_url = str(data.get("verification_uri_complete") or data.get("verification_uri") or "").strip()
    if not verification_url:
        raise SystemExit(f"device authorization returned no verification URL: {raw[:500]}")
    return {
        **info,
        "mode": "user-oauth",
        "scopes": effective_scopes,
        "device_authorization_url": device_auth_url,
        "verification_url": verification_url,
        "user_code": str(data.get("user_code") or ""),
        "expires_in": int(data.get("expires_in") or 0),
        "interval": int(data.get("interval") or 0),
    }


def build_auth_bundle(
    find_openclaw_config_path: FindConfigFn,
    *,
    include_group_open_reply: bool = True,
    user_oauth_scopes: Sequence[str] = (),
    bot_auth_commands: Sequence[str] = DEFAULT_BOT_AUTH_COMMANDS,
) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    bundle: dict[str, Any] = {
        "mode": "auth-bundle",
        "status": "ready",
    }

    permission_presets = ["openclaw-lark-tenant-baseline"]
    if include_group_open_reply:
        permission_presets.append("group-open-reply")
    try:
        bundle["permission_bundle"] = build_permission_bundle(
            find_openclaw_config_path,
            preset_names=permission_presets,
            scopes=[],
            token_type="tenant",
        )
    except SystemExit as exc:
        issues.append({"section": "permission_bundle", "message": str(exc)})
        bundle["permission_bundle"] = {
            "status": "unavailable",
            "preset_names": permission_presets,
            "message": str(exc),
        }

    oauth_scopes = [str(scope).strip() for scope in user_oauth_scopes if str(scope).strip()]
    if oauth_scopes:
        attachment_auth: dict[str, Any] = {
            "scopes": oauth_scopes,
            "status": "ready",
            "manual_steps": [
                "打开 oauth.verification_url 完成用户授权。",
                "如果飞书机器人对话里有 `/auth` 或 `/feishu auth` 提示，仍需在飞书里执行一次，补齐机器人后续以你的身份工作的权限。",
            ],
        }
        try:
            attachment_auth["auth"] = build_auth_link(find_openclaw_config_path, scopes=oauth_scopes, token_type="user")
        except SystemExit as exc:
            issues.append({"section": "user_oauth.auth", "message": str(exc)})
            attachment_auth["status"] = "incomplete"
            attachment_auth["auth"] = {"status": "unavailable", "message": str(exc)}
        try:
            attachment_auth["oauth"] = request_user_oauth_link(find_openclaw_config_path, scopes=oauth_scopes)
        except SystemExit as exc:
            issues.append({"section": "user_oauth.oauth", "message": str(exc)})
            attachment_auth["status"] = "incomplete"
            attachment_auth["oauth"] = {"status": "unavailable", "message": str(exc)}
        oauth_payload = attachment_auth.get("oauth")
        if isinstance(oauth_payload, dict):
            verification_url = str(oauth_payload.get("verification_url") or "").strip()
            if verification_url:
                attachment_auth["verification_url"] = verification_url
                bundle["user_oauth_verification_url"] = verification_url
        bundle["user_oauth"] = attachment_auth

    commands = [str(cmd).strip() for cmd in bot_auth_commands if str(cmd).strip()]
    if commands:
        bundle["bot_auth"] = {
            "status": "manual_required",
            "commands": commands,
            "notes": [
                "这是机器人侧的授权动作，不是应用敏感权限开通。",
                "建议在飞书私聊机器人或目标群里按帮助文案执行；优先尝试 `/auth`，如果插件文案明确要求 `/feishu auth`，以插件提示为准。",
            ],
        }

    manual_steps: list[str] = []
    if include_group_open_reply:
        manual_steps.extend(
            [
                "在飞书开放平台确认并发布 `im:message.group_msg` 等新增应用权限。",
                "如果刚发布应用权限，重启或重连 OpenClaw 的 Feishu 通道后再测群消息。",
            ]
        )
    if oauth_scopes:
        manual_steps.append("打开 user_oauth.oauth.verification_url 完成用户 OAuth。")
    if commands:
        manual_steps.append("在飞书里执行一次机器人提示的授权命令，例如 `/auth` 或 `/feishu auth`。")
    if manual_steps:
        bundle["manual_steps"] = manual_steps
    permission_payload = bundle.get("permission_bundle")
    if isinstance(permission_payload, dict):
        permission_url = str(permission_payload.get("permission_url") or "").strip()
        auth_url = str(permission_payload.get("auth_url") or "").strip()
        if permission_url:
            bundle["permission_url"] = permission_url
        if auth_url:
            bundle["app_scope_auth_url"] = auth_url

    if issues:
        bundle["status"] = "incomplete"
        bundle["issues"] = issues
    return bundle


def openclaw_config(config_paths: Sequence[Path]) -> dict[str, Any]:
    _, payload = _load_openclaw_config_with_path(config_paths)
    return payload


def feishu_credentials(config_paths: Sequence[Path]) -> dict[str, str]:
    config_path, cfg = _load_openclaw_config_with_path(config_paths)
    section = ((cfg.get("channels") or {}).get("feishu") or {})
    app_id = str(section.get("appId") or "").strip()
    app_secret = _resolve_secret_ref(section.get("appSecret"), config_payload=cfg, openclaw_dir=config_path.parent)
    domain = str(section.get("domain") or "feishu").strip() or "feishu"
    if not app_id or not app_secret:
        raise SystemExit("missing channels.feishu.appId/appSecret in openclaw.json")
    if domain == "lark":
        accounts_base = "https://accounts.larksuite.com"
        openapi_base = "https://open.larksuite.com"
    else:
        accounts_base = "https://accounts.feishu.cn"
        openapi_base = "https://open.feishu.cn"
    return {
        "app_id": app_id,
        "app_secret": app_secret,
        "accounts_base": accounts_base,
        "openapi_base": openapi_base,
    }


def request_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    form: dict[str, str] | None = None,
    body: bytes | None = None,
    timeout: int = 30,
) -> tuple[int, dict[str, Any], str]:
    if form is not None and body is not None:
        raise SystemExit("request_json does not allow both form and raw body")
    encoded = body
    request_headers = dict(headers or {})
    if form is not None:
        encoded = urllib.parse.urlencode(form).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
    request = urllib.request.Request(url, data=encoded, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            status = int(getattr(response, "status", 200))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        status = int(exc.code)
    except urllib.error.URLError as exc:
        raise SystemExit(f"request failed for {url}: {exc.reason}") from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = {}
    return status, payload if isinstance(payload, dict) else {}, raw


def _token_scope_set(payload: dict[str, Any]) -> set[str]:
    scope = str(payload.get("scope") or "").strip()
    return {item for item in scope.split() if item}


def _token_covers(payload: dict[str, Any], required_scopes: tuple[str, ...]) -> bool:
    scopes = _token_scope_set(payload)
    return all(scope in scopes for scope in required_scopes)


def _token_is_valid(payload: dict[str, Any]) -> bool:
    expires_at = int(payload.get("expires_at") or 0)
    return expires_at > (unix_ts() + 300)


def _refresh_is_valid(payload: dict[str, Any]) -> bool:
    refresh_expires_at = int(payload.get("refresh_expires_at") or 0)
    refresh_token = str(payload.get("refresh_token") or "").strip()
    return bool(refresh_token) and refresh_expires_at > (unix_ts() + 300)


def _fetch_user_identity(access_token: str, creds: dict[str, str]) -> dict[str, Any]:
    status, payload, raw = request_json(
        f"{creds['openapi_base']}/open-apis/authen/v1/user_info",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if status >= 400 or int(payload.get("code") or 0) != 0:
        raise SystemExit(f"failed to verify Feishu OAuth user identity: {raw}")
    data = payload.get("data")
    return data if isinstance(data, dict) else {}


def _build_saved_token(token_payload: dict[str, Any], creds: dict[str, str]) -> dict[str, Any]:
    access_token = str(token_payload.get("access_token") or "").strip()
    refresh_token = str(token_payload.get("refresh_token") or "").strip()
    if not access_token:
        raise SystemExit("missing access_token in OAuth response")
    identity = _fetch_user_identity(access_token, creds)
    granted_at = unix_ts()
    expires_in = int(token_payload.get("expires_in") or 0)
    refresh_expires_in = int(token_payload.get("refresh_token_expires_in") or 0)
    return {
        "app_id": creds["app_id"],
        "scope": str(token_payload.get("scope") or "").strip(),
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": granted_at + expires_in,
        "refresh_expires_at": granted_at + refresh_expires_in,
        "granted_at": granted_at,
        "open_id": str(identity.get("open_id") or "").strip(),
        "name": str(identity.get("name") or identity.get("en_name") or "").strip(),
    }


def _request_device_authorization(required_scopes: tuple[str, ...], creds: dict[str, str], *, state_dir: Path, pending_auth_path: Path) -> dict[str, Any]:
    auth_header = base64.b64encode(f"{creds['app_id']}:{creds['app_secret']}".encode("utf-8")).decode("utf-8")
    status, payload, raw = request_json(
        f"{creds['accounts_base']}/oauth/v1/device_authorization",
        method="POST",
        headers={"Authorization": f"Basic {auth_header}"},
        form={"client_id": creds["app_id"], "scope": " ".join(required_scopes)},
    )
    if status >= 400 or "device_code" not in payload:
        raise SystemExit(f"failed to request Feishu device authorization: {raw}")
    pending = {
        "app_id": creds["app_id"],
        "scopes": list(required_scopes),
        "device_code": str(payload.get("device_code") or "").strip(),
        "user_code": str(payload.get("user_code") or "").strip(),
        "verification_uri": str(payload.get("verification_uri") or "").strip(),
        "verification_uri_complete": str(payload.get("verification_uri_complete") or payload.get("verification_uri") or "").strip(),
        "interval": int(payload.get("interval") or 5),
        "created_at": unix_ts(),
        "expires_at": unix_ts() + int(payload.get("expires_in") or 180),
    }
    _save_json_file(state_dir, pending_auth_path, pending)
    return pending


def _refresh_access_token(saved_token: dict[str, Any], creds: dict[str, str], *, state_dir: Path, token_path: Path, pending_auth_path: Path) -> dict[str, Any] | None:
    if not _refresh_is_valid(saved_token):
        return None
    status, payload, _ = request_json(
        f"{creds['openapi_base']}/open-apis/authen/v2/oauth/token",
        method="POST",
        form={
            "grant_type": "refresh_token",
            "refresh_token": str(saved_token.get("refresh_token") or ""),
            "client_id": creds["app_id"],
            "client_secret": creds["app_secret"],
        },
    )
    if status >= 400 or "access_token" not in payload:
        return None
    refreshed = _build_saved_token(payload, creds)
    _save_json_file(state_dir, token_path, refreshed)
    _remove_file(pending_auth_path)
    return refreshed


def _poll_pending_device_authorization(pending: dict[str, Any], creds: dict[str, str], *, state_dir: Path, token_path: Path, pending_auth_path: Path) -> dict[str, Any] | None:
    if int(pending.get("expires_at") or 0) <= unix_ts():
        _remove_file(pending_auth_path)
        return None
    status, payload, _ = request_json(
        f"{creds['openapi_base']}/open-apis/authen/v2/oauth/token",
        method="POST",
        form={
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "device_code": str(pending.get("device_code") or ""),
            "client_id": creds["app_id"],
            "client_secret": creds["app_secret"],
        },
    )
    if status >= 400 and "access_token" not in payload:
        error_code = str(payload.get("error") or "").strip()
        if error_code in {"authorization_pending", "slow_down"}:
            return {
                "status": "authorization_required",
                "verification_uri_complete": pending.get("verification_uri_complete") or "",
                "user_code": pending.get("user_code") or "",
                "expires_at": pending.get("expires_at") or 0,
                "scopes": pending.get("scopes") or [],
            }
        _remove_file(pending_auth_path)
        return None
    if "access_token" not in payload:
        return {
            "status": "authorization_required",
            "verification_uri_complete": pending.get("verification_uri_complete") or "",
            "user_code": pending.get("user_code") or "",
            "expires_at": pending.get("expires_at") or 0,
            "scopes": pending.get("scopes") or [],
        }
    saved = _build_saved_token(payload, creds)
    _save_json_file(state_dir, token_path, saved)
    _remove_file(pending_auth_path)
    return {"status": "authorized", "token": saved}


def ensure_attachment_token(
    *,
    state_dir: Path,
    token_path: Path,
    pending_auth_path: Path,
    required_scopes: tuple[str, ...],
    config_paths: Sequence[Path],
) -> dict[str, Any]:
    creds = feishu_credentials(config_paths)
    saved = _load_json_file(token_path)
    if isinstance(saved, dict) and str(saved.get("app_id") or "") == creds["app_id"]:
        if _token_covers(saved, required_scopes) and _token_is_valid(saved):
            return {"status": "authorized", "token": saved}
        refreshed = _refresh_access_token(saved, creds, state_dir=state_dir, token_path=token_path, pending_auth_path=pending_auth_path) if _token_covers(saved, required_scopes) else None
        if refreshed and _token_is_valid(refreshed):
            return {"status": "authorized", "token": refreshed}
    pending = _load_json_file(pending_auth_path)
    if isinstance(pending, dict) and str(pending.get("app_id") or "") == creds["app_id"]:
        pending_result = _poll_pending_device_authorization(pending, creds, state_dir=state_dir, token_path=token_path, pending_auth_path=pending_auth_path)
        if pending_result:
            return pending_result
    fresh_pending = _request_device_authorization(required_scopes, creds, state_dir=state_dir, pending_auth_path=pending_auth_path)
    return {
        "status": "authorization_required",
        "verification_uri_complete": fresh_pending.get("verification_uri_complete") or "",
        "user_code": fresh_pending.get("user_code") or "",
        "expires_at": fresh_pending.get("expires_at") or 0,
        "scopes": fresh_pending.get("scopes") or [],
    }
