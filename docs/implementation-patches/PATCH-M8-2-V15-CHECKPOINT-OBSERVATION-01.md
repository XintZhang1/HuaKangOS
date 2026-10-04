# PATCH-M8-2-V15-CHECKPOINT-OBSERVATION-01

2026-10-04，v15 CI37174392421 两平台均已自然终局 failure。Linux 的 matrix/A/B/C/D 通过，E 为 5 通过、2 call 失败。当前 M8.2 仍唯一 in_progress，未执行的命令不计通过。

第一处是原 E `test_three_original_preparation_entries_rollback_without_internal_commit` 的观测错误：准备前两张卡各经原 `emit_wake_event` 释放一次 SAVEPOINT，SQLAlchemy 2.0.50 的 `after_commit` 也通知嵌套事务。原 `[True, True]` 不能证明外层提交。允许仅在该测试函数将实例监听改为具名、绑定独立容器的外层/嵌套提交分类，并在 finally 移除；外层仍严格零次，保存嵌套观察。第三行原故障、两行已 flush、三入口读写边界和回滚后完整 Runtime/业务快照不变均保留。不改生产事务或禁止原唯一事件 SAVEPOINT。

第二处为 `test_real_get_result_kill_restores_same_work_and_default_twenty_four_rounds` 的子进程在断点前退出 3。现有 stderr SHA 仅对应固定 RuntimeError 类型输出；生产 run_once 可能捕获原异常返回，helper 自己再抛 RuntimeError，不能确定根因。实际调用签名已核无错位。原下载包未保存子进程诊断/数据库，不据猜测修生产。

允许仅在 V 原 `_runtime_read_worker.py` 与 `_runtime_support.py` 增加这条既有故障路径的有限诊断：固定阶段、结构化 RunExecution status/reason、请求/实际 GET 计数及状态、既有观察钩子异常的类型与静态代码位置。需要时只读取原 Run/RunItem 的固定状态码与计数。异常正文、参数、locals、模型内容、推理、凭据、真实身份均不保存；不能直接倾倒 stdout/stderr。子进程只输出有固定 schema 的诊断，父进程校验并写入当前命令证据目录，再保留原失败。

同范围允许在原 `_finish_run` 调用处只读观察 Python 当前正在处理的异常（`sys.exception()`），仅取同一白名单类型/静态位置后原样调用；用于定位 run_once 内已捕获而无法从外层取得的故障。不安装全局 trace，不改变异常传播、返回或运行状态，不读取异常正文/参数/局部变量。

不改变 provider 响应、35 秒等待、原真实 GET、原断点、同 WorkItem/预算恢复与业务零写断言，不更改生产、原节点/授权或新建测试入口。两位协作者分别只改各自外部候选；root 合并并登记原 manifest/restoration 对应 SHA 后，沿统一入口重新执行。诊断轮不预称恢复成功；原失败和旧源均保留。
