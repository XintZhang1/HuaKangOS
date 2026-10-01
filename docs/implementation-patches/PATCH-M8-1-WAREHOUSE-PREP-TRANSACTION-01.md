# PATCH-M8-1-WAREHOUSE-PREP-TRANSACTION-01：库位准备的SQLite事务起点

2026-10-01，当前M8.1实际原UI阻断修复，仅`app/db.py`、`app/warehouse_api.py`。business-repair01物资第二批库位准备原POST409，原sourceCheck/GET已完成，原状态为“库存或作业已被其他操作更新”；没有成功回执或部分过账。原API明确版本不符会给另一“原单已更新”文本，本通用409来源于仓储捕获的SQLAlchemy错误；同次隔离日志有517/5。日志无请求关联，不能单凭三条错误精确绑定该POST；此前两连接探针已验证WAL读快照升写失败机制。

实际prepare_external需认证/岗位/原单/物资读取后写入库位准备和审计，其deferred SQLite Session与已修导出相同，可能不能在其他worker事务提交后升为写方。复用既有服务器BEGIN IMMEDIATE起点，在该原POST认证和业务读取前获取写事务；原具体权限、CAS、幂等、数量/成本、准备不收发以及每项独立事务保持不变。将原get_audited_read_db实现命名为get_write_db，并保留原别名及三个原导出依赖；只接warehouse.allocate，不扩大其余仓储写入或任何只读路由。PostgreSQL保持原锁/事务合同。

没有自动重试、换请求号、吞异常或放宽409判据。旧失败完整保存；代码短审、AST后在全新外部同轮来源重新点击物资/维修，后续联合需含三个原导出。一次通过只表明该次原路径结果，不声明所有SQLite并发、PG/Linux或生产验收已完成。
