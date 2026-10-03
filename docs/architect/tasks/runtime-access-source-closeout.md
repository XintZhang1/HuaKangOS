# 任务：原管理员撤权和 source-map 事务收口

**任务与负责人**：`runtime-access-source-closeout`，Codex 子代理 `mobile_closeout`，向 root 交付。只维护本记录及对应补丁，不改共享进度、实施计划、生产或共同入口。

**依据与目标**：当前唯一 M8.1 表 9/10；原 `M4-7-source-map-v1.md` 七类生产者及原登录、权限、Case/Task、Grant 和通知合同。新员工默认账号 sales，仅明确授予本店 reception；原 UI 首次改密及重登；实际管理员撤权 commit 后迟到响应拒绝，单原 worker 20 tick 无重试。七类真实生产者和无 Grant Plan close 的固定事务失败；两独立 Flow 来源真实 30 秒退避形成后创建先分发；重复原 signal 和原本人已读通知不复活。

**代码范围**：`runtime_access_closeout.py` 和 `runtime_source_hooks_closeout.py`，模块导入不启动实例。全部新来源从原 UI 创建，SQL 只读观察；故障器只在固定原 emit/dispatcher 边界作用。本任务注册前不进入 runner/source 指纹。对应补丁为 PATCH-M8-1-ACCESS-CLOSEOUT-01、PATCH-M8-1-SOURCE-HOOKS-CLOSEOUT-01。

**当前实现**：两独立模块已完成，provider/observer/scenario 出口已定义。核对原任务最少待办分派可能选另一员工后，补齐原管理员页面转交真实 Task、实际 version +1、唯一 reassign 事件及原 Case/客户不变；停用表单在这些前序完成后才准备、但仍在响应门控前。Case 创建后等待原标题及真实 Task 控件，避免响应已返回但页面未渲染的装置错误。

**验证和限制**：仅 AST 解析、导入符号/实际 API 合同人工审阅与 whitespace 检查，未运行服务、测试或真实模型。root 负责白名单、provider、生命周期 contextmanager、三个 worker 模式和场景注册，之后从全新外部合成镜像实际验证。脚本实现不表示事务或撤权验收通过。

**相邻失败保留**：`closeout-contracts-05` 六场实际四通过两失败，服务正常退出、无强杀。logout 两 Run/两卡和通知断言已完成，重登后的历史目标在原 sessions GET 返回前点击导致 count 0；已在两处等待指定原会话可见。outbox CAS 核心 201/回滚/退避/后继/通知断言已完成，末次结束点击未发 POST；追加刷新后真实 Workspace idle 等待，root 另修同 scope GET 清 arm 的生产 UI 竞争。原失败证据外置且保留，复验由 root 执行，不将已完成局部断言写成全场通过。

**本次冻结与交接**：`runtime_access_closeout.py` SHA256 `d1e58ec81c9b013e1e7b45bf3383a406a76cf53ff93e693a5cf168d7bb113c08`；`runtime_source_hooks_closeout.py` SHA256 `98ccd12aba6f08325cc00b026743cb22bd9d71d4078a20aa9ccf6b28cf287103`。AST 解析、静态导入符号存在性和 `git diff --check` 通过，没有导入应用或启动测试。待 root 统一接线与实际复验。

**2026-10-03 contracts07 实际失败与修复**：root 定向五场实际一通过四失败，服务正常退出且未强杀，原报告在外部 `browser-click/closeout-contracts-07`。logout 全场实际通过，不能继承为全套。source-map 已验证 Grant、无 Grant Plan close、Flow source 三次固定事务回滚；Flow 500 后原 close 触发未保存内容确认，脚本未点“放弃填写”，故之后的新建被原 modal 遮挡。补齐原 Cancel、实际出现时明确放弃填写、等待原 modal 关闭及丢草稿前后业务 hash 完全不变，五类原失败表单均共用该流程，不 forceclick 或重放原提交。

late-source 原本人 notice/read 实际 HTTP 422：后端明确不接受任何请求内容，但前端发了 `{}`。这是真实前后端合同接线缺陷，交 root 修前端；原脚本仍严格要求 HTTP 200、持久 read/时间和原任务 open，并补原服务器返回及请求内容观察，明确要求空请求体。admin 原 receipt/access-version commit、实际迟到响应返回、Grant permission_changed 撤销均存在；Run 终态却 cancelled/precondition_conflict。根因是 runner 原 `_cancel_fragment` 对 revalidation 401/403 无条件存 precondition_conflict，已给 root 定位及三调用点的最小错误分类修复建议。脚本仍严格要求 permission_denied，并在断言前记录实际终态/Grant/来源，20 tick 未执行仍明确保留，未降标准或将局部事实写成全场通过。

两模块本轮冻结 SHA256：access `5af1da8285987bdbf633013391d9bee0a0e29be8e9c28863b368c1136d7ab9f7`；source `b78c0926e15446682563004dc936ef47c1331e545391befb0af9ddc53a6382f6`。AST 和 whitespace 检查通过，未启动新验证或改生产。

**contracts08 原件与后续冻结**：四场完整执行，两通过两失败，CLI 1、service 0、未强杀。原管理员撤权及旧 lease 迟到写入两场实际通过；仍不等于全部 M8.1 验收。source-map 只到 Grant 和额外无 Grant Plan close 两次完整原事务回滚，后续 Flow/Task/Proposal/access/security/store 均未执行。第二次 500 原浏览器尚未清除 arm 时测试立即 refresh，随后标注“第一次核对”的动作实际发 POST 200；隔离库只读确认 Plan cancelled/version 3/goal 1、Grant 空。下一点击寻找已销毁按钮超时，非后台失权或原回滚失败。仅 `_arm_original_end` 等原错误处理结算为未 arm 后才 refresh；refresh 后重核未 arm、首次点击后等已 arm，三边界均须同 Plan、全 idle、原按钮文本及 enabled。原唯一 500/hash/login/新旧 Wake 断言保留。late-source 实际无请求体仍被全局缺 JSON Content-Type 守卫拒为 415；root 恢复原类型头并保留 undefined 体，原全局守卫与 read API 不改。source 新冻结 SHA256 `9eadf873d4473224ce3da57a9a094fce84f199092d0ed0ad0ccb7683bdf262a4`，access 不变；AST 与限定 whitespace 检查通过。root 已启动 contracts09 两受影响场；本代理未运行测试，注册源码再次冻结，新结果待实测。

**M8.4 只读补审（不登记里程碑通过）**：`native-cookie-csrf-csp-sse` 已包含真实 Chrome 网络中断/loadingFailed、浏览器原 Runtime 游标冻结、服务器离线时继续终态、恢复请求 after_seq 等于断点且大于零、最终 event_seq 连续及零卡/原业务不变；并关闭及重启独立 Chrome，通过原登录及历史读取同一已成功只读 Run，不重发。外部 `frontend-full-20261003-01` 此场实际 passed/20.36 秒，但该 57 场 run 整体失败且旧指纹，不能继承为当前全量。重启路径新建 context 并重新登录，不证明持久 profile Cookie 跨重启或进行中准备恢复。

当前 runner origin 固定 `http://127.0.0.1`、fixture `COOKIE_SECURE=false`；登录仅断言 HttpOnly/SameSite，并未要求 Secure true，故 HTTPS 安全会话尚缺。最小后续真实路径是全新外部合成实例的独立 HTTPS profile：真实浏览器信任的 TLS 证书、COOKIE_SECURE=true、原 Cookie/CSRF/CSP/SSE 与空体 JSON 头合同；分别留 Secure Cookie、TLS 及当前指纹证据。Windows 可直接用现有 Python/uvicorn 与已安装 OpenSSL，无需 Docker/WSL；证书信任条件仍须落实，不能把 ignore_https_errors 或关闭浏览器安全策略当作验收。

中文脚本目前仅 `keyboard.insert_text`、Shift+Enter 和一次真实 30 秒通知轮询后的焦点/光标比较，全 headless；没有 Windows 原输入法候选，也没有 20 条真实状态事件期间的 IME/补填焦点保护断言。已只读确认 miniconda Python 有 PyAutoGUI 0.9.54、pywin32 311，Windows 实现使用真实 user32.keybd_event；AutoHotkey/AutoIt 常见安装路径及 PATH 未找到。HKCU 预加载含 00000804/00000409、系统 CHS 目录存在，但当前选中输入法及候选窗尚未实际验证。当前 CUA native API disabled，现有 Python 系统输入模块是可行的替代候选，未执行：需 visible headed Chrome、真实前景窗口、现有中文输入法的拼音键入/候选选择及系统屏幕候选证据，再核输入/答案、光标/选区/焦点跨真实后台事件与三宽度不变。不能用 JS composition、Unicode insert_text 或剪贴板代替真实候选；本轮没有操作 UI、改变 OS 设置或安装工具。

**contracts09/10 及当前交接**：09 两场完整、CLI 1/service 0 正常收尾；notice 原空体/application-json 请求实际 200、持久 read、Task open 整场通过。source 八种原 producer 的唯一注入/原业务/login/新旧 Runtime 全行回滚均成立，但旧全局零 5xx 门禁使整场失败，原件保留。root 的精确期望故障接线已独立静态审阅：仅指定 source 场景可登记八个不同 scope、八种 kind 各一，全部实际 500/proof true；actual >=500 的 path/method/status Counter 必须完全相等，其他场景必须零登记/零 5xx。10 新 source 单场仍失败，前两回滚成立，action49 仅等待原未 arm 状态 20 秒超时；没有后续新员工点击，第二次 500 后有同 Plan 先前 GET 200 晚返回。按源码与时序推断 `loadPlan` 保存的 arm 可恢复 catch 已清意图；未直接记录 JS 两次赋值。root 加当前 `state.revokeArmed===true` 守卫已只读审阅，原同 id/goal/status/grant/allowed/serial/context 及每次 GET/CAS/无重放不变。

本任务仅补三原等待超时时纯读 Workspace/原按钮、同 Plan/Grant 最终行及原员工页面截图，诊断失败单独留证，原 timeout 原样 rethrow。原 false/true 等待、20 秒、HTTP500/唯一故障/hash 和成功范围全部保留。source 新冻结 SHA256 `fbfc3e4a54fcfde8729a53f8828d7ed3f3097f0867dfd65c9537ef78c9c5395b`；AST 与限定 whitespace 检查通过，无 app 导入、UI 操作或测试执行。生产守卫和诊断待 root 的 contracts11 三场实测；本任务脚本及本任务文档至此冻结，后续完整新结果不得继承旧局部成绩。
