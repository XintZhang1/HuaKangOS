# PATCH-M7-MISSING-DOMAIN-CONTRACTS-01

2026-10-04；依据业主本轮“除了员工试用其他都要完成”及既有持续实施授权，补齐原计划索引 M7.6.4、M7.6.5、M7.8.4、M7.8.5 对应的原业务助手合同。total_plan.md、业务目标、原业务 API/模型/迁移/状态机均不改。

发现：正文原本缺四条，CP-24/CP-28 历史已登记不一致；静态目录能检索不代表这些 provider 已实现。M8.2 暂记 blocked（真实未实现的前置合同），依原索引一次补一项；四项及最终原生命令回执接线完成后恢复当前候选完整验证。不因历史 Mock 或 unsupported 记 done。

## 首项 M7.6.4 的精确范围

- 新增 `app/assistant_runtime_domains/questionnaire_version.py`；仅原版本目录只读投影、原响应 ID 提取、四个已登记有限事实的纯核对。
- `app/assistant_runtime_domains/customer_care.py`：仅 questionnaire subtype 的冻结发放、真实答卷记录和完整回答事实；原关怀动作/通用事实保持。
- `app/assistant_runtime_domains/__init__.py`：root 唯一维护，显式注册 questionnaire_version 和三条关怀问卷事实；原操作归属不重复。
- 外部 `V/tests/m82-closeout/shared-contracts/test_http_privacy_workspace.py`：在保留原字节和既有节点的前提下追加一项实际原 API 问卷组合验证；不修改原业务确认和原答案断言求绿。后续登记实际新节点、来源 SHA、合成资格，再经原唯一入口执行。
- 外部既有 `V/tests/baseline/overlay/tests/runtime_domains/test_customer_care.py`：仅原 `test_registration_reaches_the_runtime_registry` 同节点登记断言随本项合并三问卷事实；原三条 care facts 保留，并核独立 care_case 类型的实际 fallback 且禁止 generic case。原 9 名称/顺序及其余测试保持；旧 `fallback==()` 与实际已登记独立 type 不符，不能为旧断言删除正确 type 分派。改前保存原字节/SHA/diff，归档原件不改。
- 本计划当前条目/CP、`docs/architect/` 当前交付记录及本补丁允许维护。其他三个缺正文项实施前各自追加精确文件、有限事实与异常路径。

原读路径只有 GET `/api/customer-service/questionnaires/versions` 和已登记 GET `/api/customer-service/cases/{case_id}`。版本主键来自真实 Version.id；number、policy_version 不冒充主键/对象版本。目录只显示最近 200 条且无完整分页证明，缺目标保持不可取得/unknown，不添加猜测 GET 或 SQL 旁读。

同一个新增问卷 HTTP 节点允许补一次原目录边界：经原员工 POST 构建足量合成版本使旧目标退出最近 200 列表，再用原 GET/registry 证明缺目标为 unknown/不可取得而非 nonexistent。保留原冻结 Case 发放与新旧发布证据，不添框架/测试节点、不 SQL 制造版本或降低旧断言；真实旧迁移答卷仍在 M8.3 非空迁移门槛执行。

原 POST 版本提案/独立复核仍由员工原确认；不自批、不复活早于当前版本的旧提案。版本事实仅证明原独立批准发布，superseded 不冒称当前生效。

问卷事实严格使用本 Case 原冻结 Binding 和 Response/CareRecord。runtime 与 migration 原来源分别核对；保留 legacy version_id=null/number=1，不能补造 Version.id。空白/部分 no_response 是合法已记录回应，不能当完整回答；完整回答须原 completed/resolved 且原冻结题目逐题严格通过。false/0 保留，不填缺答、不把 bool 当整数。未知或源缺失不当 false。

回执仍委托原统一 resolver；CareReceipt 最终接线另按固定原 DTO/digest 合同完成，当前静态实现不冒称可靠回执验证通过。附件/导出/银行/评审流程均不扩大。

来源：外部 `m7-missing-contract-readonly-audit-20261003T201223Z-48ed47215d/review.md` SHA25ed4b00a3a0f21d3b8b75637b216919348840ba734d3960b0b8603f3fe9c08f；原问卷 service/schema/API SHA3e535d3bae7abe48a9be29ead4082f7735f8a6c9b0cc38103526e89db8e86c59 /2166dc492663b32239d031bb865d55e9f6ff024dd88137ca2979a888a4083019 /eb500bead91e3e8584d9c603e3e8830b0adffb5a451aa4d2b895af911b760857。当前仅合同登记，测试/模型执行 0。

## 接续 M7.6.5 的精确合同登记（todo，前项静审后单独启动）

新增 `app/assistant_runtime_domains/observation_correction.py`；root 维护 `__init__.py` 的显式注册/导出；外部同一个 C 文件追加一项原 HTTP 创建/提交/独立批准/原观察不改写的组合节点。原 API/表/迁移/锁顺序/附件权限/保险或提醒业务规则不变。

`observation_correction` 的 ID 为原 Case.id；仅原 GET `/api/observation-corrections/cases/{case_id}` 与原 POST `/cases`、`/cases/{case_id}/actions/{action}` 绑定结果。catalog/vehicle/insurance sync/reminder generate 不当纠正 Case 结果，也不归本 provider 写操作。原详情为 flat 专用返回，没有 store_id/kind/flow_version/tasks；权限/类型由原专用 GET 实时守卫，不向原 API 补 mock 字段。快照用真实 Case.version，tasks=[]，原动作可用性 unknown。

有限事实固定 `correction.submitted`、`correction.approved`：只核本 Case 全原 CorrectionEvent 的 action/id/case_id/actor_id 与 submit/approve 的真实 evidence_id；approve 还须 completed 和独立于 create 的原 actor。关键源字段缺失/形状冲突保持 unknown，完整事件明确未发生才 false。只可描述原历史批准事务（原批准同事务产生 Effect），不得把当前 current.effect_id 归为此 Case；后续合法纠正/保险失效会改变当前头。replace/retract 的有效投影与不可改写的原观察分别保留，不制造实测里程、成本或凭据。GET 读取不业务提交。原 CorrectionReceipt 最终中央接线仍按原 DTO/date/default/digest 后项完成。

M7.6.5 实际原403拒绝边界补充：原 main.note_refusal 追加规则 Refusal，这是保留的原安全审计。新增 C 的 self-approve403 同节点应精确核服务器真实 `refusal.category=rule/can_escalate=false` 及唯一该次 actor/store/path/status/detail 原审计行；只允许此明确追加行，全部既有 Refusal 与其余业务/助手表逐字节保持。stale409 使用403之后快照，仍全图无写；不删除拒绝审计、不改通用 graph helper 或排除整张表求绿。

原共同三值合同补充核对：这些 Case 原 GET 公布 native version，缺失/非法版本须使相关有限事实 unknown；快照仍可 native_version=None，不猜填。M7.6.5 `_source_events` 实施该守卫；M7.6.4 新增问卷 Case 三事实也需该共同守卫，按原单项顺序补回静审后再继续下一项。原 immutable questionnaire_version 本身无 version 列，继续用真实 Version.id/摘要证据，不能填 number/policy_version 冒充。

## M7.8.4/5 接续合同登记（各自 todo，前项静审后依序实施）

M7.8.4：新增 `app/assistant_runtime_domains/clearing_order.py`，root `__init__.py` sealed 登记及原 C 文件追加一项真实原 HTTP 清算组合节点。对象 `clearing_order` 取真实 ClearingOrder.id，原 GET `/api/reconciliation/clearing/{key}`、POST `/clearing`、POST `/clearing/{key}/actions/{action}`；不冒用双方 Case 主键。专用原详情的 side/当前门店 party/本店 case_id/case_version 核对；必要本店 Case 读取复用已登记原 FLOW_READ，不重复操作归属，不读对方原 Case。

三有限事实 `clearing.local_cash_recorded`（当前本店对应 in/out 的真实 ClearingCash，严格原 order/cash/account/evidence/actor/date/整数分关系）、`clearing.settled`（原 settled、同本店 Case completed 及真实本店现金事实共同证明；paid 不作到账/结清）、`clearing.difference_recorded`（本店原同 Case clearing_difference 事件）。原 cash/events 列表受门店过滤，不将缺对方现金当未支付；缺关键来源保持 unknown。原跨店原单/资金/文件授权和双方实际确认/同事务偏移/版本/锁完全不改，原 ReconciliationReceipt 最终统一接线后项完成。

M7.8.5：新增 `app/assistant_runtime_domains/vehicle_income.py`，root sealed 登记及原 C 文件追加一项真实原 HTTP 收入组合节点。共享 `case` 的原 kind=vehicle_income/flow_version=1 显式 kind_versions 与 fact_kind_versions；原 GET `/api/vehicle-income/{key}`、POST `/api/vehicle-income`、POST `/{key}/actions/{action}` 绑定 Case.id，不将supplier/source/revision/payment编号冒用。原专用 GET 当前门店 READ 角色与 compact Task 关系严格保留，缺 status/role/version 为 None。

三有限事实 `vehicle_income.target_approved`（原 current_revision_id、同单原独立 Decision、8字段原摘要/整数分来源；pending 不取代旧批准）、`vehicle_income.receipt_recorded`（至少一条真实 VehicleIncomeCash in，不当全部应收结清）、`vehicle_income.refund_recorded`（同单原款/原账户与历史已批准修订关系，真实 out，累计不超原款）。合法历史现金不硬绑最新修订。原 GET 不披露 created_by/完整 CashEntry 时不猜填、不旁读；原业务守卫及恢复完整性单独证明。未知成本仍 null；原 supplier/source/日期/独立复核/原款退回/权限/实体合同均不改。最终 VehicleIncomeReceipt 固定原 DTO/date/default/digest 接线后项完成。只读合同来源 `m785-vehicle-income-readonly-contract-20261003T211618Z-1f4760f34c/readonly-contract.json` SHA415d3d5cd8b928b18288f1d9a5d9033c641a24c3a5465cf2c384d27bf6ff4d03。

两项不改原 API/模型/迁移/账务/报表口径，也不新增银行审批；完整外部输入 SHA/节点资格在四项及最终回执静审冻结后统一登记。当前只是未来合同登记，不并开实施状态。

## M7.8.4 原C账户维护岗位窄修

2026-10-04 M7.8.5静审结束后，唯一回开M7.8.4。原flow_api.MASTERS.accounts.write仅admin/manager，旧C中account()以finance POST期待201与原权限冲突。精确允许仅外部同C的该nested helper改为runtime.manager以当前finance选定真实门店请求原账户创建；两店主管现有显式会员资格保持，不自行扩大权限。其余旧16节点及新M785候选保持，现金仍finance本人；不改原API/DTO/权限或断言求绿。改前保留f54fd9完整字节、候选与精确差异，独立静审后恢复implemented；实际统一执行另登记。旧作者/独立报告漏核此岗位的窄结论追加更正、不删除历史。
