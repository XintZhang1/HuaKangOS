# M7.7.3 编码审阅与实测记录（集团权益适配器；含一处接口不匹配）

2026-09-28，集中测试阶段。M7.7 组第三项，CP-25 收官项。

## 1. 结论摘要（先读）

本项发现并如实登记一处**接口不匹配**：登记对象类型是 `group_member`（原 `GroupMember.id`），
而已评审的权益读取 `GET /api/group/benefits/members` 的**必填参数是 `customer_id`**
（原签名 `def member(customer_id:int, ...)`，service 侧 `member_detail(db, user, customer_id)`）。
仅凭 `group_member` id 无法建立该读取路径；助手不得自行拼接/猜测客户 ID，也不得改用未评审的映射读取。
按共同合同"缺必要 ID 返回无法建立依赖证据，不让模型猜 ID"，适配器**明确报告该不匹配并零读取**，
三条权益事实一律未知；可判定的部分（写结果绑定、回执合同）照常实现并实测。

## 2. 交付物

| 类型 | 位置 |
|---|---|
| 新适配器 | `app/assistant_runtime_domains/group_benefit.py`：`GroupBenefitAdapter(FlowCaseAdapter)`，`object_types=('group_member',)`；`read_snapshot` 报告不匹配（503 + 原页面入口，零读取）；事实按合同未知；`extract_result` 绑定原动作响应中的会员；`read_receipt` 由已评审 resolver 绑定 |
| 显式注册 | `app/assistant_runtime_domains/__init__.py`：`DomainAdapterSpec(name='group_benefit', object_types=(BENEFIT_OBJECT_TYPE,), operation_ids=(GET /api/group/benefits/members, GET /api/group/benefits/rules, POST /api/group/benefits/members/{member_id}/actions/{action}), fact_keys=BENEFIT_FACTS, fallback_object_types=())` |
| 外部套件 | `V/tests/runtime_domains/test_group_benefit.py`（6 项） |
| 未改动 | 原 `group_benefits_api.py`/`_service.py`/`_models.py`、迁移、权限表、权益规则与状态机；未新增 signal hook；未扩大 reviewed catalog |

## 3. 实测结论

运行 `20260928T135007Z-fafb1eff0f`：`status=passed`，`phase_complete=true`（源码指纹 `a3064809caea4d1c998aadef28178bfc94dc17a3a556d676672248383d6d07a1`）。

- `tests/runtime_domains/test_group_benefit.py`：**6 项通过**。覆盖：原 API 确有 `customer_id` 必填参数与四种原 KINDS（bonus/points/coupon/package）、三条 operation 在 reviewed catalog；注册范围与不抢回退、不动态导入/不写库；**不匹配时返回 503 且零读取**（`captured == []`）、无门店身份 403；引用类型四类非法输入 422；三条事实在映射补齐前一律未知且理由含 `customer_id`；未登记事实不猜；`extract_result` 对动作响应绑定会员、对两个只读面不绑定、失败响应不绑定；回执保持冻结 `request_id`、未绑定 `unsupported`、只读面 422。
- 本轮**一次通过，无返工**。

## 4. 未完成/未验收（如实登记）

- CP-25（M7.7.1—M7.7.3）三项适配器均已落盘并实测；但 **M7.7.3 的权益快照与三条事实在映射补齐前无法验证**，需评审选择其一：①补一条"member→customer"的已评审只读映射；②把本项对象类型改为客户维度（与 `customer_id` 对齐）。在此之前本项不声称权益事实已可用。
- 其余 M7 小项（M7.7.4 起）与 M8.x 按编号串行。
