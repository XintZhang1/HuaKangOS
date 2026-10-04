# PATCH-M8-2-SNAPSHOT-CONNECTION-01

2026-10-04，完整 CI `37170796831` 的 Windows 作业自然终局 failure 后，原 artifact `11291313035` 已按官方 SHA `81aab93cdc7316bcf663d5aa2a788d1fa41c07d7ebc767131ce008e67494a730` 留存。B 组 33 节点实际为 13 call passed、19 setup error、1 call failed；19 次 setup 在保留上一合成库时发生 WinError 32，另一个 call failure 是已登记的原单详情字段观察错误。不能使用 Linux 的 B32 成绩替代 Windows 结果。

共享 `m82_contract_helpers.py::database_snapshot` 使用 `with sqlite3.connect(...)`；该上下文只处理事务，不关闭连接。B 组首节点读取图快照后，下个节点即出现文件占用。SQLAlchemy 已归还连接并 dispose，测试的原生 SQLite 连接仍须由其创建者关闭，不能归入连接池管理。

精确范围仅为 V 的 `tests/m82-closeout/shared-contracts/m82_contract_helpers.py`：从 `contextlib` 导入 `closing`，将该只读 SELECT 快照连接包在 `closing(...)` 内。保留 SQL、完整行内容、排除项、比较方式、权限和业务断言；连接在返回与异常路径均明确关闭。不改 conftest 的已借出连接拒绝、源路径标记、原库留存、FK ON/defer OFF；不加 GC、重试或忽略文件占用。

保存原字节及精确差异，更新 manifest/restoration 中这一原补充输入的 SHA，与 PATCH-M8-2-CASE-DETAIL-CONTRACT-01 一起形成下一冻结输入。v13 仅字段修正的本地包保留但不运行、不上传、不冒认完整修复；下一包保留全部节点、74 数组及 101 命令，实际双平台完整结果待重跑。M8.2 继续唯一 in_progress。
