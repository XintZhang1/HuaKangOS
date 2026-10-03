# PATCH-M8-1-WAREHOUSE-RETURN-LABEL-01

2026-10-03；当前业务浏览器收口及 HK152 自然跨日候选审阅发现的实际接线缺口。精确生产范围仅 `app/warehouse_period_analytics.py` 的固定 `REASONS` 展示映射。

原 `warehouse_service.PURPOSES` 使用 `wh_other_return` 和 `wh_consume_return` 保存其他入库原退、耗材领用原退。历史报表映射只列另两个旧名称，真实原退会落入“原业务库位变动”，无法展示其既有来源业务名称。追加真实两个既有 key 的中文 label，保留旧 key，不改数据库、原流水、金额/数量、来源引用、期间/图/CSV口径及定义。

手工源码核对两个 value 与原服务固定 purpose 一致；AST 与差异检查另记，原实际退回及 D+1 历史窗口动态证据待执行，不把静态修复记验收通过。
