# 任务：原生浏览器固定点击场景

任务 id：`browser-scenarios`。负责人：点击场景子代理，向 `browser-click` 主任务交接。

目标：为当前真实隔离 HTTP 服务实现九组有意义的原生点击路径，统一可复现门禁和人工体验评价。新增需求分层覆盖由 `tests/browser_click/requirements_click.py` 提供；本代理维护上述两脚本、`rubric.json` 和本记录，清单和隔离入口由对应作者维护。

架构依据：M8 的既定员工身份、原业务 API、人工确认、依赖事实和默认关闭开关合同；本轮 `PATCH-M8-4-BROWSER-CLICK-01` 授权。生产源码保持只读。

实现：CLI `python scenarios.py --manifest <绝对 JSON> --browser <绝对 browser>`。manifest 与隔离入口协定；密码仅从外部 credentials 读取。浏览器原生同源请求，不替换 fetch、不注入前端 state。正业务提交只点真实 UI；安全拒绝与补充只读域查询使用 context.request，readonly_http_checks 与点击分别计数；SQLite mode=ro/query_only 核对。逐场景保留动作数、真实点击数、截图、可见文案、请求状态和数据证据，排除原始 Cookie/密码/推理及 trace/HAR。

固定九组：欢迎/390、768、1440/草稿/中文输入/Shift+Enter/焦点；原人工深链接；只读无卡及真实 Cookie 会员详情/数据库对照；客户准备、手机卡页签、确认、历史无重复；两步接待依赖和开启/暂停/恢复/结束；慢查询换店；慢查询退出；异常无卡；Cookie/CSRF/CSP/SSE 及身份伪造拒绝。只读查询要求助手实际回复含数据库客户全名，不能由用户输入自满足。焦点核对等待现有 30 秒通知轮询的真实响应；慢查询先观察真实 running 才切店或退出；暂停时仍以 UI 确认原第一步，跨 worker 检查周期后要求后继未准备，再恢复准备。

同组补充覆盖本轮新增 GET `/api/group/benefits/members/{id}`、`/api/repair-packages/purchases/{id}`，与原会员 GET 和 SQLite 字段对照；使用原服务预置的 proposed 购买，空核销不冒充实际收款或正向核销验收。人工导航组额外真实退出并在有效客户深链接重新填写登录，验证登录后 hash 保留。

数据库零写核对动态枚举原业务表，以单一只读事务逐行全列哈希排序；报告仅保存表/行计数和摘要。排除助手自有表、真实 `login_sessions`/`login_attempts` 和 SQLite 内部表；`app_metadata` 只排除 exact `assistant_runtime_worker:` 前缀行，其余保留。四表计数继续用于结果定位。查询、准备、异常、换店/退出和确认后历史均比较摘要，能发现原行更新而非只检测新增行。

统一标准：所有注册场景实际执行且通过才能过自动门禁，失败、超时、空场景非通过。文案简洁性、操作容易程度、视觉质量另按 rubric 人工评分，初始 pending；记录点击数不声明员工效率提高 20%。原生中文文本输入不冒充操作系统输入法候选试用。

验证：Python AST 与 rubric JSON 解析已通过；本代理未运行联合浏览器测试，隔离服务完成后的实际跑由主代理执行。报告固定九项 expected_scenarios、complete 和 passed，任何未执行或失败均退出非零。静态观察到新登录可能固定 #work 导致 home=true 默认入口失效，已交主代理用真实点击复现，不能在本记录记为已修复。

下一步：主代理集成运行、核对 DOM/API/数据库事实并按真实失败修正产品或场景错误；保留原失败证据，不降门禁。

首轮集成反馈：主代理执行九组，六组通过、三组失败并已停止服务。欢迎组的默认首页已正确显示助手，脚本把 URL hash 当成必需输出而误判；现按无hash真实登录、原生工作区响应 features.home=true、主标题“业务助手”和输入区可见联合核对，不再额外要求默认路由写入 hash。三宽度和后续交互断言保留。另两组由主代理按真实产品故障处理，本代理不改对应门禁。此修正尚待主代理复跑。

Fresh03 集成反馈：九组完整执行，八组通过；跟进暂停/恢复成功，结束提交遇真实并发版本 409。现限定同场景最多一个受保护冲突：保存真实 refusal、要求“事项已变化”可见、grant 和原业务摘要不变，记录员工核对新状态后的一轮真实重新点击；结束须重新两次确认，最后仍要求200和数据库revoked，其他错误或第二次409立即失败。报告 protected_conflicts 保留首次409，不把它抹去。后继准备后明确点待确认filter并核对第二卡ID、原单号、标题和深链接；欢迎建议追加80字内单行含业务名称的门禁。

Fresh03 的 Task478 Target closed 来源已按本机 Playwright 1.56.0 `_network.py` 源码定位：Response.finished() 在响应完成后遗留 target-close watcher，context关闭后抛出无人接收错误。欢迎轮询改为等待真实响应 body() 完整读取，不持久化内容，不吞异常或修改网络。此组修正仅AST/JSON检查通过，尚待主代理下一轮实际运行。

Fresh04 集成反馈：九组完整执行，八组通过；真实409经过一次员工重核后200/revoked，第二待确认卡身份显示通过，body替代后的Task警告消失。唯一失败为客户组刷新后点击历史前，独立scroll预检遇重绘脱离DOM。最小修正删除scroll与trial两个冗余阶段，仍校验选择器唯一并由原生Locator.click一次完成定位、滚动和actionability；保留所有后置业务断言，不加重试或固定等待。AST通过，尚待主代理Fresh05同九组复跑。

Fresh05 集成反馈：九组完整执行，八组通过；客户确认/历史组已通过，唯一失败为人工导航组在 hashchange 异步读取前把旧助手标题 visible 当作客户页面完成。真实失败截图仍为“正在读取…”，随后同次 observations 已显示客户档案和真实客户。两处导航/有效深链接登录的等待现改为真实 `#main h1` 含“客户”；原草稿往返、真实退出登录与有效 hash 保留断言不变。此为测试同步修正，不添加固定 sleep、重试或放宽业务合同。

按 `PATCH-M8-4-REQUIREMENTS-CLICK-01` 追加四组有限真实 UI 覆盖：十分类选择及111篇指引逐一点击/需求引用；193原需求编号及名称搜索；70共用原人工页面入口；九模块代表的原空表单打开、字段实际聚焦、原取消。新增员工表单额外核对默认销售、两家可用门店均不默认勾选。统计读取沿用70页面组，不猜填原单、金额、来源编号、不提交业务；采购前置供应商/车型/物资由独立夹具作者以原服务最小预置。全部组保留原业务全行摘要零写和本轮 API 非 GET 写请求门禁，逐项 checkpoint.json 保存 passed/failed/unexecuted、动作范围、真实可见结果与截图，未完成或失败不通过。

新模块暴露 `REQUIREMENT_SCENARIOS` 四项三元组清单（每项 name/callable/timeout，期限依次180、130、300、180秒）及同步 `finalize_requirement_report(manifest, browser_report)`，主代理接线原隔离 runner。源清单与本次 `source_root/web/workflow-guides.json` 核对源文档哈希、193/111完整合同、70目标集合；检查点与汇总保留发布指引字节哈希并拒绝跨指纹复用。外部 requirements-coverage.json 逐项区分搜索、指引、共享页面、部分空表单、真实业务子动作和仍未实测完整流程；HK-098与HK-002仅在对应原关键组真实 passed 后记录客户新增/历史唯一、第一接待分派确认子动作，HK-117/HK-126仅记真实 Cookie 只读补充核对。所有 full_flow_tested/business_acceptance 保持 false，入口/表单覆盖不冒充193业务验收。

本轮静态检查：两脚本 AST 通过，新模块纯元数据核对与当前发布指引合同通过（未导入 app、未启动服务或浏览器）。新模块源码 SHA256 `53a8305f6749816cb8852f6393ff64675bac447efbb7b66fd4b1c7dbf5da41ae`；发布指引 SHA256 `8b0720e079f9af77f26306b10d902900302b12bcaefac5be313c1552186fc9c3`。实际13组联合验证由主代理下一轮执行，当前新增覆盖仍为未运行。

Fresh06 已完整停止：13组中11组通过，十分类/111篇指引、193项搜索、九个原空表单均实测通过；70页面组实际36项通过后在 visit-activity 停止，剩余33项未执行。失败原件保留在该轮外部证据，不以本次修订覆盖。只读定位确认真实 GET200、统计标题/图表/实际记录已显示，成功分支以 `.notice.error` 展示 complete=false 的来源不足保护提示；旧断言把 CSS 展示样式误当读取失败。另一慢查询退出503由主代理独立处理，本代理不修改其守卫。

测试分类最小修正仅适用于已核对源码合同的 visit-activity、vehicle-period、procurement-cohort、warehouse-period。每次实际人工入口点击前临时观察对应同源 Cookie 原GET，只保留真实200的 complete/transit_complete/closing_complete布尔值和来源差异计数/说明摘要，不保存原行、编号、凭据或完整JSON。成功来源提示须与真实字段逐字匹配；完整性为false才记录 source_incomplete_warning。继续拒绝 errorpage、role=alert读取错误、其他 notice.error、非2xx API、非唯一本轮响应及原业务写入。页面显示通过仅属于page_ui层，来源警示写入逐项需求汇总，data_source_acceptance/business_acceptance/full_flow_tested仍false；不补造到店或库存来源。

此修订 AST 通过，requirements_click.py SHA256 `603bda38b674e21291bbcaed361e514a761fd35bffd3fc13141bc5a3efa5f318`。未启动应用或重跑浏览器，尚待主代理 Fresh07 同指纹完整13组联合验证。

Fresh07 最终集成证据已只读核对：`C:/Users/tiefu/.codex/HuaKangOS-agent-validation/runtime-v1/browser-click/automatic-20260930-07/evidence/browser-click-report.json` 与 `run-summary.json` 一致，注册/执行/通过13/13、失败0、complete=true、passed=true、scenario_exit_code=0。真实 Chrome154.0.8037.59、Playwright1.56.0、native_transport=true；同次共1128个记录动作、659次原生点击、4个原生键盘动作，3项Cookie只读API补充核对另计，观察到7个原生SSE响应。全部场景page_errors和external_attempts为空，17次合成模型请求，真实模型调用0、blocked_external_attempts=0。此前各轮失败与适配理由原样保留，不拼接历史片段充作本次通过。

原安全组实际观察会话Cookie HttpOnly/SameSite=Strict、CSRF Cookie非HttpOnly；页面原POST携带真实Cookie与CSRF、原SSE200、同源CSP，缺CSRF写请求及伪造身份头分别403。HTTP隔离实例Cookie secure=false，本组不冒充生产HTTPS验收。跟进组保留首次revoke409“计划已更新，请读取最新版本后修改”，grant/原业务不变且UI显示事项变化后，仅一轮员工核对并重新两次确认，最终原请求200、数据库revoked；报告记covered_protected_conflict，非后台重放或抹去冲突。

`requirements-coverage.json` 与四组检查点一致：193项原需求编号/名称检索、111篇发布指引、70个共用人工目标页面、9个原空表单打开/聚焦/取消均实际完整通过；70页面组原业务摘要不变。逐项193个help_route_tested/page_ui_tested来自这些真实共享入口证据，仍只有HK-098新增客户确认与历史无重复、HK-002第一接待分派卡确认两个真实业务子动作，第二依赖卡只准备；HK-117/HK-126是Cookie GET与数据库对照补充，不算业务点击。完整业务流程实测0，business_acceptance/full_flow_tested/data_source_acceptance均false。

四项保守来源警示同次真实Cookie GET200/布尔字段/可见文案核对通过并留在checkpoint及逐项汇总：visit-activity complete=false、来源差异6；vehicle-period complete=false/transit_complete=true、未核对代次60；warehouse-period complete=false/closing_complete=false、库位覆盖缺口4；procurement-cohort complete=false、采购来源差异4。页面渲染通过不表示这些来源完整，不补造实际到店、原始入库、库位启用或逐行订货事实，不展示/猜填完整合计。

主代理登记本次生产源码SHA256 `0ade3e7a781de93a963bc341242488abf386ee7d68bed55178838cc815e22f7a`，点击脚本集合SHA256 `e4265ebdc23ce75c2d1767e272da5bc37167221f380d0c14d4857735eacff921`。本代理仅更新本任务记录，未修改生产、测试脚本、CI、计划或主任务页，未再次执行测试。自动报告人工体验/文案评分仍pending、员工效率not_measured；659次点击不等于员工效率提升20%。193/111完整业务验收、101/283真实模型、PostgreSQL、员工试用、附件/故障恢复及生产门槛仍需各自真实环境证据，不由本轮导航/空表单/合成模型结果替代，也不据此登记原M8全面done/released或启用生产开关。

**随后主代理人工审阅结果（独立证据）**：manual02与automatic07生产/脚本指纹完全相同，实际IAB销售登录、三宽度、手机准备客户→单次确认→刷新→原客户页→退出已执行，数据库对应客户恰一条。六项人工评分3/3/3/4/3/3，详见 `V/browser-click/manual-20260930-02/evidence/manual-review.json` 和v2浏览器检查点；自动报告自身的pending保持当时事实，不改写原件。开发者审阅不替代员工试用或效率。
