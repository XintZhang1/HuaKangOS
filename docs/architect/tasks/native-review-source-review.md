# 原生人工复核外部草案：独立源码审阅

**任务与负责人**：`native-review-source-review`；M8.1 主任务 `/root` 的只读子审阅，`/root/closed_writer_audit`。2026-10-01。

**目标**：核对外部 `V/browser-click/launches/native-review-draft.py` 是否能在唯一同轮 full53、`awaiting_external_stop` 的保留实例上进行真实原页面只读操作。只提交本页及会话反馈，不改该草案、生产源码、测试、runner 或共享进度，不执行草案/preflight/helper、不启动 app/浏览器，不执行 SQL，不读取私有密码、真实 `.env` 或数据库。

**当前结论**：注册/报告字段、主要 helper 签名及 M01–M22 原路径可静态对齐；初版材料 mirror 别名及车辆详情 body 错位已由作者在外部草案修正并独立复核。当前仍需补终局后台网络证据门禁；HK071 私有密码阶段建议再与父 checkpoint 的公开阶段标识精确相等。本文没有动态运行或业务通过结论，不能凭静态检查标记 22 站已观察或 193 项验收。

## 快照与只读依据

- 初次读取实际为 417 行，SHA256 `50c31ba46221b6d24643d6c99486d4383ae1218fdaf8ac8e2b4c9caef13810c8`，不是派任务时的 323 行。
- 作者只修 mirror 别名与 M22 车辆嵌套字段后，独立复核草案为 418 行，SHA256 `68c27e1fe32d4ae636fa7cbb7bb53629853c094cb750a302a21235d427563434`。下文草案行号对应此快照；后续作者修改应追加新指纹，不覆盖本轮事实。
- 当前 HEAD `8993ca8c755194a42a48e7323fe355e80c6bf9ae` 加工作树。`tests/browser_click/run.py` SHA256 `8f40932b9a3bbfbc3122a0ee20a92883684e0fd99413f11bf2a549d0fcfd5cad`；`scenarios.py` SHA256 `d582050454c57af8a687105b154e8785b279481a7f9a4dd525a8d55bf54e28bd`。
- 沿已读 AGENTS 当前隔离浏览器授权、DSH Architect、M8.1 及 `manual-193-stations.md`/`hk099-native-review-preflight.md`，只补核本任务实际契约，不从旧结果继承成绩，不改变四个生产默认关闭开关。
- 静态解析当前 SCRIPT_FILES 全部 45 个受控文件，其中 42 个 Python 源码 AST 可解析、无缺文件。用有限 AST 的常量/名字/tuple 拼接读取注册，不 import scripts/app，不运行业务函数。
- 只读公开合成旧样例 `business-reports-complete-source-20261001-07/evidence/` 中 browser report、provenance 与指定 checkpoint。该轮是 selected 且最后业务场景失败；不作为当前 full53 通过证据。其不存在 requirements-coverage.json 是 selected 合同，不是草案应降级的理由。

## full53 preflight、注册与来源字段

草案 33–66 要求 evidence/run/runtime/source 同一外部根、manifest schema=1/synthetic=true、数据库与凭据路径仍在本 run runtime；origin 为 loopback HTTP 无用户/密码；provenance 的 source/script before=current=after、changed_paths 为空且每个镜像文件字节匹配。字段名称与 run.py:244–254/271–275 一致。provenance.source_root 是原源码来源，manifest.source_root 是本轮复制后的 source；不能把两者强行相等。

scenarios.py:62–73/756–766 静态注册结果是 **53 个唯一三元组** `(name, function, timeout_seconds)`：9 原助手、4 需求 UI、40 业务。草案 71 的 `{name for name,_,_ in SCENARIOS}` 及 73 的 `for name,function,_ in BUSINESS_SCENARIOS` 均正确。不是二元组，也不是 53 个业务 checkpoint。`function.__module__+'.py'` 是本轮相应业务脚本名。

草案 54–62 的 complete/passed/full_registered_suite_complete、scope=full_registered、registered/executed/passed_count=53、failed=0、53 unique actual/expected/all_registered 名称及每项 actions>0，与 scenarios.py:828–834/876–886 的正式字段一致。requirements-coverage 的 exact counts 为 193/111/70/9，完整且 passed，business_acceptance=false；requirements_click.py:556–585 同样产生这四键，不用 selected 场景的缺文件替代此门禁。

草案 63–66 的 scenario_exit_code=0、post_test_review.phase=awaiting_external_stop、automatic_evidence_preserved=true、stop-requested 不存在，与 run.py:306–320 一致。此时 runner 仍等待原服务退出，provider 最终 gate 尚未完成；草案 summary 保持 preview/complete=false/provider_final_gate=pending 正确。它只另开浏览器 context，不能新建服务、库或拼接三轮 selected。

40 个 parent checkpoint 的 scenario/complete/passed/requirements/acceptance_checks 与 `sales_order_business.checkpoint_evidence:111–116` 一致；source_contract_sha256、candidate_sha256、provenance、mirror 按对应真实字段检查。browser report.scenarios[] 没有 requirements；business-acceptance-report 的 checks 属于 requirements[].checks[]，草案未误用这些层级。

## 已确认并修正的两个问题

1. **材料 mirror 的已存在别名（原84–86必阻断）**：material_business.py:268–275 使用 `mirror={'sha256':SHA(provenance.json),source_sha256,script_sha256}`；reports-complete-source 用 `provenance_sha256`。旧07 两个公开 checkpoint 的该值都是 `ac3a3ffdd1789410628229dd62a59d953ab0c5e9f1cfff5f9fa6f82861b37c4d`，等于该轮 provenance 文件 SHA。原草案对 sha256 访问 provenance['sha256'] 必然 KeyError。现84–87 只允许 sha256/provenance_sha256/source_sha256/script_sha256 四种键，前两者比较文件 SHA，后两者比较对应原 provenance 字段，未知键拒绝；已独立确认最窄修正。
2. **M22 车辆详情返回层级**：`app/customer_service_api.py:163–168` 原 GET 是 `{'vehicle':..., 'observations':..., 'effective_observations':...}`；customer_reminders_business.py 也读 body.vehicle。原草案341 使用顶层 body.id/customer_id；现342 改为 body.vehicle.id/customer_id，与原 API 一致。未改后端或测试求适配。

## helper 签名与原动作边界

下列均与当前源码实际定义对齐；包括关键词参数，没有发现漏参数/多参数的静态阻断。CR/REPORT/SRC 的原导航 helper 都用实际原页面响应，不用 fetch/Cookie bridge；SQL 字符串在本文仅作为源码阅读，未执行。

| 草案调用 | 原 helper 签名/位置 |
| --- | --- |
| 新 context 与真实登录/切店 | SYS.fresh_identity(e,context,contexts):322；native_login(e,account,password,*,first=False):330；switch_store(e,store_id,account,role):228 |
| 仓储正页面 | INV.stock_read(e,item_id,store,role,*,search=True):266 |
| 三店来源报表 | SRC.open_report(e,sid,key,family,period):817；read_metadata(e,response,sid,parameters):807；SRC.M 是原 material_business，choose 沿原物资/仓库显式选择 |
| 原报表/表格/图/钻取 | REPORT.open_report(e,key,route,period):283；unique_original(data,key,case_id):304；verify_table(e,data,key,family):325；graph(e,data,chart_id):430；drill_original(e,data,key,row,family,case):466 |
| 当前同店应收 oracle | AR.current_oracle(e):908；report_match(data,oracle):1065；financial_kpi(e,data,oracle,period):1079 |
| 原有限审计 | AUD.audit_open(e,account,store_id,role):521；audit_filter(e,account,store_id,role,entity_type,entity_id=None):530；locate_audit_page(e,account,store_id,role,body,audit_id,*,entity_type,entity_id):564 |
| 当前原页面/服务摘要 | CR.read_page(e,route,title,path):188；history(e,vehicle_id):615 |
| 证据方法 | Evidence(manifest,secrets,name)；action(kind,target,**details)、observe(label,value)、key(selector,key)、snapshot(label)、business_snapshot(label)、business_unchanged(before,label)、finish()；用法与当前定义相符 |

readonly_network 189–195 安装在每个原登录 context 上，只有 login_allowed 临时允许对 **同一 origin 的 /api/auth/login POST**；其它非 GET/HEAD/OPTIONS 均 abort 并留证。route.fallback 继续触发 Evidence.attach 的既有外域 guard。SYS.native_login 原 helper保护原业务行、只允许同一员工的 Session 及唯一 login audit 追加；正常切店通过原 UI GET /auth/me 核本人/当前店岗位，不写 UserStore 或权限回执。登录不是全库零写，草案 limits 已明确说明。

HK071 193–235 从同轮父观察的私有文件指针与 manager account 加载身份，路径只准本 runtime 的 system-management-accounts-*；公开 parent 的 employee_id/current_store_roles/current_access_version 与当前本人/成员关系重核，password 不进入证据，secrets 共用并追加脱敏词。**还应在211 加 account.current_password_stage == s.current_password_stage**，当前仅验证 stage key 存在。只核公开阶段标识，不读取/打印密码，不默认旧 first/final，也不尝试其它密码。

third_admin 使用原 admin 的独立 context，按 reports-complete-source.report_sources.store_id 原 UI切第三店。操作只读原报表与原单，无临时给 finance/inventory/service 扩第三店权、无恢复权限 POST、无跨店SQL修改；原 admin 登录记录仍是明确有限合法写。

## M01–M22 精确原路径与 body

来源全部取本轮成功 parent 的 report_sources 或该 parent 原 observations，不硬编码旧 run 的业务编号。M01–M03 按 corrections[].requirement 找唯一原来源；M16 取唯一原 plan/session/succeeded+pending 两卡及 revoked Grant，不准备/确认任何卡。标题来自原 Case/title 或当前既定 h1；无原返回按钮时记录 pending，不造导航成功。

| 站点 | 实际 hash 路由 | 目标原 GET/body |
| --- | --- | --- |
| M01–03 | business-finance-order/{finance_case_id} | /api/business-finance/orders/{id}；body.case 的 id/version；原资金更正声明/原 source_case_id 按原按钮读取，不再次 execute |
| M04 | warehouse-item/{first_store_item_id} | /api/warehouse/items/{id}/stock；原同店物资、库存/占额/位置/不可变流水由 INV.stock_read 核当前值，不固定早期数量 |
| M05 | procurement-cohort | /api/inventory-reports/procurement；原第三店+period，采购 cohort 三表及 procurement_cohort_0 图；同原 purchase_case 钻取 |
| M06 | warehouse-period | /api/inventory-reports/warehouses；原第三店+period，item_id/warehouse_id 在原控件逐一选明确源；精确 filters、三表及 warehouse_period_closing，未知 opening 保持 complete=false/closing_complete=true |
| M07 | table/receivables | /api/flow/analytics；HK157 原 checkpoint.report.period；AR.current_oracle/financial_kpi 对整个当前一店相同表范围，不仅四张新单 |
| M08 | sales-quotes/{sales_case_id} | /api/sales-quotes/orders/{id}；同应收表原行先 drill flow，再原领域按钮，顶层原 id/version |
| M09 | service-orders/{associated_service_case_id} | /api/service-orders/{id}；同应收原行→同原单→原服务明细 |
| M10 | repair-orders/{repair_case_id} | /api/repair-orders/{id}；同应收原行→原维修，顶层 id/version |
| M11 | retail/{retail_case_id} | /api/retail/orders/{id}；同应收原行→原精品，顶层 id/version |
| M12 | addon-orders/{addon_case_id} | /api/addon-orders/{id}；h1 销售加装明细，原安装/VIN source 保留 |
| M13 | service-orders/{agency_case_id} | /api/service-orders/{id}；原代办本人 service 可读 |
| M14 | service-orders/{customer_other_case_id} | /api/service-orders/{id}；原其它客户服务本人 finance 可读 |
| M15 | vehicle-income/{manufacturer_income_case_id} | /api/vehicle-income/{id}；原厂家/供应商收入，与客户收入分开 |
| M16 | business-assistant | /api/business-assistant/workspace 与原 /sessions/{session_id}；仅历史/refresh/filter、原 succeeded 与 pending 卡，原同会话/plan/grant行摘要前后相等 |
| M17 | audit | /api/audit；始终 entity_type=typed_master + 原 supplier_id；source_audit_ids 指定原日志，原 finite offset/page 与同筛选查找，不扩大为所有日志 |
| M18 | membership/{customer_id} | /api/membership/members?customer_id={id}；原 body.customer；active/void period、原卡ID来自两个原 parent，人工事实与体验仍 pending |
| M19 | benefits/{customer_id} | /api/group/benefits/members?customer_id={id}；body.customer/wallets；四种独立原 wallet_id 对当前 member/版本/余额/source 做核对 |
| M20 | retail/{retail_case_id} | /api/retail/orders/{id}；原精品安装及客户接收 source event 保留 |
| M21 | customer-service/{maintenance_case_id} | /api/customer-service/cases/{id}；原 subtype 标题与原编号、id/version/assignee；不联系客户或办结提醒 |
| M22 | customer-vehicles/{customer_vehicle_id} | /api/customer-service/vehicles/{id} 的 body.vehicle；随后原 /vehicles/{id}/history，原 CV/customer 关联保留 |

M06 外层 expect_response 等 exact 期间+两个 filters，因此初次无筛选 GET 不会满足；两个原 selector 操作后的最终响应才满足。SRC.read_metadata 进一步核 exact query（忽略空参数），没有仅前端改标签冒充后端筛选。M17 原 locate_audit_page 保留同有限 type/id，admin 原允许本店与 store0 的范围；不是根据无限日志内容猜 row。M22 本次只读车辆/历史并不代替 HK099 真实跨午夜验证。

M18 的 card_source 与 active_period_id/period_void_id 已带入 matrix，但草案只检查 customer；未把那些事实另作当前 body 断言或人工评分。当前 rubric/criteria/business_accepted 均 pending/false，不能据此称这些原卡/会期已独立验证。此项属于证据覆盖待补，不是页面运行必阻断；不得把早期父记录全行照搬当当前会期。

## 尚需修正：终局后台 GET/网络证据

418 行快照中，388–389 每站 gather 当时 response_jobs 快照并检查 forbidden/page_errors/external_requests/5xx；393 校验原自动文件不变；**394 提前把 summary 标成 22_readonly_paths_observed**；395–399 再关闭所有 contexts/seed/browser；404 `e.finish()` 最后再 gather。此最后阶段没有再次检查上述网络门禁或 pending 数。

Evidence.capture_response 对 workspace.json 是 await；capture_request 也 await all_headers；observation_finished 对取消/异常追加 page_errors。此前已登录的多个 context 仍可能产生后台 GET，因此逐站一次 list(response_jobs) 不证明关闭与 finish 后没有晚到响应/采集错误。当前代码可把终局新 error/5xx 保存到 network.json 而 summary 仍标 22 observed，或捕获日志失败只进 page_errors。这是证据收尾缺口，不是已经观察到的产品失败。

最小建议只改外部草案：全部 context 关闭、finish 收集完成后保存最终 page_errors/external_requests/5xx/forbidden/pending_count，并再次执行硬拒绝；只有此终局门禁和 immutable 自动原件校验通过，才把 22 observed 状态写入最终 preview。错误保持 failed，不重试、不追加任意等待或默认通过。不改现有 Evidence/runner/生产冻结源码。

## 交接与验证边界

上述已修及待补问题分别快报给 root 与外部草案作者；只有作者可编辑自己的草案。主任务仍需首先取得唯一同轮、完整稳定的 full53 终局成功并保留原实例，再执行已复核外部脚本；本次不运行 preflight，也不探测服务是否在线。

即使后续 22 路径全部 observed，此 preview 仍不表示六项人工分数通过、全部193需求业务验收、HK099真实日期完成、真实模型101/283、PG/Linux/员工试用或生产发布。导出/下载的审计分支未选择，仍单独 pending；原自动报告不可被补充写入覆盖，provider 最终 gate 待原 runner正常停止后核。

## 427行外部修正的追加复核

作者随后仅修外部草案，独立重新读取与标准库 AST 解析：SHA256 `1125542a5132990871f7a438b3decfb336d778616113a014460435b3907e87fb`，427行；未执行。

211–212 现要求私有账号的公开 current_password_stage 精确等于父 report_sources.current_password_stage，并确认该阶段键存在。本文审阅不打开或打印私有账号文件/密码。406–416 现先 `e.finish()`，再保存 terminal_native_gate 的 pending_capture_jobs/page_errors/external_attempts/server_5xx 和 forbidden_write_attempts，并硬拒绝晚到错误。成功标记现已延到所有 context 关闭及 finish 之后，前版所述普通晚到 GET 证据缺口已修。

该427行快照仍有窄状态问题：395–396 已把 paths_read 设 true；随后398–401任一 context/seed/browser.close 抛异常，403–404 标 failed 并重抛，410–411 却可在无捕获日志异常时因 paths_read/terminal_clean 为 true 又覆盖为22_readonly_paths_observed。CLI仍失败，因此不能读取这个孤立 observed 字段当整个审阅完成。最小建议在成功条件保留已有 failed/failure 状态，另在终局硬门禁再次核 immutable 原自动字节。此问题已报 root 和唯一外部草案作者，不由本审阅者改草案。

## 最新435行终局守卫复核

作者再次最小修正后，最新冻结 SHA256 为 `4ccf21b0e0729319606c3019e29f0fa6b14a8521a58a3a515ce813d5acad4198`，435行。406–417 捕捉 finish_error、终局重核 automatic_unchanged，并把这两项与 pending/网络错误一起保存到 terminal_native_gate；418 只有既有状态不是 failed 时才写 observed，420–424 对不干净终局保持 failed 并拒绝。上一快照的关闭异常状态覆盖和收尾不可变原件复核缺口现已修。此前两种 mirror SHA 别名、M22 body.vehicle 和 HK071 stage 精确比较仍保留。

本次仍为源读审与 AST 检查，未实际执行草案；最新源中未再发现阻止按其既定 full53 awaiting_external_stop 输入调用的确定合同错误。首次实际运行仍需按主任务保持唯一同轮实例与自动原件，并核 CLI/网络终局、页面内容及 pending 人工项；不是预报运行通过或193验收完成。

## 最新444行四字段 provenance 复核

本次独立只读重核 SHA256 `b12f59898327dccc466e2de165664095bd31ade3fb85695ff622c36016d8d921`、444行，标准库 AST 解析成功，未执行。`report_business.py:240–241` 的真实 checkpoint.provenance 是 `{path, sha256, source_sha256, script_sha256}`；旧版把它全部当manifest定位字段会在path处失败。

当前82–92仅有限支持此既有形状：先要求dict，keys必须**恰等**这四项才进入86–89分支；path解析后须同本run的evidence/provenance.json，sha256须等该文件实际字节SHA，source_sha256/script_sha256须分别等已逐文件核过的同轮provenance指纹。后两项属于provenance，不从manifest猜取。另一分支只允许原五个定位键origin/source_root/runtime_root/evidence_root/database_path的子集，并逐项等于manifest；混合形状、缺失异形字段和未知键都拒绝，没有默认通过或宽泛回退。

进一步将新82–92分支逆换为上一版原两行，重建整文件的SHA精确为 `4ccf21b0e0729319606c3019e29f0fa6b14a8521a58a3a515ce813d5acad4198`。因此本轮除此精确分支外原字节完全保持，原53/40注册、full53与覆盖计数、同轮parent、mirror别名、HK071阶段、M22、终局immutable/后台GET/失败状态守卫未弱化。未再发现此四字段接线的确定合同阻断；仍只代表源码审阅。

HK099 Date草案自身eb2f78f2字节未改；其首次实际before会登记此最新依赖SHA，after必须同一SHA，不能跨版本拼接。没有运行before/after、读取密码/数据库或修改任何源/test/runner；原HK099 partial及人工/最终provider门槛保留。
