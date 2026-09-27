# HuaKangOS · 华慷集团

当前源码候选为 R4-B1-20260927，数据库迁移头 `h52j_assistant_work_plans`。包含多门店业务、岗位待办、库存/财务/会员记账、员工确认式业务助手与本地 MCP 接入。

2026-09-27 按要求精简本地仓库：测试套件、测试入口、历史截图/报告及重复说明已移至仓库外可恢复归档。业务代码和现有数据保持原样。本次清理没有验证模型能力或生产可用性。

## 启动

Python 3.11–3.13。Windows 双击 `start-preview.cmd`，按提示打开本地页面；保留同路径原预览账号和数据。也可运行 `start.ps1`；Linux/macOS 运行 `bash start.sh`。配置参考 `.env.example`。

已有库升级前须一致性备份、在副本迁移并验证恢复；R4 新增 h52j 迁移，不能只替换前端。不要对已有库执行演示初始化。

## 保留的维护入口

- [业务助手交接](docs/业务助手交接.md)
- [R4 实现与验收边界](docs/R4-B1-实现与验收说明.md)
- [本地 MCP 接入](docs/R4-B1-MCP接入说明.md)
- [交付说明](docs/交付说明.md)
- [原始需求](docs/原始功能需求表.docx)与[工作流手册](docs/全量工作流手册.html)
- [检查点](CHECKPOINT_STATUS.json)与[开发约束](AGENTS.md)

手册源为 `docs/workflow-source/`；生成与检查分别运行 `python scripts/build_workflow_guides.py` 和 `python scripts/build_workflow_guides.py --check`。

源码打包运行 `python scripts/package_source.py`，读取当前工作树，排除环境、数据和凭据，输出到仓库外。生产仍需 HTTPS、安全 Cookie、明确 Host、ClamAV、备份恢复与公司验收。
