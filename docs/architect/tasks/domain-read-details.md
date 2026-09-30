# 任务：原对象详情与本轮生产差异审阅

**任务 id 与负责人**：domain-read-details；remaining_audit 子代理。向集成负责人报告，不维护共享计划状态或其它任务记录。

**目标与交付结果**：沿当前受控原 API 补齐权益与套餐对象读取，独立人工复核本轮 8 个 Python、3 个 JS 及 capabilities 差异，关注真实误授权、错误事实及阻碍本轮代码与浏览器点击交付的硬 bug。

**架构依据与决定**：采用 implementation_plan.md 当前补丁及 PATCH-M7-7-READ-DETAIL-01、PATCH-M8-1-OBJECT-WIRING-01、PATCH-M6-4-LOGIN-DEFAULT-01、PATCH-M6-6-FOLLOWUP-VIEW-01、PATCH-M6-4-WELCOME-COPY-01。原员工身份、当前店岗位、客户责任、原金额/状态/版本守卫和员工业务确认不改变；有限 fallback 只选择固定读取 provider。

**代码快照与影响范围**：2026-09-30，HEAD 71276037dc920069d6d5fa77311b0a7fdbbc3773 及当前未提交生产差异。按审阅顺序以文件名、NUL、文件字节、NUL 拼接 12 个生产文件的 SHA256 为 f227b8734265af823a18659369e2cc037d9f006f60061e16baf48d552bb3f87f。此次仅新建本任务记录，不编辑生产源码、脚本或补丁文档。

**已完成与当前位置**：两条原对象 GET 已由原 service 生成，并在 registry/capabilities 登记。人工复核未发现本轮新增误授权或阻碍交付的已知硬 bug：

- 权益 member_id 详情先完整复用 group.member_detail 的本店、有效会员及销售/接待负责客户检查，再复用原权益投影；不默选 customer_id。有限存在性事实不代替可用余额、结清或总量，原 100 条历史限制明确标注。
- 套餐详情沿原会员购买列表客户责任、合同授权店和状态规则；未发行记录不向其它店展示。capture 只取该购买原 lot 的本店真实流水，501 探测后超过 500 明确拒绝。正金额 executed 退款须有可见 cash_id 才证明至少一笔现金退款；隐藏来源保持 unknown，零对价注销明确 refund_paid=False。quote/capture 不把 Case id 绑定为 package_purchase。
- 静态 AST 核对实际 49 个 DomainAdapterSpec；36 种 fallback（含 case）均属于自身 object_types 且各只有一个 provider。共享 case 仍仅 flow_case 作通用快照；group_member 唯一为 group_principal，权益精确事实单独分派；package_purchase 唯一为 repair_package。report_query、dictionary_entry、daily_report 保持未绑定，不静默误选。
- 登录保留合法人工深链接，无深链接由服务器 features 决定首页。切店 features 请求携带明确目标店及 storeRequest，成功与恢复路径均受 storeContextVersion/当前切换对象守卫；原请求及助手内存上下文继续丢弃迟到响应。
- setFollowup 仅在员工最终点击后鲜 GET 同一事项，检查目标版本、授权状态/原因及允许动作，然后用服务器当前版本发一次 POST。范围变化要求重新核对；409 读回但不重放；GET 与 POST 间并发仍由原 CAS 拒绝。保留结束事项二次点击。
- 欢迎建议仍按原目录、岗位/门店和最多四条筛选，只将已选业务名称加句号放入空草稿；既有草稿保护、显式发送及后端全部权限/确认合同保留。

**当前收口**：集成负责人已完成07轮13组原生浏览器联合点击（含四组需求覆盖）及外部报告，结果见末尾追加记录。本任务不衍生外部 gates、生产部署或全面验收工作。

**初始审阅验证（历史阶段）**：当时执行了 8 个 Python AST、capabilities JSON 解析及固定 fallback 映射静态核对；未导入 app、未启动服务、未新增运行测试。Fresh01/Fresh03 的版本冲突曾只读核对外部合成库及网络证据；Fresh03 没有请求/响应体和网络时间戳，不能编造精确冲突版本或原文。第二卡截图保持 history 筛选，不据此宣称生产丢卡；后续07轮集成场景已实际打开真实待确认组。历史编码审阅不代替该轮浏览器原件或完整业务验收。

**退出事务外部探针（2026-09-30，test_inventory 接续）**：依据 PATCH-M8-1-LOGOUT-TRANSACTION-01，建立全新仓库外 `runtime-v1/auth-logout-probe-20260930/`。只使用 Python 3.11.4、SQLAlchemy 2.0.50、SQLite 3.42.0；自包含两张最小合成表，沿原 SQLite connect 的 `isolation_level=None`、foreign_keys/busy_timeout 与 begin 钩子设置，额外明确 WAL。未导入 app，未读取 `.env`、真实库、账号或凭据。报告仅记录 SQL 动词、连接标签、状态、时间及错误码，不记录 SQL 绑定值。

- 原 `BEGIN`：A SELECT 合成 LoginSession，B 提交无关合成 worker 表写入，A 单次 DELETE 精确返回 `OperationalError`、517、`SQLITE_BUSY_SNAPSHOT`。A 回滚后 session 计数仍1，B写入计数1。
- 短写事务：`Session.connection(execution_options={'huakangos_sqlite_write_transaction': True})` 的选项在 begin 钩子执行前可见；A 用 `BEGIN IMMEDIATE` 后读取，B 的 INSERT 等待，A 单次 DELETE/commit 后 B commit 完成。终态 session0、worker写入1。实际物理连接1、2回池再借均没有该选项、使用原 `BEGIN`，未传播标志。
- 两组探针均完成且通过；脚本 SHA256 `29883bdb76d1b974ac05ae59a62359d33607d2809045c4392b43477b3b83883a`，外部 `report.json` SHA256 `51084adef0fc3584f2fbe5f347a2267fb87439cf4621366925c8fa87546a0a02`。两库和脚本保留原件，不改现有浏览器实例。

本结果只核对事务机制，不把517追认为 Fresh06 原503已捕获错误码，也不验证完整认证/权限链或替代13组原生点击。生产修复随后由负责人完成，精确差异与源码签名已在下文登记；其它原门槛保持。

**退出修复代码审阅**：已只读审阅负责人对 `app/db.py`、`app/security.py`、`app/main.py` 的实际差异。标志仅在原 SQLite begin 钩子读取、由退出 helper 设置；其它事务与 PostgreSQL 路径保留。SQLite helper 在旧认证读事务 rollback 后先申请短写事务，再完整调用原 `get_user` 重核 Cookie、到期、启用、CSRF和门店岗位；rollback 清除旧 ORM 读状态。随后只有一次按本次真实 session_hash 的 DELETE/commit，无删除重放或错误吞没，路由只在 helper 成功后清 Cookie。原异常处理保持，未发现该差异新增绕权或误报成功。三个文件 AST与 whitespace 检查通过；按 `app/db.py`、`app/security.py`、`app/main.py` 顺序以路径、NUL、字节、NUL 拼接的 SHA256 为 `aaed12b3f35d8fe32eacb61409ebdb696ce3aeb0c1219e707836ba5bd31a4346`，审阅前后重复读取一致。当时代码审阅仍待真实 HTTP 退出复验；07轮已完成同一套13组联合点击，具体证据见下。

**最终联合证据核对（2026-09-30，test_inventory）**：已只读读取 `runtime-v1/browser-click/automatic-20260930-07/evidence/` 的运行汇总、13组点击报告、快照 provenance、需求覆盖及慢查询退出/受控详情读取原件。`complete=true`、`passed=true`、退出码0；预期、注册、执行、通过均13，失败0。生产源码 SHA256 `0ade3e7a781de93a963bc341242488abf386ee7d68bed55178838cc815e22f7a`，脚本 SHA256 `e4265ebdc23ce75c2d1767e272da5bc37167221f380d0c14d4857735eacff921`，复制前后稳定。本次没有重新测试或修改生产代码。

慢查询退出的原生网络原件记录 `POST /api/auth/logout` 返回200，截图/可见文字回到登录页；该场景通过并核对原业务无变化。受控读取场景通过：销售本人客户查询、会员本人详情、权益会员详情、proposed 套餐购买详情均以真实原 API 对照合成库，余额/预占/状态/版本与数据库一致，权益 wallet 和套餐 capture 为空，不据此声明已发行、已付款或履约。外部 auth 探针原件仍为两组通过、报告哈希 `51084adef0fc3584f2fbe5f347a2267fb87439cf4621366925c8fa87546a0a02`，与13组浏览器结果分别保留。

本轮另实际完成193搜索、111指引、70原页面、9空表单打开后取消。只有客户新增与第一接待分派两个业务子动作实测通过；来源不完整提示、完整业务验收为否、人工统一评价 pending 与员工效率未测仍保留。真实模型、PostgreSQL、员工试用和生产条件未由本次替代；旧失败及审阅签名不覆盖。

**随后主代理人工审阅结果（独立证据）**：manual02与automatic07生产/脚本指纹完全相同，实际IAB销售登录、三宽度、手机准备客户→单次确认→刷新→原客户页→退出已执行，数据库对应客户恰一条。六项人工评分3/3/3/4/3/3，详见 `V/browser-click/manual-20260930-02/evidence/manual-review.json` 和v2浏览器检查点；自动报告自身的pending保持当时事实，不改写原件。开发者审阅不替代员工试用或效率。
