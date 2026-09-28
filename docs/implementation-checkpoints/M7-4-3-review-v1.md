# M7.4.3 编码审阅与实测记录（零售集团与门店规则适配器）

2026-09-28，集中测试阶段。M7.4 组第三项，CP-21 收官项。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 新适配器 | `app/assistant_runtime_domains/retail_group_payment.py`：`RetailGroupPaymentAdapter(FlowCaseAdapter)`，`object_types=('case',)`；快照只读 `GET /api/retail-group/orders/{case_id}`；`extract_result` 覆盖集团支付族 operation；`read_receipt` 由已评审 resolver 绑定 |
| 显式注册 | `app/assistant_runtime_domains/__init__.py`：`DomainAdapterSpec(name='retail_group_payment', object_types=('case',), operation_ids=(GET /api/retail-group/orders/{case_id}, GET /api/retail-group/orders/{case_id}/catalog, POST /api/retail-group/orders/{case_id}/actions/{action}), fact_keys=GROUP_FACTS, fallback_object_types=())` |
| 外部套件 | `V/tests/runtime_domains/test_retail_group_payment.py`（7 项） |
| 未改动 | 原 `retail_group_api.py`/`_service.py`/`_models.py`/`retail_group_rules.py`、迁移、权限表、金额与额度公式、状态机；未新增 signal hook；未改 `store_id` |

## 2. 确定映射表（从 reviewed catalog 与原 schema 核对）

| 用途 | operation_id | path_args | 原响应 / 回执族 |
|---|---|---|---|
| snapshot / 事实 | `GET /api/retail-group/orders/{case_id}` | `{'case_id': <Case.id>}` | 原集团支付详情（`plan_id`/`plan_version`、`member_*`、`tenders[]` 含 `kind`/`credit_cents`/`units`/`wallet_id`/`status`/`reservation_version`、`notice`） |
| 只读目录 | `GET /api/retail-group/orders/{case_id}/catalog` | `{'case_id'}` | 原目录读取，登记为本项可用的只读来源 |
| result / receipt | `POST /api/retail-group/orders/{case_id}/actions/{action}` | `{'case_id','action'}` | 原动作响应；回执由已评审 resolver 绑定 |

六个原动作：`authorize` / `reserve` / `capture` / `release` / `restore` / `reassign`。

事实键与满足条件（**每条只证明实际一笔，不证明整单现金到账**）：
- `retail_group.reservation_recorded`：本单原 `RetailGroupReservation`（tender 带 `reservation_version`）。
- `retail_group.capture_recorded`：本单原 `RetailGroupCapture`（tender 状态 `captured`）。
- `retail_group.restore_recorded`：本单原 `RetailGroupRestore`（原恢复读法：tender 状态 `released`），理由保留"恢复保留原批次有效期、原发行退款须由原发行店另行办理"。
明细岗位不可见（`tenders` 为空）时一律未知，不猜。

## 3. 实测结论

运行 `20260928T133541Z-d2be66e157`：`status=passed`，`phase_complete=true`（源码指纹 `2b209aa9974d7cf309647e1f5f3573c3a5846f70f27ff0dc205bf340db442499`）。

- `tests/runtime_domains/test_retail_group_payment.py`：**7 项通过**。覆盖三条 operation 在 reviewed catalog、四个原 service 函数与六个原动作、四个原模型、不动态导入/不写库/不抢回退；**注册到达运行时注册表**（Spy 捕获 spec）；快照单次 GET、ID 不一致 502、**缺原集团方案 502（不补默认值）**、无门店身份 403、上游 503、动作可用性 `unknown`；三条事实的满足/未满足/未知分支（含"不证明现金到账""不证明整单现金到账""明细不可见必须未知"三条显式断言）；未登记事实不猜；`extract_result` 边界（只读目录不属于结果 operation）；回执保持冻结 `request_id`、未绑定 `unsupported`、只读详情 422。
- 同指纹回归：M7.4.2（retail_bundle）仍通过。本轮**一次通过，无返工**。

## 4. 未完成/未验收（如实登记）

- CP-21（M7.4.1—M7.4.3）三项适配器均已 implemented 并实测；`released` 仍不记，因为真实原库、真实模型、浏览器与员工试用属 M8.x。
- 资金类事实只到"单笔实际占用/核销/恢复"，整单现金到账仍以原财务事实为准。
- 其余 M7 小项（M7.5.1 起）与 M8.x 按编号串行。
