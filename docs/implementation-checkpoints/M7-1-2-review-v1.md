# M7.1.2 编码审阅与实测记录（版本报价与车辆交付适配器）

2026-09-28，集中测试阶段。M7 章节第二项。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 新适配器 | `app/assistant_runtime_domains/sales_order.py`：`SalesOrderAdapter(FlowCaseAdapter)`，`kind='order'`、`flow_version=3`；`read_snapshot` 只读 `GET /api/sales-quotes/orders/{key}`；`extract_result` 覆盖报价族 operation；`read_receipt` 走报价族回执（`sales_quote_service._execute` 的 operation/payload 摘要），三条登记事实独立判定 |
| 显式注册 | `app/assistant_runtime_domains/__init__.py`：`DomainAdapterSpec(name='sales_order', …)`，`operation_ids=(GET /api/sales-quotes/orders/{key}, GET /api/sales-quotes/orders/{key}/vehicles, POST /api/sales-quotes/orders, POST /api/sales-quotes/orders/{key}/quotes)`，`kind_versions=fact_kind_versions=(('case','order',3),)`、`fallback_object_types=()`（不抢通用 case 回退） |
| 外部套件 | `V/tests/runtime_domains/test_sales_order.py`（9 项） |
| 未改动 | 原 `sales_quote_api.py`/`sales_quote_service.py`/`sales_quote_specs.py`/`sales_quote_finance.py`/`flow_api.py`、迁移、权限表、金额公式与状态机；未新增 signal hook |

## 2. 确定映射表（从 reviewed catalog 与原 schema 核对）

| 用途 | operation_id | path_args | 原响应 / 回执族 |
|---|---|---|---|
| snapshot / 事实 | `GET /api/sales-quotes/orders/{key}` | `{'key': <Case.id>}` | 原报价详情（含 `quotes[]` 及每版 `review`/`resolution`、`active_quote_id`、`pending_quote_id`） |
| 事实（实配车辆） | `GET /api/sales-quotes/orders/{key}/vehicles` | `{'key': <Case.id>}` | 原配车清单（登记为本项可用的只读来源） |
| result | `POST /api/sales-quotes/orders` | — | 原报价单创建响应（顶层 Case） |
| result / receipt | `POST /api/sales-quotes/orders/{key}/quotes` | `{'key': <Case.id>}` | 新版报价响应；回执族 `flow_request_receipts` + `sales_quote_service._execute` 摘要 |

事实键与满足条件：
- `sales.active_quote_approved`：`active_quote_id` 指向的报价 `review.decision='approved'` 且 `resolution` 未撤回；无 active 版本即未知，未获批/已撤回明确未满足。
- `sales.active_quote_consented`：`sales_consent_id` 与 `signed_file` 同时存在才算；缺任一即未知（提示到原页面核对签署），不把"报价获批"当客户同意。
- `sales.delivery_recorded`：只有原交付事实键才算满足；`dispatch`、金额结清、状态文字都不能替代，缺证据即未知。

## 3. 实测结论

运行 `20260928T130043Z-76ef912e42`：`status=passed`（源码指纹 `e04c4efb5d90ceb5d22b98572e30bb053c91dbed1f2735aec6bed61e87bcfe40`）。

- `tests/runtime_domains/test_sales_order.py`：9 项通过。覆盖映射在 reviewed catalog 与活跃路由中可解析、动作键与原 `sales_quote_specs` 一致（quote_approve/quote_reject/quote_withdraw/release_vehicle/refund_excess）；注册静态显式且不动态导入、不写库、不抢回退；快照单次 GET、kind 收口（其它 kind 422）、ID 不一致 502；跨店 404（不暴露旧快照）、无门店身份 403、上游错误透传；三条事实的满足/未满足/未知分支；未登记事实不猜；`extract_result` 只对登记 operation；**回执读取保持冻结的 `request_id`**（夹具断言未重新生成），未绑定回执族返回 `unsupported`，非法提交快照 422。
- 同指纹回归：M7.1.1（lead 适配器）仍通过（`20260928T130111Z-7a2cf19e77`）。

## 4. 实测发现并修复的问题

1. **跨店读取被误判为 502**：首版把"门店不匹配"与"记录残缺"合并处理；已按原页面口径改为 404（不暴露旧快照），kind 不符 422，其余形状问题才 502。
2. **快照投影要求原待办携带真实 `case_id`**：夹具按原 `task_info` 形状补齐，避免把不完整记录当成可用快照。
3. **未绑定回执族的夹具写错**：首版总是注入回执读取器，导致 `unsupported` 分支无法验证；已改为仅在显式提供时才绑定。

## 5. 未完成/未验收（如实登记）

- 本项只完成 `sales_order` 一个适配器；M7.1.3 与其后 50 个小项仍为 `todo`，按编号串行。
- 真实原库/真实模型/浏览器验收属 M8.x；`sales.delivery_recorded` 在缺少原交付事实键时按合同返回未知，不猜成功。
- 报价族回执绑定仍由已评审的 flow receipt resolver 提供，本项未新增绑定路径，也未重新生成请求号。
