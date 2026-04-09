# OpenClaw Coding Kit PROJECT

## 项目定位
- 仓库：当前克隆目录；运行时以 `pm.json` 的 `repo_root` 为准，推荐写成 `"."`
- 项目模式：brownfield
- 目标：把 `PM + coder + OpenClaw + ACPX + progress bridge` 收敛成一套可复制、可迁移、自包含的交付回路，先走 local-first，再按需接 Feishu

## 核心组成
### 1. PM 编排层
- 位置：`skills/pm/`
- 作用：任务入口、上下文刷新、文档同步、GSD 路由、执行派发
- 关键脚本：`skills/pm/scripts/pm.py`

### 2. coder 执行层
- 位置：`skills/coder/`
- 作用：提供标准 ACP / Codex 执行 worker 约束与观察脚本

### 3. OpenClaw / Feishu bridge
- 位置：`skills/openclaw-lark-bridge/`
- 作用：通过运行中的 OpenClaw Gateway 调工具，复用 Feishu 能力

### 4. progress relay 插件
- 位置：`plugins/acp-progress-bridge/`
- 作用：把子会话进度 / 完成事件回传给父会话

### 5. 示例与测试
- `examples/pm.json.example`：最小 PM 配置示例
- `examples/openclaw.json5.snippets.md`：OpenClaw 配置片段
- `tests/`：repo-local 验证与行为回归测试

## 可复制基线
- 版本库内的文档链接必须使用仓库相对路径
- 示例配置不能写死作者机器路径
- repo-local 验收必须能在复制到新目录后重跑成功
- 敏感信息、真实群组 id、真实 workspace 路径允许外置，但必须通过示例或文档说明接入方式

## 当前默认主线
- `task.backend = local`
- `doc.backend = repo`
- `coder.backend = codex-cli`
- 长任务 / brownfield / 多文件重任务按需切 `acp`

## 当前验收主线
1. `python3 -m py_compile skills/pm/scripts/*.py skills/coder/scripts/*.py`
2. `python3 skills/pm/scripts/pm.py init --project-name demo --task-backend local --doc-backend repo --write-config --skip-auto-run --skip-bootstrap-task --no-auth-bundle`
3. `python3 skills/pm/scripts/pm.py context --refresh`
4. `python3 skills/pm/scripts/pm.py route-gsd --repo-root .`

这四步通过，才算仓库在当前副本里可直接起用。
