# PATCH-M8-1-MAIN-PENDING-UI-01

2026-10-02，业主明确要求先将当前 feature 合入主分支，再在主分支继续未完成测试。本补丁属于唯一进行中的 M8.1；不修改总计划或正式验收门槛。

main 已从远端 5d38029 快进到 feature 的 176088e，并普通推送；本地与远端 HEAD 一致，原 feature 保留。后续改动和检查在 main 上进行。

允许范围：README.md 的当前分支说明、.github/workflows/browser-click-checks.yml 的 main push 触发；web/app.js 中 HK160 后续财务可视化 analytics/finance 的专项展示（只有来源表 rows、图 labels 及各序列 values 均为空的真实空专项收入原生 details，保留标题、全部明细、非空专项、原定义与导出，不能用净额零判空）；tests/browser_click/scenarios.py 中既有 protocol_error、slow_logout 的原界面恢复补测，tests/browser_click/report_business.py 中 HK160 原财务图后补充三宽原生键盘展开/收起与来源空项核对；当前实施计划 M8.1 记录、docs/architect/progress.md、docs/architect/tasks/main-pending-ui.md 及本轮浏览器结果补充。

定向测试使用原 tests/browser_click/run.py 的白名单镜像、合成 provider、原登录及 API；外置新运行 main-pending19，不恢复旧测试，不继承原 full53/native22 成绩。已停止的 automatic-business17 合成数据库仅复制到新目录，记录父源指纹与当前 HEAD、稳定源码/脚本指纹；原报告、库、截图不改写。新增外置 helper 仅补测原具体缺口，不作为完整套件通过。

检查范围：HK160 三宽长页与原现金数据；HK171/HK190/M12/M05/M06 实际表内横滚及原查看/编辑后取消；M16 侧栏关闭后的主卡、Escape/遮罩焦点恢复、Tab 和草稿保留；协议错误后有效查询、退出再登录；HK099 真实日期条件另记，不能通过改时钟、日期、撤销代替。

异常路径：发现产品错误先保存原失败证据、正常停止验证进程，再登记精确修复范围；不绕过 CSP、权限、原版本或业务事实。四生产开关关闭、真实模型调用为零，PostgreSQL/Linux/live gate/员工/生产门槛独立保留。
