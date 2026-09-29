# PATCH-M8-1-SERVICE-EXTERNAL-RESULT-01

2026-09-29；M8.1 保持 `in_progress`。本补丁在 CP-29—CP-34 里程碑复验过程中发现并修复。

## 已复现缺陷

`app/assistant_runtime_domains/service_order.py` 的 `service.external_approved` 在遍历原详情顶层
`results` 时要求每项自带 `case_id`：

```python
or not _positive_id(item.get('case_id')) or item['case_id'] != data['id']
```

但原模型 `app/service_orders_models.py` 的 `ServiceExternalResult` 只有
`id / submission_id / outcome / result / business_date / evidence_id / actor_id`，**没有
`case_id` 列**；`service_orders_service._serialize` 因此永远不带出该键。结论：该事实键在真实
数据上永远返回未知，`service.external_approved` 不可能为 True，依赖它的完成条件无法成立。

## 精确改动范围

仅 `app/assistant_runtime_domains/service_order.py` 的结果遍历分支：

1. 删除结果项上的 `case_id` 存在性与相等性要求。
2. 保留全部其余守卫：结果必须是字典、`id` 与 `submission_id` 必须是正整数、
   `submission_id` 必须指向本单已核对过的提交（`by_id`）、同一提交不得有第二条结果、
   结果编号不得重复、结论必须可识别。
3. 增加注释说明归属由 `by_id` 收口及其原接口依据。

## 保留的边界

- 提交（`ServiceSubmission`）仍然必须有 `case_id` 且等于本单 id、必须属于当前 `line_key` 集合；
  串单与串项目判定没有放宽。
- “最新提交才算批准”的语义不变：仍按每个 `line_key` 的最大提交编号取最新。
- 不改原业务动作、状态机、金额或任何写路径。

## 异常路径

- 结果指向本单之外的提交：返回未知（提交关联不完整），不猜成未批准。
- 同一提交出现两条结果：返回未知。
- 结果缺少可识别结论（含原约束不允许的取值）：返回未知。
- 顶层 `results` 为空列表：最新提交尚无批准结果 → 返回不成立（而不是未知）。
- 顶层缺少 `results` 键：返回未知。

## 测试精确范围

`tests/runtime_domains/test_service_order.py`（外部合同，原件保留为
`.bak-20260929-pre-fact-linkage`）覆盖最新提交、无关提交、缺结果键与空结果列表四种情形；
仓库内 `tests/assistant_offline/tests/test_service_facts.py` 另有真实 `/api/service-orders`
HTTP 用例覆盖补件、逐项目最新结果与部分批准。
