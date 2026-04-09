# 2026-04-09 Completeness Audit

## Verified Areas

- README、INSTALL、`.planning/PROJECT.md`、`.planning/ROADMAP.md`、`.planning/STATE.md` 的主线口径基本一致，仍以 local-first、自包含、相对链接为准。
- `run-reviewed`、`review`、`rerun`、`monitor-status`、`monitor-stop`、`complete` 这条 reviewed flow 在单任务场景下原本可用，continuation guard 仍覆盖 `acp`、`codex-cli`、`openclaw` 三类 backend。
- 配置与示例没有重新引入作者机器绝对路径；`examples/pm.json.example` 仍保持 repo-portable 形态。
- Quick Start 主线可在仓库内直接重跑：`init --write-config`、`context --refresh`、`route-gsd --repo-root .` 均成功。

## Fixes Made

### 1. Task-scoped reviewed flow lookup

Concrete gap:

- `review`、`rerun`、`monitor-status`、`complete` 在未显式传 `--run-id` 时，之前优先读取全局 `.pm/last-run.json`。
- 一旦仓库里连续跑多个任务，这些命令会把别的任务的最新 run 当成当前任务 run，导致 review gate、monitor stop、rerun source 解析错误。

Changes:

- 在 `skills/pm/scripts/pm_commands.py` 新增按 `task_id` / `task_guid` 从 `.pm/runs/*.json` 解析“该任务最近一轮 run”的逻辑。
- `monitor-status`、`review`、`rerun`、`complete` 现在都优先绑定到请求任务自己在 `.pm/runs/*.json` 里的最新 run，而不是盲目吃全局 `last-run.json`。
- 同任务有多轮 run 时，也优先以 `.pm/runs/*.json` 中较新的 task-scoped run 为准，避免旧的同任务 `last-run.json` 盖住较新的 rerun。

### 2. Repo-local fake bridge smoke path

Concrete gap:

- INSTALL 里给了 fake bridge smoke 命令，但仓库内没有现成脚本，操作员需要自己临时造一个。

Changes:

- 新增 repo-local smoke asset: `examples/fake-openclaw-lark-bridge.py`
- INSTALL 里的 fake bridge smoke 路径改成直接可用的 `./examples/fake-openclaw-lark-bridge.py`

### 3. Monitor kickoff mechanism

Concrete gap:

- reviewed run 之前虽然会创建 reporter cron，但第一次用户可见汇报要等到下一个 interval。
- 这会把“是否及时有第一条监察汇报”退化成调度粒度问题，而不是代码机制。

Changes:

- monitor 默认配置新增 `notify_on_start = true`
- reviewed run 在写完 `.pm/last-run.json` / `.pm/runs/<run_id>.json` 之后，会立刻 `cron.run --force` 一次刚创建的 monitor job
- monitor state 会把 kickoff 状态、触发时间、触发原因、bridge 返回结果写回 `.pm/monitors/<run_id>.json`，并同步回 run record
- fake bridge 也补了 `cron.run`，这样 repo-local smoke 和测试不再依赖人工脑补“第一轮汇报会不会发”

### 4. Docs/test alignment

Changes:

- README、INSTALL 补充说明：任务级命令会从 `.pm/runs/*.json` 解析该任务自己的最近 run。
- README、INSTALL、示例配置补充 `monitor.notify_on_start` 与 `cron.run` 依赖说明。
- README Quick Start 文案改为准确描述：真正写入 repo-local `pm.json` 的是 `init --write-config` 这一步。
- 新增/更新回归测试，覆盖：
  - `openclaw` backend monitored run
  - 多任务并行时 `monitor-status`、`review`、`rerun`、`complete` 的任务级 run 解析
  - `.pm/runs/*.json` 对 task-scoped lookup 的回归保护
  - 同任务多轮 rerun 时优先命中 `.pm/runs/*.json` 里的较新 run
  - reviewed run 创建 monitor 后会立即 force-run kickoff，而不是干等下一个 interval

## Validation Run

- `python3 -m py_compile skills/pm/scripts/*.py skills/coder/scripts/*.py skills/openclaw-lark-bridge/scripts/*.py`
- `python3 -m unittest discover -s tests`
- repo-local smoke:
  - `python3 skills/pm/scripts/pm.py init --project-name demo --task-backend local --doc-backend repo --write-config --skip-auto-run --skip-bootstrap-task --no-auth-bundle`
  - `python3 skills/pm/scripts/pm.py context --refresh`
  - `python3 skills/pm/scripts/pm.py route-gsd --repo-root .`

## Remaining Gaps

- Feishu、OAuth、真实 bridge 的 integrated E2E 仍依赖外部环境，本次只验证了 repo-local 可复用性与 reviewed flow 的本地正确性。
- 测试输出里仍有 `TemporaryDirectory` 的 `ResourceWarning`；不影响功能正确性，但属于可继续清理的测试卫生项。
