# M7.2.3 能力缺口报告（供评审补齐；不扩大 reviewed catalog）

日期：2026-09-28　里程碑：M7.2.3（整车批量导入后的审阅与逐行恢复）
当前状态：**in_progress**（未记 implemented；未伪造通过）
源码指纹：`d68dfb7b4aa781865557efce3ece0357d7599ffe5ecca085380c9c567ab41443`

## 1. 缺口是什么

| 项 | 值 |
|---|---|
| 计划要求的原生证据 | `GET /api/vehicle-imports/batches/{batch_id}` |
| 是否在原路由中 | **是**（`app/vehicle_imports_api.py` 存在该路由） |
| 是否在 reviewed catalog 中 | **否**（`app/business_assistant_capabilities.json` 的 `operations` 在本领域只有 `POST /api/vehicle-imports/batches/{batch_id}/actions/{action}`） |
| 合同依据 | 共同合同第 4 条："M0 在隔离源码镜像中扫描实际 FastAPI 路由注册及 `app/business_assistant_capabilities.json`，按原 `_operations()` 规则登记可用目录……列表中未登记或运行时不存在的 operation 明确拒绝并报告能力缺口，不让模型猜 ID，**不扩大 reviewed catalog**" |

因此 `VehicleImportBatchAdapter.read_snapshot()` 按合同返回 503 并给出原页面入口，三条事实键一律 `satisfied=None`；套件断言"未发起任何读取"（`captured == []`）。

## 2. 缺口阻塞了本项哪些验收

| 无法完成的验收 | 原因 |
|---|---|
| "读取→准备→员工点击原确认→重读事实"闭环 | 没有已评审的批次详情读取，无法建立 `BusinessObjectSnapshot` |
| `vehicle_import.reviewed` / `vehicle_import.confirmed` | 状态必须来自原详情；不得用模型文字或前端路由 |
| `vehicle_import.all_rows_result_recorded` | 需要 `row_count` 与完整 `rows[]` 的逐行 `result`（funds_request_id / shipment_id / receipt_id），且任何分页或缺行必须判 unknown |
| 批量中断后"只补未完成 WorkItem" | 需要逐行结果才能确定哪些行已完成 |

已完成且不再依赖该缺口的验收：目录范围与注册显式性、缺口处理、引用类型收口、`extract_result` 返回 `vehicle_import_batch` 引用、回执保持冻结 `request_id`、五个原动作名与原 API 一致（外部套件 8 项，run `20260928T131239Z-b7c08e3893` passed）。

## 3. 两种可评审的解决方式（任一即可，需评审确认）

1. **把该 GET 纳入 reviewed catalog**：在 `app/business_assistant_capabilities.json` 增加 `GET /api/vehicle-imports/batches/{batch_id}`，并确认它沿用原岗位/门店过滤与分页语义；纳入后 M7.2.3 的 `read_snapshot` 与三条事实即可按现有合同实现（本适配器已按该路径预留 `UNREGISTERED_DETAIL_READ` 常量与缺口分支，补齐只需替换该分支并加实测）。
2. **提供等价的已评审只读路径**：例如在既有已登记面中暴露批次详情（含 `row_count`、逐行稳定 `row.id` 与 `result`），并明确分页规则；适配器据此实现，不改原 API 响应、不新增自动确认。

## 4. 主张与边界

- 不扩大 reviewed catalog、不调用未登记 GET、不让模型猜批次 ID。
- 文件上传仍是原封闭面，助手只返回原页面入口。
- 在缺口补齐前，M7.2.3 保持 `in_progress`；CP-18 保持 `in_progress`，不记 `implementation_released`。
- 依赖提醒：按计划的串行规则，M7.3.1（service_intake）依赖 M7.2.3；其原生证据（`GET /api/service-intake/appointments/{key}` 等）**已在目录内**，缺口补齐后即可继续，无需再等其它外部条件。
