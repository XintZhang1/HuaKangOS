# M8.3 数据库验收收口 v1

2026-10-05，原M8.3四条完成检查均有本轮完整实测支持，登记done。CP-36仍not_ready，待M8.4；本报告不表示真实模型、浏览器、独立部署环境、员工试用或生产验收通过。

统一入口：`V/.venv/Scripts/python.exe V/run_validation.py --repo C:/Users/tiefu/.codex/worktrees/5502/HuaKangOS --milestone M8.3`，V=`C:/Users/tiefu/.codex/HuaKangOS-agent-validation/runtime-v1`。strict `20261005T021219Z-f699b0cc5f`实际18通过；完整run `20261005T021313Z-4db44dd34a`的唯一登记节点`__main__.DatabaseContracts.test_upgrade_restore_and_original_database_contracts`实际通过，exit0、无skip/timeout、284.797秒、自然排空。下述37个拒绝场景、24个并发阶段是该节点内实际断言，不能冒算为额外pytest节点。

## 原完成检查与实际结果

| 原检查 | 本轮证据 |
|---|---|
| h52j→唯一新头可重复、旧行完整 | SQLite及真实PG16.15均由h52j升级到h53k；475张旧表中19个非空表、31行合成旧记录逐值保持；再次执行head迁移，全表快照不变。 |
| 旧计划不自动启动、恢复不补造确认冻结 | 每种数据库以明确同库Session运行3次实际Worker tick，均idle、无模型请求、无新卡/冻结；仅新增本worker心跳，原业务与助手行不变。 |
| 两库迁移及并发本轮证据 | 每库12阶段：8类唯一约束、原计划版本CAS、两个实际Worker同步争租约及旧fence拒绝、outbox通知flush后故障回滚/重试、两连接同步竞争。唯一/CAS为两个独立连接的先胜后拒；实际同步竞争是Worker和outbox两组，不混称。 |
| 联合恢复成功、错误引用及缺附件拒绝 | SQLite原联合备份恢复；PG原生pg_dump/pg_restore到另一新数据库，附件到独立对象根，原行/序列/字节和hash一致。SQLite21、PG16个原守卫场景全过，含跨员工/店、孤儿、循环、JSON重复键/null、缺失/损坏附件；SQLite另含坏数据库/清单/未完成bundle及已有目标拒绝。 |

迁移与恢复时9张新Runtime表初始为空；随后完整性负例构造可回滚的合法Runtime图、并发路径通过原员工HTTP与实际Worker生成Run/卡/计划，再验证有数据的Runtime守卫。旧数据范围为本次19表31行和1件54字节合成附件，不声称覆盖公司全部历史数据。PG备份为已审阅原生工具流程，原SQLite备份CLI未改成PG入口。

生产仅修改`app/assistant_runtime_integrity.py`与`app/business_assistant_plan_integrity.py`：元数据查询支持SQLAlchemy PG，引用用具名参数，JSON读取保留SQL NULL、JSON null及重复键。实际两库拒绝场景验证原守卫未放宽；未修改迁移或业务状态机。验证后仅更新本项验收记录。

## 输入与进程证据

strict与完整run的五指纹及source/harness/external三个文件映射逐项相同，全部输入运行前后稳定：

| 输入 | SHA256 |
|---|---|
| source | bd6d63ff6209ccd0ed85dfa975a55b43a880f251129a10489aa0ee7c9dc00082 |
| harness | be0830776b372f099b67a842cf85c66ac801281ca4aed527d2ac8d6351d7b159 |
| external input | 233493c328b9d98f4238d39dfe5e40eb4e26052ee276f3310a8fbfce6cabd806 |
| dependency lock | 3910945cf6063ebe984b40cc22667657bd83476dcca1024ef4884b10f01dc930 |
| installed dependencies | e537a94af533e550a48e512063354bc101cc12ab2a9e696bbe0aa7ea207b618a |

测试的生产两文件SHA分别为`3cdee9cb255cae1561d7b1e32b1c291b5febcb23067ccbe87219c15732c0cba1`和`b681a4cc3261b20419eef5289fa53bd4ab92cd1b57b4314ebefd9e0326f38887`。实际依赖前后相同：psycopg及psycopg-binary3.2.12、SQLAlchemy2.0.50、Alembic1.18.4；PG五工具均16.15且哈希未变。13次PG身份核验、16组安全比较均真；26个原生工具调用无超时，停止rc0/status3、原PID与pidfile消失。

25次合成provider请求（源夹具3、两库各11）、真实外部模型0、业务确认0。原员工Cookie/CSRF/门店/岗位检查保留，四个生产功能开关默认关闭。全部数据库、随机凭据、对象、备份和日志均在外部本次owned目录。

原件根为`V/runs/20261005T021313Z-4db44dd34a`，命令原件在`command-results/m83-owned-database-contracts`：

| 原件 | SHA256 |
|---|---|
| run.json | f3fd66e2c6965c109d887c3587b10d4ae590c884229b8921232019dd00614fde |
| command-result.json | c7d89ea441d112de76428fb6716ab03ffd871100f50ef15b7b347b55c1809342 |
| m83-database-contracts.json | b92eb0311783c0cd92c4f0cc5dd322a2dbd4b50804aa50819263e7bc275c85d5 |
| m83-owned-postgres.json | 5f5196217760b5d4c3a537fb210fbb8c84b2e5787634e96ef9cd252df8839c31 |

原生dump2614117字节，实际重算SHA`d5a0c7d7603901ea0f1302f4a9e444d56282d8e71f7df8ea880e86091924bac7`。两份审阅位于`V/closeout-20261003/m83-contracts-candidate-20261005T013054Z-237815bc44`：root的`complete-contracts-root-review.json`有26项真值检查，SHA`87ceff5ca9b7f5603d16bae8f5f3fe6fe98f49aed4f8eff60ecab0f37fcd1ca2`；独立审阅`independent-complete-database-contracts-review-reg.json`，SHA`91232617d5942b97d848a533f13dba8515973dac4662e61fd7a2a295b05afe10`。

runner对本类单命令仍原样记录`phase_complete=true/milestone_complete=false`，未篡改报告或扩充自动放行规则。本计划按以上完整原件和四条完成检查登记done。首探针五次失败和扩展两次失败均保留于对应补丁，未拼接或继承成绩。
