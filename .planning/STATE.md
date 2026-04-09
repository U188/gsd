# OpenClaw Coding Kit STATE

## 当前状态
- 仓库主线已经按“可复制、可迁移、自包含”收紧了一轮
- 当前版本化文档不再依赖作者机器上的绝对文件路径
- `pm.json` 示例现在可随仓库一起移动，默认用 `repo_root = "."`

## 本轮收口范围
- `README.md`
- `INSTALL.md`
- `examples/pm.json.example`
- `skills/pm/scripts/pm_config.py`
- `.planning/*.md`
- `tests/test_pm_config_relative_root.py`
- `tests/test_docs_portability.py`

## 本轮验收标准
1. 仓库文件链接不再指向作者本机路径
2. `pm.json` 里的相对 `repo_root` 能按配置文件位置解析
3. 仓库复制到新目录后，Quick Start 主线还能跑通

## 当前风险 / 未决项
- 完整 Feishu / progress bridge E2E 仍依赖真实环境，不属于 repo-local 复制性验收范围
- `acp` 路径是否能直接使用 `sessions_spawn`，仍取决于实际 OpenClaw 构建和工具暴露面

## 推荐下一步
- 继续把 ACP / bridge 的集成验收补成可重复脚本
- 保持 local-first smoke 作为每次发版前的必跑门禁
