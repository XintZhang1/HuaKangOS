# PATCH-M8-3-PG-INTEGRITY-01

2026-10-05，M8.3 当前首探针第5轮 `20261005T010657Z-d02027bf91` 实际复现生产兼容缺口：SQLite升级及联合恢复完成，真实PG的h52j建库、非空原行投影、h53k升级和旧值核对已执行；原Runtime完整性函数在PG查询`sqlite_master`，SQLSTATE42P01。strict `20261005T010624Z-81f0f06494` 18通过，与探针五指纹相同且未变；探针56.719秒自然exit1，原PG停止和排空证据完整。PG联合恢复尚未执行，不能记通过。

## 精确修复范围

- `app/assistant_runtime_integrity.py`：数据库表/列元数据对SQLAlchemy连接使用原项目已有的inspect模式；原sqlite3连接保留原查询。固定SQL执行助手允许具名绑定参数；PG已知JSON列选取原始文本，保留SQL NULL、JSON null和重复键差异，不用已解码对象重建JSON。
- `app/business_assistant_plan_integrity.py`：复用上述有限读取助手，用具名参数核对原卡引用；PG的旧steps取文本后仍由原解析/WorkStep/graph合同校验。继续跳过engine2的历史steps快照，不增加或放宽业务规则。
- 本补丁、M8.3原项、architect任务/索引与本项验收小报告。

不修改迁移、业务表、备份内容、数据库连接配置、确认/身份守卫或原JSON有效性合同；不新增通用数据库抽象层。原SQLite CLI仍只支持SQLite；这两处只读完整性函数支持M8.3已登记的实际SQLAlchemy PG连接，不扩充raw psycopg接口。

先在外部候选保留两文件原字节、审阅窄差异；通过原统一入口重新strict和首探针。首探针通过后仍需M8.3原并发、错误引用、缺附件及恢复拒绝路径，不把空Runtime表的升级核对当作全部Runtime完整性验收。

2026-10-05实际结果：两文件候选分别为 `3cdee9cb255cae1561d7b1e32b1c291b5febcb23067ccbe87219c15732c0cba1` 与 `b681a4cc3261b20419eef5289fa53bd4ab92cd1b57b4314ebefd9e0326f38887`，经root和独立agent审阅正式合入。strict `20261005T011612Z-7a4e2b079c` 18通过；首探针 `20261005T011722Z-77b19bb18d` 1通过/exit0，SQLite与真实PG16.15的升级、原完整性及联合恢复全部实际走通。五指纹一致且未变，原PG停止成功，无真实模型请求。剩余原合同继续M8.3，不以本次空Runtime升级检查替代损坏JSON和并发验收；详见M8-3-first-probe-review-v1。
