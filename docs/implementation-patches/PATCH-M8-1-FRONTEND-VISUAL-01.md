> 来源：E:/HuaKangOS 业主安排的视觉实施记录，2026-10-04 整合保留。下文结果属于原候选；当前状态和复验只查 implementation_plan.md，旧 CI、mutex 与时间预算以当前源码为准。

# PATCH-M8-1-FRONTEND-VISUAL-01

2026-10-03，按业主本轮截图与明确要求实施，同属当前 M8.1 收口，不另开里程碑、不改原正式验收门槛。

## 问题与结果

模块指引链接呈现浏览器默认样式；统计导航重复展示报表目录；各处“交给助手”按钮冗余且存在不可用体验；助手控件缺少清晰层次；全站视觉需要参考 Salesforce Lightning。改为统计直接进入数据可视化、原报表作为其中可查的子入口，保留原业务/岗位/深链接；移除交给助手按钮，员工由业务助手输入。调整助手控件及全站视觉，使用真实浏览器鼠标操作审阅。

## 精确范围与归属

- 导航与链接：`web/app.js`、`web/moduleworkspaces.js`、`web/assistantworkspace.js`、`web/businessux.js`、`web/workflowguides.js`、`web/workflowcontent.js`；不改业务 API、权限或报表计算口径。源码核对发现工作流文章另有不走共用入口的独立助手按钮，一并移除。
- 助手控件：`web/businessassistant.js`、必要的 `web/businessassistantfiles.js`；保持原确认/停止/草稿/忙碌与迟到响应守卫。
- 全站样式：新增 `web/lightning.css`、在 `web/index.html` 引用；按实际布局保留响应式与可访问性。
- 测试与记录：`tests/browser_click/` 现有脚本、README、截图记录生成模块和 `records/`。保留当前已注册主要流程及真实 HTTP/浏览器点击。按用户新要求，只有合成页面截图和逐项 Markdown 记录可附在测试文件夹；完整日志、密码、数据库、配置仍在外部 NTFS 隔离目录。失败原件保留，报告不继承历史结果。
- 总时限适配：`tests/browser_click/run.py` 的全套进程预算、`.github/workflows/browser-click-checks.yml` 的作业预算；原每场景时限与验收断言保持。首轮实际3109.21秒，未完整执行的末报表原预算1500秒，原3600秒总时限不足覆盖原合同的完整执行预算。将总时限设5400秒、CI作业105分钟；超时仍失败，不使用局部结果放行。
- 审阅记录：本补丁、`docs/architect/tasks/frontend-visual.md`、共享索引本任务条目、`implementation_plan.md` 当前记录、必要的新检查点报告及根 README 的入口说明。

## 异常路径与验收

保留切店/退出、未发草稿、待卡、未知结果、员工/门店权限、集团只读、失败即停批量、中文输入与窄屏。390/768/1440、统计图表/明细/原报表入口、助手发送/附件/新对话/历史/停止/人工确认与原业务主要流程实际点击复测。每项记录实际结果、动作数、截图、源码与脚本指纹；没有截图或失败不得写通过。合成模型阻止外网；不开启生产开关，不调用真实模型，不部署。

## 视觉参考

参考 [Salesforce Lightning 按钮](https://v1.lightningdesignsystem.com/components/buttons/)、[卡片蓝图](https://developer.salesforce.com/docs/platform/lightning-component-reference/guide/lightning-card.html) 的蓝色主操作、白底次操作、细边框与清晰分区；助手会话工具参考 [Claude Code 桌面会话组织](https://claude.com/blog/claude-code-desktop-redesign)。使用本地 CSS 与原生 SVG，不引入外部样式、组件框架或请求。

## 实现代码审阅

导航/助手控件由两子代理分工，root 集成；独立只读审阅发现并修正普通岗位无法调用经营汇总 API 的返回导航、移动端原直接子控件选择器失配，以及窄桌面输入区操作宽度。有汇总权限的岗位直接进入可视化；普通岗位旧深链接与已授权专项入口保留，不新增汇总读取权。原草稿、历史、停止、人工确认、合法引用与迟到响应守卫保留。生产 JavaScript Node 语法检查、测试 Python AST 与差异检查通过；浏览器实测结果另附本轮检查点，不提前记 passed。

## 首轮失败与修正边界

`frontend-full-20261003-01` 完整执行57项，52通过、5失败，CLI退出1；服务退出0且未强杀。该轮1323个安全截图/Markdown文件已发布至测试记录目录，原证据不覆盖。失败包括旧CSS隐藏新键盘提示、新脚本假设不存在的销售侧栏模块链接、相同标题提前满足造成报表目录加载时即点击、持续跟进收尾期间连续两次真实409，以及末项授权检查的旧信号集合断言。末项原因另核，不预判为产品缺陷。

显示修正只在晚加载样式恢复 `.ba-compose-help`；测试导航改为真实快捷操作入口并等待实际目录加载。跟进测试在待确认后继卡出现后，只读等待其真实Run成功与当前同事项wake事件分派完成，再执行原两次结束确认；开始/结束快照和耗时留证，不写库、不关worker、不改CAS、不新增盲重试。首次拒绝期间授权和原业务均保持不变，现有证据不足以宣称后端数据缺陷。

末项只读诊断确认：UTC01:46:04.164781 的授权回执11只新增门店1、3两条 `access.changed`；旧 `task:641:1`、`task:643:1` 在04.359453/04.414490正常分派，旧回执10在04.324493推进调度。新增集合没有其他信号；原全行相等误把调度字段更新判作覆写。按照实际 `assistant_runtime_outbox.py::_event_cas`，装置只允许旧pending行的 `state/attempt/next_attempt_at/dispatched_at/version` 合法同增，旧ID、其余全部列和旧dispatched行仍严格不变；新ID集合仍须恰等于当前回执的精确门店信号，并记录前后差异。此为过时测试合同的窄适配，不修改生产实现或删除旧失败。

定向controls-02执行4项，3通过；跟进等待/真实撤销已成功，无409，但后续M16旧脚本要求历史弹层节点删除而失败。新控件为 `aria-controls` 保留稳定隐藏节点；`pending_ui.py` 改核节点存在、`hidden` 与实际不可见，并保持打开可见、历史、草稿、键盘及三档宽度检查。controls-03执行2项，故障恢复通过，跟进暂停阶段连续两次409，按原门禁失败，正常停服。由实际时序将来源等待通用于暂停及结束前：核本卡唯一成功Run、同事项所有当前Run终态及全部wake分派，重读不得遗漏新Run；不改任何业务提交与重试边界。两轮失败与截图都保留，不能合成完整通过。

controls-04发生执行器故障：`runtime_faults.py::_atomic_json` 替换 `runtime/worker-state.json` 时WinError5，监督器因此退出，restart与后续Run超时；服务退出3、未强杀，两个失败和6个安全记录文件保留。精确修复仅限该测试文件 `_load`：Windows打开控制JSON时允许读/写/删除共享，使现有原子替换可与只读句柄并存；其他平台读取不变。保留原子写、错误抛出、原进程与超时断言，不加替换重试、不改OS权限或生产代码。句柄交由文件流关闭，失败路径也关闭，不泄露凭据。
