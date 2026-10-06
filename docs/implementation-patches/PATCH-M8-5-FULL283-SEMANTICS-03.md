# PATCH-M8-5-FULL283-SEMANTICS-03：全量 283 例语义缺口集中修复

状态：实施中；归属 M8.5，登记于 2026-10-07。当前仅 M8.5 为 `in_progress`，CP-37 为 `not_ready`，M8.6 仍为 `todo`。不修改 `total_plan.md`、冻结的 283/101 场景及其原判据。

## 已有证据和裁决

当前 HEAD `c37fa3d`、干净工作树上，隔离真实 Flash 全量运行 `20261006T190206Z-bac7e79d49` 自然结束，283/283 个原场景执行，101 项仅为同批重叠子集；467 张业务表逐例等值，84 张卡保持待员工确认，零业务确认。861 次新请求全部结算。停后累计 8840 次，已结算约 220.507535 元，旧 7 次未知按 66.322432 元全额占用，保守总占 286.829967 元；400 元／12000 次门禁已显式暂停，账本原件在 V。技术审计为 V `closeout-20261007/full190206-terminal/terminal-audit.md`；独立逐例语义审阅为 V `closeout-20261007/full190206-partition-{A,B,C}/`。B04 初审误认为客服无权，原接口复核表明客服可准备会员权益申请而由经理执行，已改判可接受并保留纠错原件。当前合计应以三份最终分区报告重新计算，普通失败不可因结构通过而记为验收。

三份分区报告及 B04 更正附录最终交叉计数：全量 253 可接受／30 普通语义失败／0 关键失败；同批重叠 101 项为 86／15／0。V `closeout-20261007/full190206-terminal/aggregate-correction.md` 仅追加最终计数，旧技术审计原文保留。本补丁修复已观察到的回答与原业务入口、权限、时间、问项及已发布指南不一致，不重设计原业务状态机、金额规则、岗位授权或确认边界。任何新安全关键错误、真实写入、门禁/隔离异常先停止并保留原件。

## 允许的精确改动

- 助手说明与工具暴露：`app/business_assistant_prompt.py`、`app/business_assistant_business_prompt.py`、`app/business_assistant_service.py`、`app/business_assistant_business_tools.py`、`app/business_assistant_guides.py`、`app/flow_api.py`。限于空查询/409范围、专用入口与旧 Flow 区分、实际岗位/403与静态目录预测区分、时间区、确认卡不可编辑字段说明、准确需求命中提示、只读与写入区分；旧发票原单读取继续可用，但生产不可新建的旧 `flow:invoice` 不再作为可准备表单暴露。
- 终答完整性：`app/assistant_runtime_provider.py`、`app/assistant_runtime_runner.py`。限于非流式响应完整结束标志和确切不完整终答检测；不能把未完成答复记 `succeeded`，不得重放已执行工具或业务写入。
- 已有权益规则管理入口：`web/benefits.js`、`web/group.js`。限于无会员上下文时经理/管理员可在本店直接查看和发布冻结规则；购买、发放、核销、退款仍使用原会员/原单权限接口。
- 工作流前端说明：`web/workflowcontent.js`。仅修复已发布 HK-095 已有月结只读查询和 `mode=guide` 只读/原页指引被共用“生成表单后待确认”文案覆盖的问题；只有员工明确进入写入分支才提示确认卡。`wf-period-close.assistant.steps` 与 `wf-coupons-and-benefits.assistant.steps` 同步按查询/规则配置分支调整，避免页面“复制给业务助手”把无会员规则配置写成先找客户原单。
- 已发布工作流源：`docs/workflow-source/business.json`、`docs/workflow-source/services.json`，限于本次报告列出的退款已执行状态、采购付款、月结查询、权益规则、维修接待岗位、审计可见范围及相关版本/时间说明；生成物只能用 `scripts/build_workflow_guides.py` 更新 `web/workflow-guides.json`、`web/workflow-handbook.html`、`docs/全量工作流手册.html`，不直接改生成物或历史定义。
- 对应最小离线回归放在外部 V 原已登记 `tests/` 下；必要时仅在 V 的 `run_validation.py`、M8.5 manifest/selector/来源指纹中登记受影响原 ID 的定向入口，不改冻结场景或放宽判据。检查点、`implementation_plan.md`、`docs/业务助手交接.md`、`docs/architect/tasks/m85-live-closeout.md`、`docs/architect/progress.md` 可记录真实状态和证据，不提前标 done。

## 实施及复验

先按原接口核对每处受影响合同，再改上列源码/源指南；做 Python/Node 语法、指南生成物 check、定向隔离自检与代码审查。冻结新源码及验证输入，重绑外部五指纹并运行 M0.1 strict。恢复付费门禁前核算账本及旧未知占用，定向复验失败 ID 与邻近正确 ID，逐例审回答/工具/对象和真实卡、确认及业务表。受影响例可接受后，从零再跑同一 283，单列重叠 101 且逐例语义复核，不能拼旧全量或代表。M8.5 原完成条件全满足后才进入 M8.6。

2026-10-07 候选代码审阅：上述生产源码、工作流源和三份生成物已按 30 个普通失败的真实合同完成定点修订。独立审查又发现并已修复三处确切遗漏：无客户权益规则页补齐同编码新版所需的规则经济字段；空模型终答进入一次仅答复重试或失败，不再记成功；预收抵用/退款取消提示覆盖未执行的草稿与已批准占额状态。8 个改动 Python 文件 AST、3 个前端脚本 `node --check`、工作流生成器 `--check` 和 `git diff --check` 已通过。V 的原完整收集实收 3424 节点且新 7 节点逐字登记，但运行时源码继续变化，且准备运行本身不构成同输入通过；新 strict、定向隔离测试和付费真实复验仍待执行。账本仍保持 halt，未因此调用模型或修改旧费用。
