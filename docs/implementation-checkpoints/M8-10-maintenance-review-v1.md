# M8.10 维护交接审阅

2026-10-05，按 PATCH-SCOPE-MAINTENANCE-20261005-01。此前数据库修复及范围调整已经推送 main（b92c5f7）；本次整理不改变业务规则、迁移、默认开关或确认接口。

## 交付内容

- README、ARCHITECTURE、CODEX_EXECUTION_PROMPT、DEEPSEEK_TESTING_HANDOFF 与 `docs/维护交接.md` 按实际源码说明 Web、Runtime worker、准备/人工确认、跟进、回执和独立运维助手；补齐五条读码路径、配置归属、数据库管理和验证材料来源。
- 五处生产注释说明批量首失败停止、worker 注入连接归属、读取前后权限重验、跨恢复预算及实际 HTTP 尝试计数。原架构文档的旧批量继续执行说明同步修正。
- `scripts/package_source.py` 仅给原白名单加入六份现行根文档；不改变环境、数据库、测试、CI、日志与凭据排除规则。

## 实际核对

root 独立核对五个生产 Python 文件的 AST（去掉 docstring）与 b92c5f7 一致；打包脚本 AST 只有精确六份文档集合差异。总计划及迁移无改动。文档作者与 root 分别核对 91 个本地链接；启动、迁移和关键函数按源码核对，`git diff --check` 通过。没有改 JS，没有因此重复运行长回归或启动业务实例。

原打包入口实际退出 0，检查包有 1276 文件、69 个完整迁移目录文件，九份必需维护文档齐全；ZIP CRC、逐文件与工作树字节核对通过，未包含禁用路径、数据库、日志或凭据模式。包生成于本审阅和最终状态记录之前，只作白名单验证证据，不冒称后续模型候选的完整指纹。

外部证据：`V/closeout-20261005/maintenance-review/package-inspection.json`；检查包 SHA256 为 `fc23fb3efa8a68408d2a815b83d2e63e92d46727604f9f21c678daaa41639cb8`。文档独立静审：`V/closeout-20261003/maintenance-doc-review-20261005T033514Z/static-review.json`，SHA256 `a3597db56c8f50fbabbc9a5586eba4b9f5eb4d4e1aac789129907a90111d04e5`。

## 结论与边界

本次维护交接范围可收口并推送 main；M8.5/M8.6 真实模型复验单列，尚未发起本轮生成调用。M8.4/M8.7/M8.8 未执行剩余项已由业主取消，不记通过；员工与生产验收不代签。运维邮件仍依赖原部署的外部 SMTP 模块，文档已经明确，源码包不宣称包含完整邮件运行环境或完整归档验证材料。
