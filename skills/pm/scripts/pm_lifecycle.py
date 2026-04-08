from __future__ import annotations

from typing import Any

VALID_ACP_CLEANUP_MODES = {"delete", "keep"}


def normalize_acp_cleanup_mode(value: Any, *, default: str = "delete") -> str:
    normalized = str(value or "").strip().lower()
    if normalized in VALID_ACP_CLEANUP_MODES:
        return normalized
    return default


def acp_cleanup_mode_from_coder(coder: dict[str, Any] | None) -> str:
    if not isinstance(coder, dict):
        return "delete"
    return normalize_acp_cleanup_mode(coder.get("acp_cleanup") or coder.get("cleanup") or "", default="delete")


def build_run_cleanup_plan(*, backend: str, session_key: str = "", acp_cleanup: str = "") -> dict[str, Any]:
    normalized_backend = str(backend or "").strip()
    normalized_cleanup = normalize_acp_cleanup_mode(acp_cleanup, default="delete")
    normalized_session_key = str(session_key or "").strip()
    owned_artifacts = {
        "task_lock": "released-at-run-exit",
        "run_record": "kept",
    }
    if normalized_backend != "acp":
        owned_artifacts["acp_session"] = "not-applicable"
        return {
            "status": "not-applicable",
            "backend": normalized_backend,
            "session_key": normalized_session_key,
            "acp_cleanup": "",
            "session_cleanup_state": "not-applicable",
            "owned_artifacts": owned_artifacts,
        }
    session_state = "auto-delete-on-run-exit" if normalized_cleanup == "delete" else "retained-by-policy"
    owned_artifacts["acp_session"] = session_state
    return {
        "status": "planned",
        "backend": normalized_backend,
        "session_key": normalized_session_key,
        "acp_cleanup": normalized_cleanup,
        "session_cleanup_state": session_state,
        "owned_artifacts": owned_artifacts,
    }


def finalize_last_run_for_completion(
    last_run: dict[str, Any] | None,
    *,
    task_id: str = "",
    task_guid: str = "",
    completed_at: str,
    finalized_at: str,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    if not isinstance(last_run, dict) or not last_run:
        return None, {
            "status": "no-last-run-record",
            "task_id": str(task_id or "").strip(),
            "task_guid": str(task_guid or "").strip(),
        }

    normalized_task_id = str(task_id or "").strip()
    normalized_task_guid = str(task_guid or "").strip()
    run_task_id = str(last_run.get("task_id") or "").strip()
    run_task_guid = str(last_run.get("task_guid") or "").strip()
    if normalized_task_guid and run_task_guid and normalized_task_guid != run_task_guid:
        return last_run, {
            "status": "task-mismatch",
            "task_id": normalized_task_id,
            "task_guid": normalized_task_guid,
            "run_task_id": run_task_id,
            "run_task_guid": run_task_guid,
        }
    if normalized_task_id and run_task_id and normalized_task_id != run_task_id:
        return last_run, {
            "status": "task-mismatch",
            "task_id": normalized_task_id,
            "task_guid": normalized_task_guid,
            "run_task_id": run_task_id,
            "run_task_guid": run_task_guid,
        }

    backend = str(last_run.get("backend") or "").strip()
    session_key = str(last_run.get("session_key") or "").strip()
    cleanup_plan = build_run_cleanup_plan(
        backend=backend,
        session_key=session_key,
        acp_cleanup=last_run.get("acp_cleanup") or "",
    )
    cleanup_result = dict(cleanup_plan)
    cleanup_result.update(
        {
            "status": "finalized",
            "completed_at": completed_at,
            "finalized_at": finalized_at,
        }
    )
    updated = dict(last_run)
    if normalized_task_id:
        updated["task_id"] = normalized_task_id
    elif run_task_id:
        updated["task_id"] = run_task_id
    if normalized_task_guid:
        updated["task_guid"] = normalized_task_guid
    elif run_task_guid:
        updated["task_guid"] = run_task_guid
    updated["completed_at"] = completed_at
    updated["finalized_at"] = finalized_at
    updated["finalized_by"] = "pm complete"
    updated["cleanup_result"] = cleanup_result
    return updated, cleanup_result
