# PATCH-M8-1-VEHICLE-PROCUREMENT-WRITER-01

2026-10-01，finance05已自然结束且另两关联run的工具handle、Python进程与50705/50706监听均消失，报告未complete，分别按中断保留；无原目录重启。当前持续浏览器交付授权内先登记实际生产原因。

finance05唯一实际失败为原POST /api/vehicle-procurement/orders/85/actions/pay返回409。原Case85 receiving/v5、Funds1待付21000000分、vp_pay本人财务15成立；同原reference无Cash、Payment/Shipment/Receipt均0，尚未发运，无VIN或编号冲突。engine日志唯一OperationalError code517（SQLite BUSY_SNAPSHOT），原svc.execute将它与IntegrityError等统一回滚为通用409。command的get_db在身份/业务读取后才写，WAL并发写提交后无法提升旧读快照。原失败保存了路径/角色/Cookie/CSRF存在性与真实表单输入，未保存完整raw request_id，不冒称完整原封包证据或重放结果。

只修改 app/vehicle_procurement_api.py：导入已有get_write_db，原POST /orders/{case_id}/actions/{action}的db依赖改为get_write_db并保持先于get_user。沿用同一缓存Session，在SQLite身份/事实读取前短事务BEGIN IMMEDIATE；PostgreSQL沿原Session。原catalog/list/detail/export与create不改，schema/权限/本人Task/CAS/幂等/独立交易/金额精度/原业务同事务均不变；不增加retry、盲重放、绕过worker/改OS/改业务规则或把取消当成功。

三关联旧run原件和失败/中断分别留存，未知结果不当通过。AST/独立精确源审后新fresh财务17、应收11、报表6重办真实前序与原款，最后当前指纹全注册联合。启动采用隐藏独立进程、外置标准输出/错误及PID记录，以便后续goal段用操作系统进程与监听核对存活，不改变run.py或CI入口和门禁。真实日期/期间/193人工/独立环境及四默认关闭开关保持。
