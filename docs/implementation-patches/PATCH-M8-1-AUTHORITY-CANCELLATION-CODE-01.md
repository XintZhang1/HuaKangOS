# PATCH-M8-1-AUTHORITY-CANCELLATION-CODE-01

2026-10-03，属于当前唯一进行中的 M8.1。业主已要求除员工试用外完成全部技术验收。本补丁允许修改 `app/assistant_runtime_runner.py` 中 `_cancel_fragment` 及其三个调用点；不改变原业务权限、状态机或工作流。

`V/browser-click/closeout-contracts-07` 的真实管理员页面已将本轮新建合成员工 access_version 从 1 改为 2，原业务提交成功后模型迟到响应抵达。Run 实际取消且 Grant 随后因 permission_changed 撤销，但取消 helper 固定将原 `revalidate_principal` 的 401/403 记为 precondition_conflict，丢失真实权限拒绝分类。原失败报告保留。

helper 增加内部错误码参数，三个调用点仅依据重新核验身份抛出的真实 HTTP 状态，将 401/403 记录为 permission_denied；其他情况沿用 precondition_conflict。模型报错、自由文本和外部请求不能指定此分类。原 rollback、同一 principal 的 release、租约/fence/CAS、失租拒绝和不自动重放全部保留。

待独立代码审阅与新外置原生浏览器复验：真实撤权提交、迟到 prepare 零新增卡/WorkItem、原 Run 取消分类、Grant 停止及同 worker 后续 20 tick。静态检查不代表该业务验收通过。
