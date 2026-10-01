# PATCH-M8-1-DOCUMENT-WRITER-01

2026-10-01，M8.1。全部关联验证已收尾，精确仅 app/flow_api.py 的 generate 文档POST依赖及必要 get_write_db import。

member-boutique-reports06在原销售生成本版文档 POST /api/flow/cases/86/documents 返回503；外部合成server日志 OperationalError code=5。父销售失败导致后五依赖未办，不自动重放，不降为passed。该端点先 get_user/原单读取后在 deferred SQLite事务写文件和Event/Audit；已存在 get_write_db 提供写路由在auth/原单读取之前保留SQLite短写事务。

仅此已观察写端点使用 get_write_db，其他get_db读取、文档权限/版本/原字节快照/模板/文件扫描/同事务Event/Audit/提交和Receipt合同不改。SQLite在真正读取前 BEGIN IMMEDIATE，PostgreSQL保持既有行为；不重试生成、改busy超时、吞503、全表豁免或循环重放。原单据生成代码不改，模型/真实数据/生产四开关不启用。新隔离原销售到结果与受影响父链复验；静态不等真实并发/PG验收，原失败保留。
