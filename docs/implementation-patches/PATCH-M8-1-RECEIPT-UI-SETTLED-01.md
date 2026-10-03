# PATCH-M8-1-RECEIPT-UI-SETTLED-01

2026-10-03；M8.1 验证器适配。允许范围仅 `tests/browser_click/runtime_receipt_closeout.py`：新增原回执按钮就绪 helper，在 `_lookup_ui` 与 mismatch 分支 `_recover_followup` 冻结核对证据之前等待同 session/proposal 的唯一可见原按钮和原 UI 非 busy 状态。

正式 run `20261003T064631Z-7769222357` 中，原确认 HTTP 返回并不表示 finally 中的事项/计划刷新和 paint 已结束；失败截图仍显示处理中，随后原页面已显示核对入口。原业务201、唯一原确认和不可变事实断言保留；不得通过重发确认、补造卡或增加超时预算修复时序。

外部候选 `V/closeout-20261003/m81-validator-candidate-20261003T075350Z-a5e38820d1` 的精确 session/proposal selector 已独立静态审阅。`closeout-validator-targets-12` 中冻结前 not_found、成功后结果保存故障、丢返回可靠回执三个完整场景已通过；整个候选仍运行，不继承为正式全量通过。正式80场原失败保留，生产源码不变，正式登记复验仍待执行。
