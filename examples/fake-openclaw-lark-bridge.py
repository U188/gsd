#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tool", required=True)
    parser.add_argument("--action", default="")
    parser.add_argument("--args", default="{}")
    parser.add_argument("--session-key", default="")
    parser.add_argument("--message-channel", default="")
    parser.add_argument("--account-id", default="")
    parser.add_argument("--message-to", default="")
    parser.add_argument("--thread-id", default="")
    ns = parser.parse_args()

    payload = json.loads(ns.args or "{}")
    state_path = Path.cwd() / ".pm" / "fake-bridge-log.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state = {"calls": [], "next_job_id": 1}
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))

    calls = state.setdefault("calls", [])
    calls.append(
        {
            "tool": ns.tool,
            "action": ns.action,
            "args": payload,
            "session_key": ns.session_key,
            "message_channel": ns.message_channel,
            "account_id": ns.account_id,
            "message_to": ns.message_to,
            "thread_id": ns.thread_id,
        }
    )

    if ns.tool == "sessions_spawn":
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"status": "ok", "result": {"details": {"childSessionKey": "child-1", "runId": "run-acp-1"}}}, ensure_ascii=False))
        return 0

    if ns.tool == "cron" and ns.action == "add":
        job_id = f"job-{state.get('next_job_id', 1)}"
        state["next_job_id"] = int(state.get("next_job_id", 1)) + 1
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"status": "ok", "job": {"jobId": job_id}}, ensure_ascii=False))
        return 0

    if ns.tool == "cron" and ns.action == "remove":
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"status": "ok", "removed": payload.get("jobId") or ""}, ensure_ascii=False))
        return 0

    if ns.tool == "cron" and ns.action == "run":
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"status": "ok", "jobId": payload.get("jobId") or "", "runMode": payload.get("runMode") or "force"}, ensure_ascii=False))
        return 0

    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "ok"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
