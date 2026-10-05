# M8.3 首探针实测审阅 v1

2026-10-05；仅首探针通过，M8.3仍in_progress，CP-36不放行。主线基线bf08ec1，包含PG-INTEGRITY补丁的两处未提交源码；此前五轮失败原件保留，未拼接为本次结果。

统一入口：`V/.venv/Scripts/python.exe V/run_validation.py --repo C:/Users/tiefu/.codex/worktrees/5502/HuaKangOS --milestone M8.3`；V为`C:/Users/tiefu/.codex/HuaKangOS-agent-validation/runtime-v1`。配对strict为`20261005T011612Z-7a4e2b079c`（18通过），本次run为`20261005T011722Z-77b19bb18d`（实际1节点通过，exit0，84.844秒），无跳过、超时或强制清理，正常排空。报告phase_complete=true、milestone_complete=false。

## 实际证据

- 员工原HTTP创建事实、真实Worker和3次合成provider准备卡、上传1件私有附件；真实外部模型请求0。
- SQLite与专用PG16.15从h52j升级到唯一h53k，475张旧表、19个非空表、31行原值保持；旧计划engine1/version7、默认值及空Runtime表正确。
- SQLite使用原联合备份恢复；PG使用真实pg_dump/pg_restore恢复到另一新数据库，附件恢复到不同对象根。整库快照、序列、原完整性守卫和私有附件字节/hash均通过。
- PG12次身份核验全真；实际fast stop rc0/status3、原PID与pidfile消失。安装依赖前后相同：psycopg及psycopg-binary3.2.12、SQLAlchemy2.0.50、Alembic1.18.4。
- 两处生产修复只涉及只读元数据、具名参数及PG JSON原文本；root和独立agent静审，无迁移或业务规则更改。

## 五指纹与原件

strict与探针以下五值相同，运行前后均未变：

| 输入 | SHA256 |
|---|---|
| source | 86aee34dab4184d9d9bf59805b24033ca4b5b8d2f43d9e01f81bfdfa18faa220 |
| harness | 60c1302fa79175f73be1e0483893de2af447ad6f2da371331b5fee7ad6d76c6c |
| external input | 5f7318aaa4e12cffc2b4bb89710dd49307a87afae652a0fcb87e654a29f7f27b |
| dependency lock | 3910945cf6063ebe984b40cc22667657bd83476dcca1024ef4884b10f01dc930 |
| installed dependencies | e537a94af533e550a48e512063354bc101cc12ab2a9e696bbe0aa7ea207b618a |

原件位于`V/runs/<上述run>/`及其`command-results/m83-owned-database-first-probe/`。本次run.json SHA为`6eb02e5dcf3cccc03d77053774ea146dc79537dd9cc2c518cc39d4e187cecb75`；m83-first-probe.json为`3d4882807bc95694faabf0a43cf1c7acf42cd91d91c63e2490566b5a885c349b`；m83-owned-postgres.json为`60146f3f98f73773615cf5a168da385afd5a749f6def4f58fcd51febb100d7d6`。原生dump2614131字节，SHA`5078eac97404f093a19a4c3a9e30cbdb12f906b734fdcc3ae056fbf34c7d36a0`。

root的16项原件核对全部通过：`V/closeout-20261003/m83-pg-integrity-candidate-20261005T010945Z-a63bdfd25f/first-probe-success-review.json`，SHA`5583b0df23be5ffa3cbfaba19c4861e3b9b9e1166fd98700cf5884f2fba9c7ff`。

## 保留范围

本次未覆盖旧计划实际Worker不自动启动、重复head迁移、唯一/CAS、真实双worker租约、事务outbox竞态、损坏引用/循环/JSON及缺失/损坏附件拒绝。新Runtime表为空，不能据此声明这些合同通过。继续在同一M8.3内完成原四条检查；真实模型、浏览器、独立运行环境和员工试用分别保留。
