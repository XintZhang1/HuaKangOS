# PATCH-M8-1-LOGIN-TRANSACTION-01：SQLite登录认证写事务

日期：2026-10-01。来源：全新外部 `business-presales-20261001-05` 在HK-001/002及未选候选原生校验通过后，换销售员工的原Cookie登录返回503；服务日志只记OperationalError，不能记为已经捕获517。原失败、原已保存的接待/分派事实均保留，不重放业务，不以重跑成功覆盖此失败。

源码原因候选：原authenticate读登录失败计数、账号，再验证密码并删除旧attempt，后续同事务登录audit/Session提交；SQLite显式BEGIN在WAL下可被并发worker写入使读快照升写失败。authenticate当前对精确BUSY_SNAPSHOT仅重试一次，Fresh05仍失败。原退出补丁外部两连接探针已独立验证该事务机制及服务器Connection option的begin时机/回池不泄漏，不能把探针错误码当成本次503实测原文。

精确允许范围：`app/security.py`仅在SQLite authenticate读取前，使用已存在且只由服务器设置的 `huakangos_sqlite_write_transaction=True` 预留写事务；原认证流程执行一次，删除旧的一次snapshot重试及无用import。`implementation_plan.md`仅M8.1追加事实；相关任务和编码审阅报告。`app/db.py`已有钩子、POST/login、密码/throttle/session/Cookie/岗位合同及PostgreSQL均不改。

这只改变本来需要写attempt/audit/session的SQLite登录事务起点。密码验证在该事务内，持有单writer期间不得增加外部调用；原耗时密码验证仍执行一次，WAL读不被改成写。未知提交、超时、连接失败仍原样拒绝，Session只commit一次且commit成功后才设置Cookie，不捕获或循环重放。先原生实际完整售前链及受影响新注册浏览器检查，后恢复M8.1 implemented；原独立环境和生产门槛保持未验收。
