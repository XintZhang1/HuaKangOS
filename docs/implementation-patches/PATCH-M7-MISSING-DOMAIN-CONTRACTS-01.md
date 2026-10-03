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
