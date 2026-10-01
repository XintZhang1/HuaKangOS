# PATCH-M8-1-REPORT-TRANSACTION-01：有审计写入的原CSV导出事务

日期：2026-10-01。IAB外部report-diagnostic01两次明确原导出出现503/OperationalError、原export审计零新增；02一次成功并新增恰好一条。原失败保留，不能用一次成功消除已知间歇问题。三类CSV在同get_db鉴权及读报表后追加审计，SQLite WAL显式BEGIN读快照可能在并发worker提交后无法升级writer。无app导入、全新外部scratch库双连接最小探针复现read→write升级517；原IAB错误未记录扩展码，不冒称已确认517，05的隔离code5亦未绑定导出。

精确生产范围仅`app/db.py`新增显式`get_audited_read_db`依赖，及`app/flow_api.py`的analytics_export、`app/inventory_reports_api.py`的export、`app/visit_activity_api.py`的export采用此依赖。SQLite在该GET的任何鉴权/报表读取前沿已有server-only执行选项保留writer，确保原报表读取和单次审计提交同一稳定事务；FastAPI共享get_db缓存仍将同Session交给get_user。PostgreSQL沿原事务。普通GET、业务写、权限/期间/门店/原导出值、审计字段和CSV公式防护均不改。

不在鉴权后rollback丢上下文、不重试失败提交、不重复导出、不删除审计或放宽单条审计断言。SQLite导出期间会保留单writer，保留原30秒资源界限；长报表吞吐和PostgreSQL真实条件仍需原环境验收，本补丁不宣称已达到生产容量。三文件原导出先短审，原同源点击/全CSV/精确一条审计及其他业务不变核对，再完整注册复验；新IAB代表导出另留证。
