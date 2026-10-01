# PATCH-M8-1-RECONCILIATION-TRANSACTION-01：核账同事务写入入口

2026-10-01，当前M8.1，精确生产范围仅 `app/reconciliation_api.py` 的原POST batches创建及batches动作两入口，在原get_user前复用已评审get_write_db同一个Session。清算origins/clearing、全部GET/原CSV及service口径不改，app/db.py已有合同不新增分支。

实际 `business-finance-followon-20261001-01` 五场景完整执行4通过1失败、退出1，23完整自动check；核账创建POST返回原SQLAlchemy通用409，HK095失败、HK097未开始，全部原件保留，镜像源91ce1df7/脚本a7d8b2e1。该轮唯一外置数据库诊断是OperationalError code517，但诊断没有请求路径关联，不把它写成已精确绑定该POST。源审阅确认create_batch先认证/查询整个原snapshot再追加新批，现deferred SQLite读事务有既已证明的写升级风险；原动作重算/封存也读取当前snapshot，使用同一写事务合同。

SQLite认证读取前开始已有BEGIN IMMEDIATE，保持原期间/原定义22及现金定义7/原scope、版本/摘要、本人/独立店长/原Task、原回执/单事务与未知结果拒绝。PostgreSQL沿原Session，无SQLite额外语句。不自动重试、重放、换request_id、提高分数或放宽原409。本次关联实例已退出后实施，AST/独立短审，再以全新同轮五前序路径实际复验创建与后继，不继承旧23为新结果。
