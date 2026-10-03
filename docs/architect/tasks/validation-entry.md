# M8.1 正式外部验证入口接线

负责人 validation_entry，向 root 交接；2026-10-03。

目标：保留历史绑定与原证据，将 V 的正式入口一次性绑定到当前同 Git 工作树，保留 M8.1 两个既有合同并追加当前完整原生浏览器入口。采用 `PATCH-M8-1-VALIDATION-WORKTREE-BINDING-01`，严格绝对路径绑定、合成数据库与网络守卫不改。

范围：仅 V 内固定 adapter、静态注册清单、harness 必要白名单、当前 binding / manifest 和不可覆盖的迁移记录；本文件记录本任务。生产代码、仓库测试入口、根实施计划由 root 维护。

当前位置：核对旧 binding 和 manifest 均仍为 `E:\HuaKangOS`，没有中断前遗留的 adapter 或 binding-history。只读 Git 核对两路径 common-dir 均为 `E:/HuaKangOS/.git`，origin 相同。已新建 V 的 `harness/m81_browser_inventory.py` 与 overlay `tests/m81_browser_entry.py`；静态编译通过，AST 读取当前 56 个脚本与 77 个场景，没有导入 app 或场景模块。

下一步：待 root 冻结本轮新增注册文件后，exclusive 保存旧 binding / manifest / provenance / isolation 的字节与 SHA，再登记精确白名单、完整场景清单与 adapter。由 root 独立审阅后执行正式新 run。

验证边界：本任务没有启动验证、浏览器、数据库或业务服务；接线不表示任何验收通过，原 runs 和历史成绩保持原样。
