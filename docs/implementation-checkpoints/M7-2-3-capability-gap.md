# M7.2.3 能力缺口报告（已撤回：原判断有误）

日期：2026-09-28（同日撤回）　里程碑：M7.2.3
结论：**本报告先前的"能力缺口"结论作废**，M7.2.3 已按真实目录规则实现并通过实测。

## 1. 原判断与错在哪

- 原判断：`GET /api/vehicle-imports/batches/{batch_id}` 不在 `app/business_assistant_capabilities.json` 的 `operations` 里，故按合同不得读取，记能力缺口。
- **错误**：把 JSON 目录当成了读取白名单。实测原网关 `app/business_assistant_gateway._operations()`：
  ```python
  if method=='GET':
      if route.body_field: continue
  elif op_id not in reviewed: continue     # 只有写操作要求已评审
  ```
  即 **写操作须在 reviewed catalog 内；GET 由活跃路由发现**，并仍受 `DOMAINS`/`CLOSED_DOMAINS`/`DENIED`/body 过滤与调用时授权——与 M7 共同合同第 4 条原文一致。
- 实测证据：在隔离镜像内执行 `_operations()`，`GET /api/vehicle-imports/batches/{batch_id}` 返回 `discovered: True`，同族 GET（catalog、orders/{case_id}/batches、orders/{case_id}/manifest）同样在列；本领域写操作仅 `POST .../actions/{action}`，它在 JSON 目录内。

## 2. 更正后的实现与证据

- `VehicleImportBatchAdapter.read_snapshot` 使用该 GET（单次，`path_args={'batch_id': …}`），`fact_snapshot` 按原 `status` 判 `reviewed`/`confirmed`，按 `row_count` + 完整 `rows[]` 逐行结果判 `all_rows_result_recorded`（缺行、重复行标识、未登记类别、缺结果字段一律 unknown），`read_receipt` 只对已评审写操作开放。
- 外部套件 `V/tests/runtime_domains/test_vehicle_import_batch.py`：**9 项通过**，run `20260928T131640Z-e250f94ef3`，源码指纹 `46229e32526130166d92e4ba72828d3053f0c33f8c3774206c9bc7adc7ef9bcd`；同指纹 M7.2.2、M7.2.1 回归通过。
- 同步修复的真实缺陷：批次对象不是 Case，父类 `snapshot_from_record` 会按 `case` 校验引用（实测 422）；现由本适配器直接投影统一快照 DTO，动作可用性一律 `unknown`（原批次只返回岗位筛选的动作名，不当作已验证可用）。

## 3. 教训（写入本项记录）

读取可用性的唯一判据是**原网关的运行时目录规则**，不是 JSON 目录文件；判断能力缺口前必须实测 `_operations()`，避免把"未在 JSON 里"误当成"未获准"。
