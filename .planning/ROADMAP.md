# demo ROADMAP

## 当前阶段
### Phase 0 · local-first 验证与主线打通
目标：先把仓库、运行时、OpenClaw 接线、Codex 路径和默认执行模型收敛到可实际使用的状态，不引入 Feishu 变量。

已完成：
- [x] 拉取仓库到 `/root/openclaw-coding-kit`
- [x] 安装 `gsd-tools`
- [x] 安装 `acpx`
- [x] 配置并验证 `codex`
- [x] 跑通 `pm init`
- [x] 跑通 `pm context --refresh`
- [x] 跑通 `pm route-gsd`
- [x] 定位 `sessions_spawn` 桥接失配根因
- [x] 为 `backend=acp` 增加自动回退到 `openclaw` backend 的修复
- [x] 将默认执行模型收敛为 `coder.backend = "codex-cli"`
- [x] 增加长任务自动切换到 `acp` 的策略
- [x] 补充回退、自动路由、唯一 label 等测试与修复
- [x] 更新 `README.md` / `INSTALL.md` 的主线说明
- [x] 清理仓库中的过程垃圾文件，使工作区回到干净状态

## Phase 1 · 当前稳定基线
当前推荐基线：
- `task.backend = local`
- `doc.backend = repo`
- `coder.backend = codex-cli`
- 长任务 / brownfield / 多文件重任务再切 `acp`
- 默认以 Telegram / local-first / 非 Feishu 为当前可用路径

已确认：
- `pm.json` 已与当前主线一致
- `pm context --refresh` 已重建上下文
- `/root/.openclaw/workspace` 当前不存在，无需再做 legacy 清理

## 仍可继续做的增强项
### Phase 2 · 协作链进一步稳固
- [ ] 收口 `pm_dispatch.py` / `invoke_openclaw_tool.py` 的兼容逻辑
- [ ] 明确 `sessions_spawn` 在当前 OpenClaw 构建中的真实可用调用面
- [ ] 验证 `openclaw` backend 与 `codex-cli` backend 的行为差异并补成固定验收
- [ ] 进一步降低 `.planning` / `.pm` 历史状态对判断的干扰

### Phase 3 · progress bridge 与 ACP 完整链
- [ ] 验证 `acp-progress-bridge` 在当前环境的事件回传
- [ ] 明确主会话、子会话、bridge 三者的数据契约
- [ ] 形成 repo-local E2E smoke 命令

### Phase 4 · 可选 Feishu 集成
- [ ] 校验 Feishu plugin 只保留单一路径，避免重复注册
- [ ] 验证 task/doc OAuth 与权限 bundle
- [ ] 补 integrated mode 文档与验收命令

## 当前已知限制
- OpenClaw `2026.3.24` 当前构建下，`/tools/invoke` 对 `sessions_spawn` 的暴露不稳定，不能把它当成理所当然的默认能力
- 旧的 `.planning` / `.pm` 状态文件可能保留历史阶段痕迹，阅读时要区分“当前生效配置”和“历史运行记录”
- 已存在的旧 Codex 会话不会自动吃到新装的 superpowers / `/root/.codex/AGENTS.md` 覆写；新开会话才会生效

## 当前可执行主线
1. 直接按 `codex-cli` 默认路径使用这套系统处理日常任务
2. 在长任务、重任务、brownfield 任务上按自动路由或显式指定切到 `acp`
3. 需要更高稳定性时，再继续做 bridge / progress / E2E 收尾
