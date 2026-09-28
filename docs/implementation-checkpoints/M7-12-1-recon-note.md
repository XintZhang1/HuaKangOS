# M7.12.1 编码前置侦察记录（insurance_order，未完成实现）

2026-09-28，集中测试阶段。M7.12 组首项（也是索引中最后三项之一）。**本文件只记录侦察事实，不表示该项已实现。**

## 1. 原始面（已核对的 reviewed catalog）

| operation_id | 说明 |
|---|---|
| `GET /api/insurance-orders` | 原列表 |
| `GET /api/insurance-orders/catalog` | 原目录（动作/标签 LABELS） |
| `GET /api/insurance-orders/{case_id}` | **本项快照读取** |
| `POST /api/insurance-orders` | 原创建 |
| `POST /api/insurance-orders/{case_id}/actions/{action}` | 原动作（quote/review/authorize/submit/result/receive/disburse/direct_paid/termination/refund/commission_review） |
| `POST /api/observation-corrections/insurance/{case_id}/sync` | 原观察更正同步（本项未涉及，**不得**擅自使用） |

## 2. 注册合同（计划原文要点）

- `object_type=case`，**`InsuranceOrder.id` 与原 `Case.id` 相同** → 快照 key 用**原 Case.id**，
  路径参数为 `{case_id}`（与 M7.7.1/M7.8.x 的"原单 id 即 case id"约定一致）。
- 三条事实键与满足条件：
  - `insurance.current_quote_consented`：**当前**原报价有 `InsuranceConsent`，且引用**同 `quote_id`/`digest`**；
  - `insurance.external_result_recorded`：本单原 `InsuranceResult` 及原 `submission_id`/`outcome`；
    **任意外部结果不能满足已出保**；
  - `insurance.policy_issued`：原结果 **`outcome=issued` 且真实 `policy_number` 存在**；
- 边界原话：**保费/佣金保持各自原资金事实**（不得以报价或外部结果替代收款/佣金事实）。

## 3. 已核对的原实现线索

`app/insurance_service.py` 含 `is_detailed`、`can_read`、`get_order`、`_quote`、`_policy`、
`_previous_policy_id`、`_applied`、`_execute` 等函数。

**已逐字确认（本轮第二次读取）**：

- 路由：`@router.get('/{case_id}')` → `service.describe(db, user, service.get_order(db, user, case_id))`；
- **key 就是原 `Case.id`**：`get_order(db, user, key)` 内部为 `single_store(db)` → `_role(user, READ)` →
  `row = flow.get_case(db, user, key)` →（`is_detailed` 不成立则 `404 本店独立保险单不存在`）→
  `_one(db, InsuranceOrder, row.id)` → 返回**原 case 行**；写入侧同为
  `@router.post('/{case_id}/actions/{action}')` → `command(case_id, action, body)`；
- 附件证明：`_proof(..., financial=False)` 取 `authorization`（财务类取 `receipt`），
  `asset.generated` 或 `can_file` 不通过即 403「须上传…」——
  **附件存在不等于业务事实**，事实层不得以附件作为满足条件。

**仍需逐字确认**：`insurance_service.describe()` 投影中 `quote`/`consent`/`result`/`policy`
的**真实字段名**（`quote_id`/`digest`/`submission_id`/`outcome`/`policy_number` 是否与计划用词一致）。

## 4. 下一步（下一轮第一步，不虚构完成）

1. 逐字读 `app/insurance_api.py` 的 `{case_id}` 详情返回结构与 `insurance_service` 的详情构造，
   确认 `quote_id`/`digest`/`consent`/`submission_id`/`outcome`/`policy_number` 字段名；
2. 按本仓库既有范氏实现 `app/assistant_runtime_domains/insurance_order.py`：
   单次只读快照（用 **Case.id**）、ID 不一致 502、动作可用性 `unknown`、
   三条事实（**外部结果不满足已出保**；`policy_issued` 必须 `outcome=issued` **且**真实 `policy_number`；
   报价同意必须同 `quote_id`/`digest`，缺字段或摘要不一致一律**未知**）、
   写结果只绑定 insurance 族 operation、回执由已评审 resolver 绑定并保持冻结 `request_id`；
3. 注册（`fallback_object_types=()`）并补外部套件 `$ValidationRoot/tests/runtime_domains/test_insurance_order.py`，
   实测通过后登记 `implemented` 与评审记录。
