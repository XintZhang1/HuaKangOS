# PATCH-M8-1-CANCEL-WRITER-01

2026-10-03，M8.1 唯一进行项。外部 candidate14 原生取消卡片的一次 POST 返回 503；原服务记录 SQLite OperationalError code 5，首次 proposal flush 在原读事务中升级写事务失败。原卡仍 pending，原业务全库未变；不把脱敏 table=other 推断成具体 SQL 或 code 517。

允许范围仅 `app/business_assistant_api.py`：导入既有 `get_write_db`，单张 cancel 的数据库依赖改用该函数。现有 FastAPI 缓存的同一 `get_db` 先进入 SQLite BEGIN IMMEDIATE，再读取身份和卡片；该短取消分支无模型或网络 await。保留原身份、门店、digest、状态、版本、Wake 同事务及 PostgreSQL 行为，不添加重试，不扩到 confirm 或 batch。

外部精确候选已静态审阅并经独立审阅。`cancel-writer-candidate-20261003T100832Z-0ecfd0a263` 原五场全部通过，实际 CLI 0、service 0、forced=false；一次原生 cancel 200，原卡 cancelled、依赖仍 waiting，无替代卡，469 表 1842 行原业务指纹不变。生产候选 bbe95959、脚本 6a381599，20 合成模型、真实和外部请求均 0。该成绩属于独立候选，不继承为正式 80 场或 PostgreSQL 验收。

正式 `20261003T091007Z-d9d0e4c819` 已自然收尾，CLI 1；原后端 11/11、19/19，浏览器 80 执行 / 75 通过 / 5 失败，原失败证据保留。合入精确候选后重新冻结和执行受影响路径及正式完整合同。

已按原生产6fcabf8e及原60脚本23aae285完整指纹守卫合入精确API字节1e4ca698；原件和实际合入指纹保存在外部 `merge-cancel-worker-20261003T110528Z-c851bf0d/merge.json`。合入后生产bbe95959、脚本6a381599，AST与差异检查通过；正式完整复验仍待执行。
