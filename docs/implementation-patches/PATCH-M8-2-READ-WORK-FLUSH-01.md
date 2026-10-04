# PATCH-M8-2-READ-WORK-FLUSH-01

2026-10-04，CI37176583479 在 Linux、Windows 均已自然终局 failure，相关进程结束后才修改源码。M8.2 仍唯一 in_progress。

Linux 的 E 原读取恢复节点在 checkpoint 前退出3。有限诊断实际记录 IntegrityError、runner 的 `_finish_write` flush 位置、3 succeeded / 2 pending / 1 running；唯一 GET 200 是首个准备内部的目录查询，不能解释为后续显式原单 GET 已成功。原 SQL 错误正文未保存，不声称已动态捕获具体约束名。

代码审阅确定 `_accept_read_work` 新建分支先 `db.add(work)`，再给已有 RunItem 设置 `work_item_id`。两个 mapper 只有标量外键而无 relationship；SQLAlchemy 2.0.50 同级 SaveUpdateAll 的 mapper 排序先 RunItem、后 WorkItem，因而不能靠 add 调用次序保证源行先写入。这与失败状态吻合，同文件 `_prepare_row` 已显式先 flush 源 WorkItem。

允许生产修改仅限 `app/assistant_runtime_runner.py::_accept_read_work` 新建分支：在 `db.add(work)` 后调用既有 `_flush(db)` 并说明必须先写入外键源记录；随后保留原关联和 `_finish_write`。不新增 commit，不改变持有锁的同一事务、最终身份/权限/fence 重验、失败整体 rollback 或已有 WorkItem 复用路径；不关闭外键、不增加重试，不改变模型或业务确认边界。

root 登记范围，day 实施单文件小改，mobile 独立复核，reg 独立审阅 Windows 实件。原 v16 的 provider、E 节点/断言、故障 helper、801 输入、74 数组、101 命令/授权、预算与断点全部保持；复用已核验 capsule asset609102816 / SHA519e60ee37dfa5df99063db69a43605cd2b0fe9383c56a99b6208f97ededbe79，对新源码通过统一入口重跑两平台 strict/full。原失败证据保留，静审不计恢复测试通过。
