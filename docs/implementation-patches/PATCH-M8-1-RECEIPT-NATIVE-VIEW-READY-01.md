# PATCH-M8-1-RECEIPT-NATIVE-VIEW-READY-01

2026-10-03；当前 M8.1 定向装置修复。允许范围仅 `tests/browser_click/runtime_receipt_closeout.py` 的 `_prepare_flow` 原主管登录后的页面等待。

`closeout-contracts-04` notice 场在原主管登录成功后立即检查 assign selector 唯一性，原 Case 详情尚未渲染；失败截图随后显示本人本店、原“分派接待”任务和可用“转交”按钮。登录 helper 只等待门店框，不能当作原深链接详情已读完成。增加实际 Case 标题和实际 Task ID 原按钮 visible/enabled 等待，再进行原点击；不改登录、权限、分派对象、版本、业务 API 或等待超时预算，不增加提交重试。

原失败保留。AST/差异静态检查和后续新实例动态结果分别记录，等待适配不表示已通过。
