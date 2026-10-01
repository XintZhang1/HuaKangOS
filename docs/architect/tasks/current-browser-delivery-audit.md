# 当前浏览器交付候选只读审查

**任务 id 与负责人**：`current-browser-delivery-audit`；子审阅者 `visual_reports_current`，向 `/root` 报告。2026-10-02。

**目标与交付结果**：核当前源码候选、测试/CI 注册、原需求来源和原生只读审阅草案的交付边界。本次只新增本页；未执行草案/helper、浏览器、应用、SQL、测试或旧套件，未修改源码、测试、runner、主进度或实施计划。

**最小结论**：本次静态审阅未发现已证实的代码/草案闭环阻断；随后 full16 的 HK071 原 checkpoint 已出现真实源库位不足失败，构成本轮全53通过阻断，详见末节。其余收尾仍待真实终局；本页不预测超时或成功，不计 accepted，不继承 full15。Git 交付尚须包含当前受控新增脚本和其它既定改动，不能仅交当前 HEAD。

## 快照、测试清理与注册

HEAD 为 `8993ca8c755194a42a48e7323fe355e80c6bf9ae` 加当前工作树。审查时 dirty 范围：app 51、web 10、tests 40、CI 1、docs 216、implementation_plan 1；其中 tests 新增未跟踪 24 个受控脚本，docs 未跟踪 213 个。本页创建后的文档计数会增加，不能把该计数当生产指纹。

当前工作区目录及 HEAD 路径清单只保留 `tests/browser_click/`；`.github/workflows/` 只有 `browser-click-checks.yml`，未发现旧 tests 目录或旧套件 CI。当前 CI 直接运行隔离 `tests/browser_click/run.py`，使用 Python 3.13、Playwright 1.56.0 和 Chromium，外置输出，只上传 evidence，不上传合成库/配置/凭据/附件。本次未触发远端 CI，不以该文件存在宣称 Linux 已通过。

有限 AST 解析（不 import 应用/脚本）核得 53 个唯一注册三元组：9 助手/安全 + 4 需求 UI 覆盖 + 40 业务场景。`SCRIPT_FILES` 为 45 个，无缺文件；其中 42 个 Python 文件 AST 可读。53/40/45 是注册数量，不是执行或接受成绩。

full16 原 provenance：生产 `76862a922e57832b92d6f9e68ec0804e2182a992da0cd3b150297487532a525b`，脚本 `66a265e65333b1f688f7dd74cb5de32acbb7a249059d1140c8239b7ca39502a4`，`snapshot_stable=true`。逐文件只读摘要核对 635 个生产镜像文件、45 个脚本与当前工作树一致，无错配。未读取 credentials、真实 `.env`、数据库或附件。

## 原需求与默认开关

`docs/原始功能需求表.docx` 实际 SHA-256 为 `ddf297678e5d6d35e1dbfffc5c232c3d56748934eb22b58bbb9f9d5343689aae`；与 requirements_manifest 的 source_sha256 和 catalog 的 source_docx_sha256 一致。manifest 实际摘要 `19840f4fc5fd816d94ea35a4602a31bde4674105e44621eeb4cfe42bdad27a1f` 与 catalog.source_manifest_sha256 一致。两清单均 193 项且 ID 集合相同；manifest 仍为 10 模块、111 工作流、70 共用页面，catalog 的 193 来源审阅/check 合同不冒充执行成绩。catalog 实际摘要 `eeea5ea2088ac932fe9f725ef1d4bd68073507bd23f695df360ef0036ba8a3ff`。

`app/config.py` 的 `flag` 默认 false；HOME、RUNTIME、FOLLOWUP、NOTIFICATIONS 四新开关都没有传入 true 默认值。隔离 fixture 显式开启只服务本轮合成实例，不能写成生产启用；同时使用外部 SQLite、synthetic provider、阻外网、空模型密钥、legacy write=false、structure_only 文件校验。原 PG/Linux 独立平台、101/283 真实模型、真实员工/IME/效率、附件/ClamAV、真实款物签字、生产 HTTPS/安全 Cookie/Host 门槛保留。

## native-review-draft.py 来源与闭环

外部草案 `V/browser-click/launches/native-review-draft.py` 当前 444 行，AST 可读，SHA-256 `b12f59898327dccc466e2de165664095bd31ade3fb85695ff622c36016d8d921`。本次仅阅读，不执行或修改。

来源入口要求唯一外部 evidence/run/runtime/source、synthetic=true、127.0.0.1 原服务、逐文件稳定镜像、完整同轮 53 名称与 passed/actions、193/111/70/9 覆盖、原 scenario_exit_code=0 和 `awaiting_external_stop` retained 服务。只导入该轮已核 scripts；不拼 selected、不另起服务/库。40 个业务父 checkpoint 要求 complete/passed，检查原 requirements/check evidence 和实际 candidate/catalog 指纹；HK099 的 partial_requirements 不被循环冒充完整通过。

父 provenance 精确四字段格式按原 provenance 路径/实际字节/生产和脚本摘要核对；其它只允许 manifest 的 origin/source/runtime/evidence/database 字段子集且逐值一致。mirror 只允许 sha256/provenance_sha256/source_sha256/script_sha256，两种 provenance 字节摘要别名与源码实际合同相符，没有误取 manifest 中不存在的生产摘要。

22 站只取成功父/observations 的有限真实原单、客户、车辆、物资、仓库、钱包、会话/卡/plan/grant 来源；即时重核原 GET、当前 CAS、Cookie、当前门店岗位与 SELECT。HK071 私有来源限定本 runtime 指针，current_password_stage 与父公开代次相等；第三店只读使用源中真实 store_id 的 admin，不给已恢复权限的员工补授权。正常登录 Audit/Session 有原独立守卫，不称全库零写；读路径保留原业务摘要与 M16 有限助手行不变。

context 网络只允许 GET/HEAD/OPTIONS，以及原登录窗口的精确 `/api/auth/login` POST；其余写入阻止并留证，既有外域 guard 仍生效。实际三宽 snapshot/Tab/Escape/展开/有限原单跳转只能证明实际走过的读取路径；CSV/导出分支未选择、六 rubric 和业务 criteria 仍 pending，business_accepted=false。root 须在实际执行后看图及判定，不能靠草案写成 22 站或 193 体验通过。

终局先关闭 context/browser，再调用 `Evidence.finish` 的顺序没有已证实静态错误：当前 `scenarios.py:399` 的 finish 只 gather 已捕获网络任务并保存 actions/network/observations，不访问 page。每站此前也 drain response_jobs；终局再核 finish_error、pending jobs、pageerror、外网、被拒写、5xx 和自动原件摘要。任何真实捕获错误会记 failed，原失败不会被最终 observed 覆盖；不能凭浏览器已关猜测 finish 必失败，也不提前保证实际收尾通过。

## 当前位置与下一步

full16 由 root 运行，本页不改或停止。外层 scenarios subprocess 超时为 3600 秒，CI 作业为 75 分钟；53 场景扩大后的实际预算须由本轮终局证明，尚无实际 timeout，不预测为失败。root 告知启动约 UTC 19:11、19:37 已 37/37，是进度而非本审阅者新的终局通过证据。

root 取得同轮原自动全53通过及 retained 服务后，才可选择执行该草案；full16 目前已不满足该 passed 前置，不能给本轮强行执行或继承。草案 preview 仍保留 complete=false/provider_final_gate=pending，原服务正常 stop 后还须核 runner 退出码/provider 外网0。HK099 真实 Date 到期需另以同实例实际 D→D+1、原授权/本店事实不改留证，不能调时钟、修改日期或回填；原 partial 留存。后续源码/脚本改变需 fresh 证据，不继承本次审查或 full15 阅图成绩。

## full16 HK071 实际失败的只读诊断

root 通知第51场景 HK071 失败，本审阅者随即只读本轮 `inventory-store-scope-hk071/business-checkpoint.json` 与前序父 checkpoint。当前 HK071 `complete=false/passed=false`，错误为“原明确源位当前不足500或现场盘点围栏；不换数量/造余额”。失败发生 `inventory_scope_business.py:529` 的 `sufficient`，在原移库创建前；未降低数量、改源位、跳过围栏、执行 SQL 或修改本轮源码/脚本/报告。

原 `initial_local_nonempty` 的实际 API 读数为 item9、version51，总量2250 milli、可用2250、价值2250分；明确源库位2的 balance1/version15只有250 milli/250分，目标库位3的 balance4有2000 milli/2000分。retail、addon、holds、transit、approved_return、count 均为0，因此已证实的是源位250不足500，不是总量短缺或现场盘点围栏。

以下均来自本轮原 API entries 和已通过父的有限 case 来源，数量与价值在这些条目中数值一致：

| 父原件 | 本店源库位2的原条目/原收发 | 净数量变化 milli | 源位余额 milli |
| --- | --- | ---: | ---: |
| materials 收尾 | 原采购94、盘点95/97、店内移库96；entries1/3/5/6/7/13 | 5250 | 5250 |
| 自费维修100 | entries14/15/16；stock22/23/24 | -1250 | 4000 |
| 会员后继零售135 | entry18；stock26 | -1000 | 3000 |
| 会员积分等级零售164 | entry34；stock42 | -1000 | 2000 |
| 保养包维修179 | entry35；stock43 | -1000 | 1000 |
| 跨店材料185 | entries36/39；stock44/47 | -750 | 250 |

本轮失败 cleanup 的原 `failed_run_explicit_role_restoration` 证明员工19已恢复仅店1 manager、group=false、access_version3，原目标会话由1归0。本诊断不执行任何恢复动作。

后续 fresh 轮可复用 `receivables_business.py:272` 的既有 `material_precondition` 原 UI 独立采购流程补足事实：参数从已通过 materials.source_preconditions 取 supplier2（原 vehicle_purchase HK171）、flow_account1（原 HK021 实付账户）；primary 取 item9/warehouse2，原 source_location2，fixture 使用 manifest.business_fixtures.vehicle_purchase，并生成新 token。调用前须读取这些行的当前版本/启用/同店状态，保留原同轮父来源与脚本指纹检查；不得借用精品父 item13 或改源位到3。

该既有流程按1.000实际单位、10.00元单价申请独立采购，主管独立批准、财务请款及独立批准、实际付款1000分、库管上传现场证据并向原库位2实收1000 milli，新增批次价值1000分；不直接修改余额。对本次单位“升”应准确展示“1升”，现有 AR 文案硬写“精品一件”，后续复用需同步精确单位说明。保持原 HK071 `AMOUNT=500` 与成本守卫后，预期 item总量/价值2250→3250，源位250→1250后移出500剩750，目标2000→2500，原位在途闭环且移库前后总量/价值均3250。原条目保留不动；这些是后续修复参数和预期，不是执行结果。

**实际阻塞**：full16 HK071 源位不足的真实失败；本轮全53通过条件不满足。其余未执行条件：full16 原 runner 终局、fresh 修复后的同指纹全53、原生只读草案实际运行及逐图人工判断、HK099 真正截止日、原独立环境/模型/员工与生产门槛。

## PATCH-M8-4-INVENTORY-ACTUAL-PURCHASE-01 独立续审

2026-10-02，续审由 root 分派，仅阅读登记补丁、full16 冻结 scripts 与当前候选，并追加本页。原 full16 `browser-click-report.json` 已核 `complete=true/passed=false/scope=full_registered`，53个原记录为52 passed/1 failed，唯一失败仍为 HK071；原 run-summary 的 scenario_exit_code=1。root 另确认原 runner 正常收尾、CLI3、provider合成16/真实0/阻外0、关联Python退出。其原失败保留，新修改不继承52通过数。

**静态结论**：未发现确定阻断，候选可在全新外部镜像通过原入口验证。本结论不计动态 passed/accepted，不执行 helper、应用、浏览器、SQL、测试或外网。

对照原 full16 provenance 的635个生产文件均无变化；45个指纹脚本仅 inventory_scope_business.py 和 receivables_business.py 两项变化，没有修改 catalog、注册、runner、CI 或其它 helper。当前摘要：inventory_scope_business.py=`2fbf63ef0c0d59b2b641967c5333317062e650ef60208d6b204eefe8aab654fe`；receivables_business.py=`c08beefbfb92492448042feed9794e3fcf77678031ce0f4ebfb01e3ecee9e76e`。

AR 文件与原冻结 AST 除 `material_precondition` 的点击文案和 reason 两条语句外完全一致；签名、1.000/10.00输入、1000 milli/1000分请求、付款和收货守卫未变。HK071 原函数 AST 仅 sources 与 inventory_scope_business 改变；新增 uuid/AR 导入和AR来源字节检查属于该必要接线。对所有本地脚本作静态 import 图检查，AR没有返回inventory_scope的路径，未发现新增循环导入；未 import 或执行模块。

来源仍使用同轮完整父的有限材料原ID：当前 item、warehouse、两库位与真实启用关系继续核对；当前 supplier 与采购银行账户从 materials.source_preconditions 取得，检查同店启用、supplier原版本、银行类型、原warehouse/source location一致。原私有 `src.account` 保持员工登录用途；新采购资金账户独立保存为 `src.purchase_account`，没有覆盖私有账号或将凭据写入采购证据。原 fixture 的 manager12、inventory14、finance15均为本店原岗位，helper仍以本人登录和原授权接口办理。

采购现在始终在员工门店查询前明确执行，无“缺货才重试”或静默fallback。新原单创建的BT.Guard保护全业务摘要与精确旧行/列；批准保留独立主管与原Task/CAS/事件/回执；合同、请款、独立批准、付款与现场收货保留各自guard和本人原UI。实付核唯一procurement_payment与cash_entry的1000分、out、账户、原凭证及创建人。inline_receive仍对源库位2明确准备1000 milli，逐项CAS、allocation目的/原位置/办理人、唯一receipt、stock_move与entry量值来源全部检查，旧现金/库存/其它原行不能被覆盖删除。

`current_stock` 来自原MAT.item_stock，实际结构为 item/enrollment/balances/stock_moves/entries，含门店总量、库位、不可变流水与收发量值守恒；因此 `src.item=purchased.current_stock.item` 取值正确。采购结果保存到HK071原check证据后先调用未修改的sufficient；员工/两店读取及改权后又调用同一sufficient取得移库baseline。AMOUNT500、明确源位、held、counting围栏、零旧在途检查，以及后续protected_totals、physical_entries、原确认receipt、500实际在途/接收和权限清理都与full16函数AST相同。补货前的历史原件保留，后续移库以补货后的真实stock为基准，不将采购增加量误计为移库变化。

尚待 fresh 实测：原UI采购确实追加1000 milli/1000分到原源位、当前财务投影闭合、后续500移库完整数量成本守恒、当前账号/权限恢复及原全53收尾。HK099真实Date、其它原环境、人工六项体验及193完整接受仍pending。
