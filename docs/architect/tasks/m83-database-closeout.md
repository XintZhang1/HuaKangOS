# M8.3 隔离数据库升级与联合恢复

负责人 root；当前范围与状态只以 implementation_plan.md 的 M8.3 为准。前置 M8.2 与 CP-35 已按 v23 双平台原件释放，main 基线 bf08ec1。

本项已按原四条完成检查收口，完整结果见 `docs/implementation-checkpoints/M8-3-database-closeout-review-v1.md`：021313Z-4db44dd34a完整1节点通过、284.797秒，同strict18五指纹与三文件映射不变；两DB各3旧计划tick/12并发、SQLite21与PG16拒绝及原独立恢复全过，PG正常停止、模型0。root26项与独立原件审阅完成；只在实施计划登记done，CP-36待M8.4。以下保留各轮当时记录。

先实施 PATCH-M8-3-OWNED-PG-PROBE-01 的有限首探针：实际非空 h52j 事实、唯一 h53k 升级、真实完整性检查以及新数据库/新对象根联合恢复。外部缓存 PostgreSQL 16.15-5，主数据库仍为 runner 标记的 SQLite，PG 集群只在全新 command-runtime 建立。

首轮当前源码strict18通过；首探针`20261005T004405Z-a5a0da8c12`实际1项/1error、exit1、21.25秒自然退出、五指纹与strict一致。原员工HTTP/合成provider及SQLite旧库升级已执行；原计划校验拒绝新夹具多余status键。仅删除此键后重新strict/首探针，保留失败原件与校验合同；未启动PG、真实模型或生产服务。原M8.3并发、错误引用、附件拒绝和完整恢复均未预记通过。

第二轮strict18通过；`20261005T004837Z-4cd69a12b0`在44.407秒后自然failed，SQLite原升级/守卫/联合恢复实际完成，PG init/start成功但DDL前身份比较拒绝。实际stop rc0/status3、原PID及pidfile均消失。下一步只补该比较安全诊断再重验，未改生产代码或记全项通过。

第三轮诊断只定位到IP文本的/32掩码差异，原10项其它身份比较全真；只改查询host表达式，保持严格地址和所有权判定。第三轮strict18通过、首探针仍failed、PG正常关闭；原件见补丁所列005549 run。

第五轮真实PG已完成h52j投影、h53k升级与旧值核对，原Runtime完整性sqlite_master查询失败42P01；当前day负责外部候选两只读接口，root审阅与正式合入/验证，范围见PATCH-M8-3-PG-INTEGRITY-01。原五轮失败和正常停止证据保留，不提前记PG恢复通过。

第六轮已完整通过：strict `20261005T011612Z-7a4e2b079c` 18通过，首探针 `20261005T011722Z-77b19bb18d` 1通过、84.844秒自然退出；原两处生产修复已双人静审和动态验证。475旧表/19非空/31行及1件私有附件在SQLite、真实PG升级和独立恢复均保持，五指纹稳定，PG正常停止。详见M8-3-first-probe-review-v1；新Runtime表仍为空，未覆盖原剩余合同。

下一增量仍为M8.3：root负责重复head迁移、实际旧engine1计划三次Worker tick不自动启动及统一入口接线；day负责两数据库唯一/CAS、实际双worker租约和事务outbox；mobile负责原完整性/附件拒绝；regression独立审阅。三方只在外部候选实现同一里程碑的检查，root逐项合入后统一实际运行。无其它里程碑in_progress。

完整扩展首轮实际failed：015431Z-7ee005cea8，1error/164.719秒、正常排空/PG停止；SQLite三tick/21拒绝/双Worker/outbox/CAS/前三唯一走通，测试proposal-work准备提交因第二读取事务未结束停于OperationalError。day仅结束该准备读事务，root补安全sqlite整数码与登记，reg独审；之后重新完整命令。不改生产或把片段当通过。

扩展第二轮020357Z-95accd942e仍failed：147.453秒、自然排空/PG停止，SQLite21拒绝和12并发子阶段、原行和完整性核对已执行。最后activeGrant断言暴露夹具先结束事项后新增结构授权的收尾顺序错误；只把前次本人revoke改pause，最后revoke和全断言不变。后续PG扩展未执行，继续同一M8.3。
