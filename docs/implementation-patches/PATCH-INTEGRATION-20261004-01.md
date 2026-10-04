# PATCH-INTEGRATION-20261004-01

2026-10-04，业主更新交付顺序：先整合 main、Cutie/DeepSeek 修复与 review、业务助手新增提交以及旧工作区由业主安排的界面改动，检查后合入 main 并删除其它分支；随后继续全部技术门槛，只保留员工试用和人工验收。允许 GitHub 环境可运行的 CI 测试。本记录取代此前暂停与“全部技术项完成后才合 main”的执行顺序，不改变原验收条件。

## 来源与保留

- main `7a4f872`，助手候选 `276181b`，运维 review `2e44fa9`（PR #16）。旧 bugfix、caret、Runtime、verified 分支头均已是 main 与助手候选祖先，不重复回放。
- `E:/HuaKangOS` 的未提交视觉设计属于正式范围。按其 `PATCH-M8-1-FRONTEND-VISUAL-01` 的原差异合入；不以旧整文件覆盖当前助手确认、回执、取消和 SQLite 修复。
- 合并前全部 refs 的可验证 Git bundle、两个脏工作区的 tracked binary diff 与状态清单已保存到仓库外 `V/closeout-20261003/branch-integration-20261004T012552Z-f6faf8e4cd`。未读入或提交凭据、原预览数据及证据包。原工作区保留。

## 精确改动范围

- 运维分支原生产文件、服务示例、隔离测试、文档按原提交合入；两个文档冲突保留双方历史，并由当前计划说明最新执行顺序。
- `app/ops_mcp.py` 只补两个实际拒绝缺口：JSON-RPC params 必须为对象；非 ASCII Authorization 返回正常认证失败。对应 `tests/ops_review/` 原隔离入口验证，不扩大工具或业务权限。
- 原 UI：`web/lightning.css`、`app.js`、`index.html`、`assistantworkspace.js`、`businessassistant.js`、`businessassistantfiles.js`、`businessux.js`、`moduleworkspaces.js`、`workflowcontent.js`、`workflowguides.js`。保留统计岗位过滤、全部人工业务深链接、稳定 ID、草稿及迟到响应守卫；保留新的运维反馈入口。
- `tests/browser_click/` 仅适配上述真实 UI：原交接任务的标题/转交/说明定位，历史控件固定隐藏节点，统计直接进入图表后的显式报表目录。原注册场景、五档窄屏、说明宽度、零业务写入及故障守卫保持。旧 mutex、CI 和总时限改动已被新候选取代，不回退。
- 工作流原源数据保持；E 的 coverage/线上生成物只有换行差异。便携手册的内联样式和文章控件由当前 `scripts/build_workflow_guides.py` 发布模式重新生成，保留全部当前修复及原截图来源，不复制旧整份手册。
- `.github/workflows/ops-review.yml` 补真实生产接线、依赖与服务文件路径，增加 main 推送检查；保留 Python/Node 官方运行环境及无外部模型/邮件的合成入口。现有独立全量回归调度保留；不恢复已删除的浏览器 CI 任务。
- `AGENTS.md`、`implementation_plan.md`、README 和 architect 任务记录维护最新授权、来源与实际结果；`total_plan.md` 不修改。

## 检查及边界

先完成独立差异审阅、语法检查、运维隔离测试及受影响的实际浏览器路径，再合入 main。后续 M8.2 完整回归与 PostgreSQL、真实模型、独立运行/恢复等原技术条件仍须实际执行，旧通过和中断结果不继承。M8.2 保持唯一 in_progress；本整合不是新业务里程碑。四个生产开关默认关闭，合并源码不表示生产上线。分支删除前核对祖先关系及脏工作区文件保留，不删除工作区或业务数据。
