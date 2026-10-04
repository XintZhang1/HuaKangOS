# PATCH-M8-2-READ-OBSERVATION-01

2026-10-04，CI37178121548 已在 Linux 05:03:45 UTC、Windows 05:10:38 UTC 自然终局 failure，全部相关运行结束后才修改输入。M8.2 仍唯一 in_progress。

Linux 原读取故障恢复节点已越过之前的 WorkItem 写入失败，完成 checkpoint、自然回收及23次后续 provider 请求；原 `model_round_budget` 断言通过。当前失败在同节点238：读取观察器总数25，原断言24。此处之后的同 WorkItem、完整预算、首卡与全部业务快照断言未执行，不预称整体恢复通过。

原 observer 捕获 `runtime_read_tool` 的全部调用，包括准备卡内部的原目录 GET。固定执行路径为恢复原单 GET一次、第二张 crm:customers 卡准备时的目录 GET一次、23轮新的原单 GET。第一次已保存卡不应重做。原报告省略了25条完整参数，具体构成为源码支持的判断，必须在新一轮用精确断言验证。

允许仅修改 V 原 `tests/m82-closeout/runtime-boundaries/test_runtime_checkpoint_recovery.py` 的 `test_real_get_result_kill_restores_same_work_and_default_twenty_four_rounds` 观察断言：保留全部 reads 记录，严格等于一个本 Case GET、一个 `GET /api/flow/catalog`（path_args为空、query恰为assistant_kind=customers），再23个同 Case GET的完整有序参数列表。23次provider仍独立严格要求。任何多余/重复/错序/错对象/错目录查询均拒绝，不仅把24改25，不过滤掉其它调用。

原provider响应、checkpoint、恢复等待、24轮/600秒预算、同 WorkItem两attempt、首卡逐列不变、两卡待确认、完整manifest和业务零写断言全部保持；不改生产、helper、原节点、命令、授权或平台范围。day只改外部独立候选，mobile独立审阅；root合并并更新manifest/restoration对应单文件SHA及输入draft，重新冻结source-only胶囊，通过统一入口执行两平台strict/full。原失败与源文件留存，不继承为新指纹通过。
