# PATCH-M8-1-MAIN-RESUME-TESTS-01

2026-10-02，业主要求继续未完成测试并提交 GitHub。归属当前唯一 `in_progress` 的 M8.1，沿 MAIN-PENDING-UI-01/NATIVE-SSE-RECONNECT-01 补齐有限点击路径，保留原 M8.4/CP-36 和其它正式门槛。

当前 main `6d2368e`、工作树初始干净且已快进同步。fresh `main-resume23` 原入口真实执行 security 一项，CLI1；游标从1到6且等于原 event_seq6，只有 after_seq0请求，页面异常0，合成4/真实0/外部0。浏览器离线没有断开已打开流，不能据此归因产品，也不能删除补读断言。

允许范围：`tests/browser_click/scenarios.py` 现 security 用 Chrome 原生 `Page.stopLoading` 中断已有请求并观察真实 `Network.loadingFailed`/本地游标，随后保留原非零 after_seq、完整终态、原业务不变检查和独立 Chrome 重启；如果实际浏览器命令不能关闭已有流，可在 `fixture_server.py` 的隔离服务控制循环按外部明确标记仅关闭对应 Run 事件 TCP transport，记录真实连接关闭，不修改 ASGI响应、事件、Run或业务事实。失败原件仍保留，不以命令成功冒充断线。

新增 `tests/browser_click/pending_ui.py` 只读补测函数，复用原 followup 的本人 session/plan/second_card 和原 source report 的真实库存/采购来源；主卡三宽、历史关闭、抽屉 Escape/遮罩焦点、原生 Tab/草稿和768表内横滚/原单。接线仅涉及 `scenarios.py` 的 followup尾部、`report_complete_source_business.py` 的原报表读取尾部、`run.py` 的 SCRIPT_FILES；`report_complete_source_business.py` 所用 `nav` 的原函数归属先核对，768导航必须先点击真实菜单再走原目录。辅助函数不继承旧parent成绩、不改业务日期、配置、权限、状态或金额，也不复制旧库。

允许维护 README/点击入口说明、当前 M8.1记录、本任务及 progress条目、本轮递增检查点。应用缺陷另登记实际文件与原因后实施，任何编辑先收尾相关进程。全部 app 导入/运行仅在原白名单外部全新 NTFS 镜像，合成provider阻外。HK099旧grant已主动撤销且有效截止2026-10-02，不能算真实到期；到期边界仍需独立active授权及真正次日。原模型/PG/Linux/员工/生产及四开关默认关闭不变。

fresh `main-resume24` Chrome原事件请求真实 `net::ERR_ABORTED`，离线游标1保持至原服务seq6，恢复请求after_seq1并完整应用6。后续旧整库比较误包含前面故意 `/api/users` 403追加的原 `escalation_refusals`。允许 security 对故意拒绝单独核唯一新增服务器 refusal（本人/店/path/原refusal_id/旧行及其它全表不变），后继SSE/重启以拒绝后真实快照核零业务写入；不忽略拒绝表，不改原拒绝服务或放宽权限。`Page.stopLoading`仅是浏览器终止资源传输，不能声称OS网卡或TCP RST验收；[原生协议合同](https://chromedevtools.github.io/devtools-protocol/tot/Page/#method-stopLoading)。

精确768导航归属为 `tests/browser_click/vehicle_purchase_business.py:nav`；只在真实 sidebar不可见时点击原菜单并等可见，再沿原link/details导航，原请求/标题/全表保护保留。原管理封闭面 `/api/users` 的服务器分类为rule/can_escalate=false，测试不得猜成authority。fresh25错误猜分类的失败也保留；fresh26的同场景全部执行通过CLI0，含真实断流/非零游标补读和两次独立Chrome原生登录/历史恢复。

fresh27九项联合8过1，完整报告但整体CLI1；M16三宽/抽屉/键盘及4恢复检查通过，M05表内右列通过，M06已经原生菜单与真实筛选/表/CSV/图成功，原滚轮装置把容器可见区域中点取在sticky topbar遮挡区（y71.76，容器top0.36/bottom143.16）。仅调整 `pending_ui.py` 原wheel落点的可见交集上边界为真实topbar.bottom，保留单次可信wheel/右端/末列/全表hash断言，不动产品CSS或直接赋scrollLeft；失败原件仍保留。
