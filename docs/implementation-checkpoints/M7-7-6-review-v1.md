# M7.7.6 编码审阅与实测记录（会员价格规则适配器）

2026-09-28，集中测试阶段。M7.7 组第六项，CP-26 收官项。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 新适配器 | `app/assistant_runtime_domains/member_price.py`：`MemberPriceAdapter(FlowCaseAdapter)`，`object_types=('member_pricing_rule',)`；快照只读 `GET /api/member-pricing/rules/{key}`（**key 即原规则 id**，与对象类型一致）；`read_receipt` 由已评审 resolver 绑定 |
| 显式注册 | `app/assistant_runtime_domains/__init__.py`：`DomainAdapterSpec(name='member_price', object_types=(PRICE_OBJECT_TYPE,), operation_ids=(rules/{key}, candidates, POST rules, rules/{key}/actions/{action}), fact_keys=PRICE_FACTS, fallback_object_types=())` |
| 外部套件 | `V/tests/runtime_domains/test_member_price.py`（9 项） |
| 未改动 | 原 `member_pricing_api.py`/`_service.py`/`_models.py`、迁移、权限表、价格与范围公式、状态机；未新增 signal hook |

## 2. 确定映射表（从 reviewed catalog 与原 schema 核对）

| 用途 | operation_id | path_args | 原响应 / 回执族 |
|---|---|---|---|
| snapshot / 事实 | `GET /api/member-pricing/rules/{key}` | `{'key': <MemberPricingRule.id>}` | 原规则详情（`plain(rule)` + `case_version`/`state`/`number` + `scopes[]` + `decisions[]` + 开放任务） |
| 只读候选 | `GET /api/member-pricing/candidates` | — | 原候选读取（登记为只读来源，不作为结果 operation） |
| result | `POST /api/member-pricing/rules` | — | 原规则创建响应 |
| result / receipt | `POST /api/member-pricing/rules/{key}/actions/{action}` | `{'key','action'}` | 原动作响应（submit/approve/reject/cancel）；回执由已评审 resolver 绑定 |

事实键与满足条件：
- `member_price.approved`：本规则原 `MemberPricingDecision` 为批准；只有提交/驳回明确未满足；决定缺可识别动作类型时未知。
- `member_price.cancelled`：原 cancel 成功结果与当前原状态一致（`state='cancelled'`）。
- `member_price.authorization_recorded`：必须原 `MemberPricingAuthorization` 明确关联本规则冻结报价快照；**候选存在不证明已应用/已授权**，详情未提供关联时未知。

## 3. 实测结论

运行 `20260928T135434Z-03b787be6f`：`status=passed`，`phase_complete=true`（源码指纹 `f12ab9a34e3aa6036c5659f98069fa3b0b3b6a5a0725fa2bbab3a289c871a0fa`）。

- `tests/runtime_domains/test_member_price.py`：**9 项通过**。覆盖四条 operation 在 reviewed catalog、四个原 service 函数与四个原动作、四个原模型、不动态导入/不写库/不抢回退；**注册到达运行时注册表**（Spy 捕获 spec）；快照 key 即规则 id、ID 不一致 502、无门店身份 403、上游 503、动作可用性 `unknown`；引用类型四类非法输入 422；三条事实的满足/未满足/未知分支（含"提交/驳回不满足批准键""决定缺动作类型必须未知""候选不证明已授权"三条显式断言）；未登记事实不猜；`extract_result` 边界（候选读不绑定）；回执保持冻结 `request_id`、未绑定 `unsupported`、只读详情 422。
- 本轮**一次通过，无返工**。

## 4. 未完成/未验收（如实登记）

- CP-26（M7.7.4—M7.7.6）三项适配器均已落盘并实测；**M7.7.5 的套餐事实因 purchase↔member 维度不匹配待评审补齐**（已如实登记，未伪造）。
- 会员价格授权事实在详情未提供冻结快照关联时按合同未知。
- 其余 M7 小项（M7.8.1 起）与 M8.x 按编号串行。
