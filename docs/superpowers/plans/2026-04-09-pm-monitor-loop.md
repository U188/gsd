# PM Worker Monitor Loop Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a machine-readable PM monitor loop that starts a recurring cron for async worker runs, keeps one active monitor per run, and automatically stops that cron when the task is completed or explicitly stopped.

**Architecture:** Keep v1 inside the existing PM Python surface. Add a focused `pm_monitor.py` module for config normalization, monitor state, cron payload generation, and stop/finalize helpers; then wire `pm_commands.py` so `run-reviewed`/`rerun` start or roll monitors and `complete`/`monitor-stop` close them. Persist all monitor state in `.pm/monitors/<run_id>.json` plus mirrored fields in `.pm/last-run.json` and `.pm/runs/<run_id>.json` so the loop is observable and testable without operator memory.

**Tech Stack:** Python 3, argparse, JSON state files, existing OpenClaw bridge invocation, `unittest`

---

## Scope Freeze

This plan covers one subsystem only: PM monitor lifecycle for async worker runs. It does **not** redesign ACP progress streaming, task backends, or review verdict logic.

## File Structure

- Create: `skills/pm/scripts/pm_monitor.py`
  - Single responsibility: normalize monitor config, decide applicability, build/read/write monitor state, build cron payload/prompt, and build close/finalize results.
- Modify: `skills/pm/scripts/pm_config.py`
  - Add `monitor` defaults plus `monitor_config()` accessor.
- Modify: `skills/pm/scripts/pm_commands.py`
  - Start monitor after eligible runs, roll monitor on rerun, expose `monitor-status` / `monitor-stop`, and close monitor during `pm complete`.
- Modify: `skills/pm/scripts/pm_cli.py`
  - Add CLI surfaces for `monitor-status` and `monitor-stop`.
- Modify: `skills/pm/scripts/pm.py`
  - Wire `pm_monitor.py` helpers into the API namespace and provide bridge-backed cron add/remove helpers.
- Modify: `tests/test_pm_local_cli.py`
  - Add end-to-end CLI tests with a fake bridge script that records cron add/remove calls.
- Create: `tests/test_pm_monitor.py`
  - Pure unit tests for monitor helpers and cron payload generation.
- Modify: `examples/pm.json.example`
  - Add the new `monitor` config block.
- Modify: `README.md`
  - Document the monitor loop, when it applies, and the operator flow.
- Modify: `INSTALL.md`
  - Document bridge/cron prerequisites and smoke-test commands.

No plugin work in v1. Do not change `plugins/acp-progress-bridge/` unless implementation proves the PM-only approach impossible.

### Monitor record shape to introduce

Persist this shape in `.pm/monitors/<run_id>.json` and mirror the same object under `monitor` in each run record:

```json
{
  "status": "active",
  "task_id": "T1",
  "task_guid": "guid-123",
  "run_id": "run-abc",
  "backend": "acp",
  "repo_root": "/repo",
  "child_session_key": "child-session",
  "cron_job_id": "job_123",
  "cron_schedule": {"kind": "every", "everyMs": 300000},
  "prompt_path": "/repo/.pm/monitors/run-abc.prompt.txt",
  "started_at": "2026-04-09T03:00:00Z",
  "last_checked_at": "",
  "last_notified_state": "",
  "stopped_at": "",
  "stop_reason": "",
  "stop_result": null
}
```

### Config block to add

```json
"monitor": {
  "enabled": true,
  "mode": "cron",
  "interval_minutes": 5,
  "stalled_after_minutes": 20,
  "notify_on_review_pending": true,
  "notify_on_review_failed": true,
  "auto_stop_on_complete": true
}
```

---

### Task 1: Add monitor config and pure helper tests

**Files:**
- Create: `skills/pm/scripts/pm_monitor.py`
- Create: `tests/test_pm_monitor.py`
- Modify: `skills/pm/scripts/pm_config.py`
- Modify: `examples/pm.json.example`

- [ ] **Step 1: Write the failing config/accessor tests**

```python
from pm_config import default_config, monitor_config


def test_default_config_contains_monitor_block():
    cfg = default_config()
    assert cfg["monitor"]["enabled"] is True
    assert cfg["monitor"]["interval_minutes"] == 5


def test_monitor_config_merges_defaults_with_active_config():
    pm_config.ACTIVE_CONFIG = {"monitor": {"enabled": False, "interval_minutes": 9}}
    merged = monitor_config()
    assert merged["enabled"] is False
    assert merged["interval_minutes"] == 9
    assert merged["auto_stop_on_complete"] is True
```

- [ ] **Step 2: Write the failing pure monitor-helper tests**

```python
from pm_monitor import should_start_monitor, build_monitor_state, build_monitor_prompt


def test_should_start_monitor_only_for_async_acp_runs():
    assert should_start_monitor(backend="acp", side_effects={"session_key": "child"}, monitor_cfg={"enabled": True}) is True
    assert should_start_monitor(backend="codex-cli", side_effects={}, monitor_cfg={"enabled": True}) is False


def test_build_monitor_state_captures_run_identity(tmp_path):
    state = build_monitor_state(
        repo_root=tmp_path,
        task_id="T1",
        task_guid="guid-1",
        run_id="run-1",
        backend="acp",
        side_effects={"session_key": "child-1"},
        monitor_cfg={"interval_minutes": 5},
        now_iso="2026-04-09T03:00:00Z",
    )
    assert state["run_id"] == "run-1"
    assert state["child_session_key"] == "child-1"
    assert state["status"] == "pending-cron"
```

- [ ] **Step 3: Run the focused test file and verify it fails**

Run: `python3 -m unittest tests.test_pm_monitor -v`
Expected: FAIL with `ImportError` / missing `monitor_config` / missing `pm_monitor`

- [ ] **Step 4: Implement the minimal config + helper surface**

```python
def monitor_config() -> dict[str, Any]:
    defaults = default_config()["monitor"]
    raw = ACTIVE_CONFIG.get("monitor")
    merged = dict(defaults)
    if isinstance(raw, dict):
        merged.update(raw)
    return merged


def should_start_monitor(*, backend: str, side_effects: dict[str, Any], monitor_cfg: dict[str, Any]) -> bool:
    return bool(monitor_cfg.get("enabled")) and str(backend).strip() == "acp" and bool(str(side_effects.get("session_key") or "").strip())
```

- [ ] **Step 5: Implement prompt generation with deterministic source-of-truth paths**

```python
def build_monitor_prompt(state: dict[str, Any]) -> str:
    return "\n".join([
        "You are the PM monitor tick for one PM run.",
        f"Repo root: {state['repo_root']}",
        f"Run record: {state['run_record_path']}",
        f"Monitor record: {state['monitor_path']}",
        f"Cron job id: {state['cron_job_id']}",
        "If the run is finalized/completed, remove the cron job and mark the monitor closed.",
        "If review is failed, emit one rerun reminder.",
        "If review is passed but task is not completed, emit one complete reminder.",
        "Otherwise stay silent unless the state changed.",
    ])
```

- [ ] **Step 6: Run the helper tests again**

Run: `python3 -m unittest tests.test_pm_monitor -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add skills/pm/scripts/pm_config.py skills/pm/scripts/pm_monitor.py tests/test_pm_monitor.py examples/pm.json.example
git commit -m "feat(pm): add monitor config and helpers"
```

---

### Task 2: Start monitor cron on eligible runs and roll it on rerun

**Files:**
- Modify: `skills/pm/scripts/pm_commands.py`
- Modify: `skills/pm/scripts/pm.py`
- Modify: `tests/test_pm_local_cli.py`

- [ ] **Step 1: Write the failing CLI integration test for run-reviewed monitor creation**

```python
def test_run_reviewed_creates_monitor_for_acp_runs(self) -> None:
    first_run = run_ok("run-reviewed", "--task-id", "T1", "--backend", "acp", "--agent", "codex")
    self.assertEqual(first_run["monitor"]["status"], "active")
    self.assertTrue(first_run["monitor"]["cron_job_id"])
    monitor_file = root / ".pm" / "monitors" / f"{first_run['run_id']}.json"
    self.assertTrue(monitor_file.exists())
```

Use a fake bridge script in the test temp repo and point `OPENCLAW_LARK_BRIDGE_SCRIPT` to it. The fake script should return deterministic JSON for `cron.add`.

- [ ] **Step 2: Write the failing rerun rollover test**

```python
def test_rerun_stops_previous_monitor_before_starting_new_one(self) -> None:
    failed = run_ok("review", "--task-id", "T1", "--verdict", "fail", "--feedback", "redo", "--reviewer", "qa")
    rerun = run_ok("rerun", "--task-id", "T1", "--backend", "acp", "--agent", "codex")
    self.assertEqual(rerun["monitor"]["status"], "active")
    self.assertEqual(rerun["monitor"]["replaces_run_id"], failed["run_id"])
```

- [ ] **Step 3: Run just the new CLI tests and verify they fail**

Run: `python3 -m unittest tests.test_pm_local_cli.PmLocalCliTest.test_run_reviewed_creates_monitor_for_acp_runs tests.test_pm_local_cli.PmLocalCliTest.test_rerun_stops_previous_monitor_before_starting_new_one -v`
Expected: FAIL because run payload has no `monitor` block yet

- [ ] **Step 4: Add bridge-backed cron helpers in `pm.py`**

```python
def cron_add(job: dict[str, Any], *, session_key: str = "main") -> dict[str, Any]:
    return invoke_bridge("cron", "add", {"job": job}, session_key=session_key)


def cron_remove(job_id: str, *, session_key: str = "main") -> dict[str, Any]:
    return invoke_bridge("cron", "remove", {"jobId": job_id}, session_key=session_key)
```

Expose these helpers through the API object passed into `build_command_handlers()`.

- [ ] **Step 5: Start the monitor inside `execute_run()` after `write_pm_run_record()` inputs are known**

```python
monitor = api.start_run_monitor(
    repo_root=str(api.project_root_path()),
    task_id=task_id,
    task_guid=str(task.get("guid") or ""),
    run_id=run_id,
    backend=backend,
    side_effects=side_effects,
    session_key=session_key,
)
payload["monitor"] = monitor
api.write_pm_run_record(payload, run_id=run_id)
```

Rules:
- only start when `backend == "acp"` and monitor config is enabled
- if the source run already has an active monitor and this is `rerun`, stop the old one first
- if monitor is not applicable, return `{"status": "not-applicable"}`

- [ ] **Step 6: Persist monitor files and mirror metadata into run records**

`pm_monitor.py` should provide a helper that writes:
- `.pm/monitors/<run_id>.json`
- optional `.pm/monitors/<run_id>.prompt.txt`

The returned `monitor` object should be embedded in both `last-run.json` and `runs/<run_id>.json`.

- [ ] **Step 7: Re-run the focused CLI tests**

Run: `python3 -m unittest tests.test_pm_local_cli.PmLocalCliTest.test_run_reviewed_creates_monitor_for_acp_runs tests.test_pm_local_cli.PmLocalCliTest.test_rerun_stops_previous_monitor_before_starting_new_one -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add skills/pm/scripts/pm.py skills/pm/scripts/pm_commands.py tests/test_pm_local_cli.py
git commit -m "feat(pm): start and roll worker monitors"
```

---

### Task 3: Close the monitor loop on complete and add operator stop/status commands

**Files:**
- Modify: `skills/pm/scripts/pm_cli.py`
- Modify: `skills/pm/scripts/pm_commands.py`
- Modify: `skills/pm/scripts/pm_monitor.py`
- Modify: `skills/pm/scripts/pm.py`
- Modify: `tests/test_pm_local_cli.py`

- [ ] **Step 1: Write the failing tests for auto-stop on complete and explicit stop**

```python
def test_complete_stops_active_monitor(self) -> None:
    completed = run_ok("complete", "--task-id", "T1", "--content", "done after pass")
    self.assertEqual(completed["monitor_stop"]["status"], "stopped")
    last_run = json.loads((root / ".pm" / "last-run.json").read_text(encoding="utf-8"))
    self.assertEqual(last_run["monitor"]["status"], "stopped")


def test_monitor_stop_command_is_idempotent(self) -> None:
    first = run_ok("monitor-stop", "--run-id", run_id, "--reason", "manual close")
    second = run_ok("monitor-stop", "--run-id", run_id, "--reason", "manual close")
    self.assertEqual(first["status"], "stopped")
    self.assertEqual(second["status"], "already-stopped")
```

- [ ] **Step 2: Run the focused failing tests**

Run: `python3 -m unittest tests.test_pm_local_cli.PmLocalCliTest.test_complete_stops_active_monitor tests.test_pm_local_cli.PmLocalCliTest.test_monitor_stop_command_is_idempotent -v`
Expected: FAIL because no command or stop hook exists yet

- [ ] **Step 3: Add CLI commands**

Add to `pm_cli.py`:

```python
monitor_status = sub.add_parser("monitor-status")
monitor_status.add_argument("--task-id", default="")
monitor_status.add_argument("--task-guid", default="")
monitor_status.add_argument("--run-id", default="")
monitor_status.set_defaults(func=handlers["monitor_status"])

monitor_stop = sub.add_parser("monitor-stop")
monitor_stop.add_argument("--task-id", default="")
monitor_stop.add_argument("--task-guid", default="")
monitor_stop.add_argument("--run-id", default="")
monitor_stop.add_argument("--reason", default="pm monitor-stop")
monitor_stop.set_defaults(func=handlers["monitor_stop"])
```

- [ ] **Step 4: Implement close/finalize helpers in `pm_monitor.py`**

```python
def stop_monitor(state: dict[str, Any], *, reason: str, now_iso: str, cron_remove_fn: Callable[[str], dict[str, Any]]) -> dict[str, Any]:
    if state.get("status") == "stopped":
        return {"status": "already-stopped", "monitor": state}
    remove_result = cron_remove_fn(state["cron_job_id"])
    state["status"] = "stopped"
    state["stopped_at"] = now_iso
    state["stop_reason"] = reason
    state["stop_result"] = remove_result
    return {"status": "stopped", "monitor": state, "remove_result": remove_result}
```

- [ ] **Step 5: Wire `pm complete` to auto-stop active monitors**

Right after `finalize_last_run_for_completion(...)`, close the active monitor when all of these are true:
- run record has `monitor.status == "active"`
- monitor config has `auto_stop_on_complete == True`
- the task completed successfully

Return the stop result as `monitor_stop` in the `complete` payload.

- [ ] **Step 6: Implement `cmd_monitor_status` and `cmd_monitor_stop`**

`cmd_monitor_status` should resolve by `--run-id` first, then fall back to the last run for the task.

`cmd_monitor_stop` should:
- load the current monitor state
- stop the cron if active
- persist the updated monitor JSON
- mirror the updated `monitor` block back into `last-run.json` and `runs/<run_id>.json`

- [ ] **Step 7: Re-run the focused tests**

Run: `python3 -m unittest tests.test_pm_local_cli.PmLocalCliTest.test_complete_stops_active_monitor tests.test_pm_local_cli.PmLocalCliTest.test_monitor_stop_command_is_idempotent -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add skills/pm/scripts/pm_cli.py skills/pm/scripts/pm_commands.py skills/pm/scripts/pm_monitor.py skills/pm/scripts/pm.py tests/test_pm_local_cli.py
git commit -m "feat(pm): close worker monitors on completion"
```

---

### Task 4: Document the operator loop and run the full regression suite

**Files:**
- Modify: `README.md`
- Modify: `INSTALL.md`
- Modify: `examples/pm.json.example`
- Modify: `tests/test_pm_monitor.py`
- Modify: `tests/test_pm_local_cli.py`

- [ ] **Step 1: Add one documentation test case to protect the public flow**

Extend `tests/test_pm_monitor.py` or `tests/test_pm_local_cli.py` with a round-trip assertion that the prompt text and docs example stay aligned on these commands:
- `run-reviewed`
- `review`
- `rerun`
- `monitor-status`
- `monitor-stop`
- `complete`

- [ ] **Step 2: Update README monitor section**

Add a concrete operator snippet:

```bash
python3 skills/pm/scripts/pm.py run-reviewed --task-id T1 --backend acp --agent codex
python3 skills/pm/scripts/pm.py monitor-status --task-id T1
python3 skills/pm/scripts/pm.py review --task-id T1 --verdict fail --feedback "Add evidence"
python3 skills/pm/scripts/pm.py rerun --task-id T1 --backend acp --agent codex
python3 skills/pm/scripts/pm.py review --task-id T1 --verdict pass --reviewer qa
python3 skills/pm/scripts/pm.py complete --task-id T1 --content "done"
```

Document the expected monitor lifecycle:
- async run starts monitor cron
- rerun replaces the previous monitor
- complete stops the monitor automatically

- [ ] **Step 3: Update INSTALL prerequisites**

Spell out that monitor mode needs bridge access to `cron.add` and `cron.remove`. Include a smoke-test command that uses the fake/local backend path when Feishu is not configured.

- [ ] **Step 4: Run the target PM regression suite**

Run:

```bash
python3 -m unittest tests.test_pm_monitor tests.test_pm_commands tests.test_pm_local_cli tests.test_pm_runtime tests.test_pm_lifecycle tests.test_pm_run_artifacts -v
```

Expected: PASS

- [ ] **Step 5: Run one manual CLI smoke in a temp repo**

Smoke path:

```bash
python3 skills/pm/scripts/pm.py create --summary "Monitor demo"
python3 skills/pm/scripts/pm.py run-reviewed --task-id T1 --backend acp --agent codex
python3 skills/pm/scripts/pm.py monitor-status --task-id T1
python3 skills/pm/scripts/pm.py review --task-id T1 --verdict pass --reviewer qa
python3 skills/pm/scripts/pm.py complete --task-id T1 --content "done"
```

Expected:
- monitor JSON exists after `run-reviewed`
- `monitor-status` shows active cron metadata
- `complete` returns `monitor_stop.status == "stopped"`
- `.pm/last-run.json` shows stopped/finalized monitor metadata

- [ ] **Step 6: Commit**

```bash
git add README.md INSTALL.md examples/pm.json.example tests/test_pm_monitor.py tests/test_pm_local_cli.py
git commit -m "docs(pm): document worker monitor loop"
```

---

## Final Acceptance Checklist

- [ ] `monitor` defaults exist in config and example config
- [ ] only async ACP runs create monitor state
- [ ] one active cron per run, with rollover on rerun
- [ ] `pm complete` auto-stops the active monitor and persists the stop result
- [ ] `pm monitor-status` and `pm monitor-stop` work on the latest run and explicit `--run-id`
- [ ] `.pm/monitors/<run_id>.json`, `.pm/last-run.json`, and `.pm/runs/<run_id>.json` agree on final monitor state
- [ ] README + INSTALL describe the exact closed-loop flow
- [ ] full regression suite passes
