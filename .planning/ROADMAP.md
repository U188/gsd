# OpenClaw Coding Kit ROADMAP

## Phase 0 · 自包含基线
目标：先保证仓库复制到任意新目录后，local-first 主线仍能直接使用。

已完成：
- [x] README 内仓库文件链接改为相对路径
- [x] `pm_config.py` 支持从 `pm.json` 所在目录解析相对 `repo_root`
- [x] `examples/pm.json.example` 改为 `repo_root = "."`
- [x] 清理版本化 `.planning` 文档中的作者本机路径与单机执行痕迹
- [x] 补充便携性相关测试

## Phase 1 · 当前稳定基线
- `task.backend = local`
- `doc.backend = repo`
- `coder.backend = codex-cli`
- Quick Start 作为复制后首轮验收路径

## Phase 2 · 协作链稳固
- [ ] 把 `pm_dispatch.py` / `invoke_openclaw_tool.py` 的兼容逻辑继续收口
- [ ] 明确 `sessions_spawn` 在不同 OpenClaw 构建中的真实可用调用面
- [ ] 增补 `openclaw` backend 与 `codex-cli` backend 的固定验收

## Phase 3 · progress bridge / ACP 完整链
- [ ] 验证 `acp-progress-bridge` 在更多环境下的事件回传
- [ ] 形成 repo-local E2E smoke 命令
- [ ] 补齐 monitor / review / complete 全链路证据

## Phase 4 · 可选 Feishu 集成
- [ ] 校验 Feishu plugin 只保留单一路径，避免重复注册
- [ ] 验证 task/doc OAuth 与权限 bundle
- [ ] 补 integrated mode 文档与验收命令
