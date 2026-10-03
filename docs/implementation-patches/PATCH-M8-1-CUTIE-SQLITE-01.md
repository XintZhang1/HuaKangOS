# PATCH-M8-1-CUTIE-SQLITE-01

2026-10-03，当前唯一进行项 M8.1。业主授权全部助手计划收口至待人工验收，并修复 Cutie 的 GitHub issue #15 后统一上传 main。

## 原因与范围

原 `dispatch_one` 已完成独立读取并 rollback，但进入保存阶段后，通知/跟进 proof 会先读取来源，再更新 WakeEvent。SQLite deferred 事务在并发原业务提交后升级写锁会产生 BUSY/BUSY_SNAPSHOT；失败延期路径也可能重复读取后升级。现有 queue 已提供 `_sqlite_writer`，用于短写事务第一条 SQL 预留写锁，不改变数据库参数或重放原业务。

允许修改 `app/assistant_runtime_outbox.py`：分发保存、分发失败延期、定时核查保存及延期复用该原 helper；所有网络和来源解析先结束，锁仅覆盖原短写事务。PG、CAS、权限/版本验证、原事务原子性及退避保持原合同。不得给整个 worker/网络阶段持锁，不新增自动重试。

验证允许新增 `tests/browser_click/sqlite_outbox_closeout.py`，以及统一入口必要注册/白名单接线。真实原登录、客户新增/旧版本保护和并发读取来自原页面；数据库仅 SELECT 取证，事务观察仅记录分类/栈及非敏感指标。核 source、通知及唤醒唯一性、业务结果和有限负载下错误，不把有限零错误推为容量基准或PG结论。

## 异常路径

并发仍可能改变 proof/CAS 来源，原409/rollback及延期保留；等待SQLite原30秒锁预算后失败仍显式报告。失败重试不能复活已分发事件，不能改原业务成功、造通知或重复提交。原code517历史来源不全部归因于本补丁，仅报告受影响路径的新证据。

动态证据、精确指纹和人工代码审阅在本轮检查点追加；未运行前不声明通过。
