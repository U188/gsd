from __future__ import annotations

import unittest
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
PM_SCRIPT_DIR = REPO_ROOT / "skills" / "pm" / "scripts"
if str(PM_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(PM_SCRIPT_DIR))

from pm_lifecycle import acp_cleanup_mode_from_coder, build_run_cleanup_plan, finalize_last_run_for_completion


class PmLifecycleTest(unittest.TestCase):
    def test_acp_cleanup_defaults_to_delete(self) -> None:
        self.assertEqual(acp_cleanup_mode_from_coder({}), "delete")
        self.assertEqual(acp_cleanup_mode_from_coder({"acp_cleanup": "keep"}), "keep")

    def test_build_run_cleanup_plan_marks_acp_delete_as_auto_cleanup(self) -> None:
        plan = build_run_cleanup_plan(backend="acp", session_key="agent:codex:acp:demo", acp_cleanup="delete")
        self.assertEqual(plan["status"], "planned")
        self.assertEqual(plan["session_cleanup_state"], "auto-delete-on-run-exit")
        self.assertEqual(plan["owned_artifacts"]["run_record"], "kept")

    def test_finalize_last_run_for_completion_updates_run_record(self) -> None:
        record, cleanup = finalize_last_run_for_completion(
            {
                "task_id": "T1",
                "task_guid": "guid-1",
                "backend": "acp",
                "session_key": "agent:codex:acp:demo",
                "acp_cleanup": "delete",
                "run_id": "run-1",
            },
            task_id="T1",
            task_guid="guid-1",
            completed_at="2026-04-09T07:45:00+08:00",
            finalized_at="2026-04-09T07:45:01+08:00",
        )
        self.assertIsInstance(record, dict)
        self.assertEqual(cleanup["status"], "finalized")
        self.assertEqual(cleanup["session_cleanup_state"], "auto-delete-on-run-exit")
        assert record is not None
        self.assertEqual(record["finalized_by"], "pm complete")
        self.assertEqual(record["cleanup_result"]["owned_artifacts"]["acp_session"], "auto-delete-on-run-exit")


if __name__ == "__main__":
    unittest.main()
