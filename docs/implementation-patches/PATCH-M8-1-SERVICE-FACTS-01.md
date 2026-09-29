# PATCH-M8-1-SERVICE-FACTS-01

2026-09-29；M8.1 保持 in_progress，基点 `47d9dc2`。

## 已发现差异

原 `service_orders_service.describe` 返回顶层 `submissions` 与顶层 `results`，以 `results[].submission_id` 关联；现适配器却在提交行内寻找嵌套 results，无法认出实际已批准结果。原命令按当前项目 `line_key` 取最新提交，不是整单最大 submission id；每个项目至多一个最新结论，至少一项批准不等于整单办结。

## 精确改动范围

- `app/assistant_runtime_domains/service_order.py`：仅修正 external_approved 的原证据投影；与实际顶层结果、当前项目、逐项目最新提交关联；完整空结果为尚未批准，缺失/截断/矛盾结果为未知，不能猜 ID、将历史结论移植到新提交或把单项目提升为整单。
- `tests/assistant_offline/tests/test_service_facts.py`：新增表驱动投影与原 HTTP/API/SQLite 真实业务流回归。创建独立主管，原上传/批准/授权/提交/补件/结果/办结接口，不改原规则；模型仅用合成响应验证公开计划条件。
- 如页面新增对应端到端用例，精确路径为 `tests/assistant_offline/tests/test_browser_ui.py`、`tests/assistant_offline/browser_server.py`；不增加生产测试端点。

先以未修正生产代码记录红灯，再修复并复验；保留旧失败证据。无真实模型、无生产数据、无部署、无四个默认功能开关变更。当前尚未登记测试成功。
