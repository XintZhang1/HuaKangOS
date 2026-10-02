# HuaKangOS · 华慷集团

当前开发分支为 `main`；2026-10-02 已将 `feature/assistant-agent-runtime` 快进合入并推送主分支。核心 Runtime 实现及 M8.1/M8.2 收口记录见 [实施计划](implementation_plan.md)；历史源码候选和新实现不能混为生产验收。

2026-09-30 按业主要求重新组织测试：旧测试与旧套件 CI 移出工作区，新验证以 [浏览器实际点击](tests/browser_click/README.md) 为入口，使用当前源码、原登录和业务 API、仓库外合成数据库及离线模型响应。GitHub Actions 使用相同入口。运行截图、日志和密码不进入仓库。PostgreSQL、真实模型、员工试用等门槛仍按计划保留。

历史业务源码基线为 R4-B1-20260927，迁移头 `h52j_assistant_work_plans`。当前分支另已追加 `h53k_assistant_runtime`；迁移文件存在不代表已有数据库已升级。原多门店业务、岗位待办、库存/财务/会员记账、人工确认与本地 MCP 接入继续保留。

2026-09-27 按要求精简本地仓库：测试套件、测试入口、历史截图/报告及重复说明已移至仓库外可恢复归档。业务代码和现有数据保持原样。本次清理没有验证模型能力或生产可用性。

## 启动

Python 3.11–3.13。Windows 双击 `start-preview.cmd`，按提示打开本地页面；保留同路径原预览账号和数据。也可运行 `start.ps1`；Linux/macOS 运行 `bash start.sh`。配置参考 `.env.example`。

已有库升级前须一致性备份、在副本迁移并验证恢复；升级应包含对应版本的完整迁移链，不能只替换前端。不要对已有库执行演示初始化。

## 保留的维护入口

- [0927_bugfix 修复及 DeepSeek 复测交接](docs/0927_bugfix-Codex修复与复测.md)
- [业务助手交接](docs/业务助手交接.md)
- [R4 实现与验收边界](docs/R4-B1-实现与验收说明.md)
- [本地 MCP 接入](docs/R4-B1-MCP接入说明.md)
- [交付说明](docs/交付说明.md)
- [原始需求](docs/原始功能需求表.docx)与[工作流手册](docs/全量工作流手册.html)
- [检查点](CHECKPOINT_STATUS.json)与[开发约束](AGENTS.md)

手册源为 `docs/workflow-source/`；生成与检查分别运行 `python scripts/build_workflow_guides.py` 和 `python scripts/build_workflow_guides.py --check`。

源码打包运行 `python scripts/package_source.py`，读取当前工作树，排除环境、数据和凭据，输出到仓库外。生产仍需 HTTPS、安全 Cookie、明确 Host、ClamAV、备份恢复与公司验收。
