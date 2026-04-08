from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PM_SCRIPT_DIR = REPO_ROOT / "skills" / "pm" / "scripts"
if str(PM_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(PM_SCRIPT_DIR))

from pm_commands import build_command_handlers


class _FakeApi:
    def __init__(self) -> None:
        self.spawn_calls = 0
        self.openclaw_calls = 0
        self.codex_calls = 0
        self.persist_dispatch_calls = 0
        self.persist_run_calls = 0
        self.last_bundle = {"current_task": {"task_id": "T1"}}
        self.ACTIVE_CONFIG = {}

    def build_coder_context(self, task_id: str = "", task_guid: str = ""):
        return self.last_bundle, Path("/tmp/coder-context.json")

    def coder_config(self) -> dict:
        return {
            "backend": "acp",
            "agent_id": "codex",
            "timeout": 60,
            "thinking": "high",
            "session_key": "main",
        }

    def build_run_message(self, bundle: dict) -> str:
        return "run message"

    def resolve_effective_task(self, bundle: dict) -> dict:
        return {"task_id": "T1"}

    def build_run_label(self, root: Path, agent_id: str, task_id: str) -> str:
        return f"{agent_id}:{task_id}"

    def project_root_path(self, repo_root: str | None = None) -> Path:
        return Path("/tmp/repo")

    def spawn_acp_session(self, **kwargs):
        self.spawn_calls += 1
        raise SystemExit("Tool not available: sessions_spawn")

    def run_openclaw_agent(self, **kwargs):
        self.openclaw_calls += 1
        return {"status": "ok", "summary": "completed", "result": {"payloads": []}}

    def run_codex_cli(self, **kwargs):
        self.codex_calls += 1
        return {"backend": "codex-cli", "status": "ok", "summary": "completed", "result": {"payloads": []}}

    def persist_dispatch_side_effects(self, bundle: dict, result: dict, *, agent_id: str, runtime: str) -> dict:
        self.persist_dispatch_calls += 1
        return {"runtime": runtime, "kind": "dispatch"}

    def persist_run_side_effects(self, bundle: dict, result: dict) -> dict:
        self.persist_run_calls += 1
        return {"kind": "run"}

    def write_pm_bundle(self, name: str, payload: dict) -> None:
        self.last_written_name = name
        self.last_written_payload = payload


class PmCommandsFallbackTest(unittest.TestCase):
    def test_cmd_run_falls_back_from_acp_to_codex_cli_when_sessions_spawn_unavailable(self) -> None:
        api = _FakeApi()
        handlers = build_command_handlers(api)
        args = argparse.Namespace(
            task_id="T1",
            task_guid="",
            backend="acp",
            agent="main",
            timeout=120,
            thinking="high",
            session_key="main",
        )

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = handlers["run"](args)

        self.assertEqual(code, 0)
        payload = json.loads(buf.getvalue())
        self.assertEqual(payload["backend"], "codex-cli")
        self.assertEqual(api.spawn_calls, 1)
        self.assertEqual(api.codex_calls, 1)
        self.assertEqual(api.openclaw_calls, 0)
        self.assertEqual(api.persist_dispatch_calls, 0)
        self.assertEqual(api.persist_run_calls, 1)
        self.assertIn("fell back to backend=codex-cli", payload["warnings"][0])
        self.assertEqual(api.last_written_name, "last-run.json")
        self.assertEqual(api.last_written_payload["backend"], "codex-cli")


if __name__ == "__main__":
    unittest.main()
