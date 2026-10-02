# 浏览器实际点击验证

当前入口是 `run.py`，已注册53个场景、45个指纹文件：9个助手与安全场景、4个目录覆盖场景、40个原业务场景。需求清单对应业主提供的193项原表，包含111条发布指引和70个共用原页面。脚本声明192项完整功能检查；车辆档案HK099保留真正截止日后读取的条件。声明数不是本轮实际通过数。

本轮结果见 `docs/本轮浏览器验收结果.md` 与 `docs/implementation-checkpoints/M8-4-browser-click-193-coverage.md`。automatic-business17在源码76862a92/脚本06d17fb8完整53/53、原CLI0正常结束，192项已登记功能检查通过；15次合成模型、0真实/外网。193项检索、111指引、70共用页面、9代表表单实际完成，仍分别记录目录与业务范围。同实例native v3补充22站原生只读、三宽截图，原自动证据及业务保持。最后维修手机布局补丁仅两展示文件，最终生产2e4b6032/同脚本在新repair-mobile18完成三宽与原表实际横滚定向复查；不写成最终源码重跑完整53。真正Date到期、未测分支、完整人工/员工、原独立环境/模型/生产门槛保留；全部193正式业务接受仍false。新CI配置未在本轮推送或远端运行。旧失败及探针失败保留于v6，不拼成绩。

```powershell
# 全部当前注册场景；默认输出仓库外全新隔离目录。
python tests/browser_click/run.py --browser "C:/Program Files/Google/Chrome/Application/chrome.exe"

# 自动成功后保留同一实例，供实际浏览器查看结果。
python tests/browser_click/run.py --review-after-tests --browser "C:/Program Files/Google/Chrome/Application/chrome.exe"

# 独立交互审阅，不产生自动通过结论。
python tests/browser_click/run.py --serve --browser "C:/Program Files/Google/Chrome/Application/chrome.exe"
```

`--review-after-tests` 必须启动时明确指定，自动失败不会开放窗口。窗口期间 `run-summary.json` 的 `complete/passed` 仍为false。人工审阅另存该实例外部 `evidence/manual-review/`，不改原自动报告或重复已提交业务；在其 `runtime/` 创建 `stop-requested` 文件，正常停止后才继续完整注册、193项目录与最终网络记录门禁。按Ctrl+C中断自动运行或该窗口仍失败。CI默认全自动，不等待人工窗口。

统一标准在 `rubric.json`：显示正确、步骤容易理解、文案简洁、事实清楚、错误恢复和可用性。六项人工评分各至少3分并附具体观察；金额、数量、状态、任务、权限、唯一提交、旧行保护和无5xx/未处理异常另为硬门禁。原生UI点击、自动截图人工看图、补充只读API与数据库核对分别记证。真实模型101/283、PostgreSQL、独立平台、员工效率、真实外部事实及生产发布保留原条件，四生产功能开关默认关闭。

旧测试及套件CI已移出工作区并在仓库外保留可恢复副本；`.github/workflows/browser-click-checks.yml` 是当前唯一验证CI，使用同一入口，只上传 `evidence/`。本轮尚未推送运行的CI不记为成功。

## 历史注册、方法和运行记录

下方记录均按当时的源码、脚本指纹和注册数量阅读，不作为当前成绩。

最新完整结果：automatic-business09注册/执行/通过28/28、退出0，84项完整自动业务核对，5208动作/2560点击，生产1597eb7b/脚本7cc1267d、镜像稳定。页面异常与外部尝试0，16合成/0真实模型。193搜索/111指引/70共用页面/9代表表单仍只是各自UI覆盖，业务人工接受0、full193=false；保险及开票核账候选未注册。详见v5检查点，下文均按各轮原指纹理解。

最新：automatic-business08完整27执行26通过/销售HK017任务页仍加载时脚本查按钮失败，75完整自动check、3局部另列；整体failed。人工02同指纹仅维修/接待显示定向六项通过，不替全部业务体验。结束实例后原等待窄修/独立短审，财务五项已注册，当前28场景automatic-business09完整运行中，无预写新结果。保险、开票/核账候选仍未镜像/注册。下文24/27/23为各阶段历史事实。

2026-10-01：完整automatic-business07同次24/24、71项自动业务核对通过；同指纹人工完成态发现错误等待提示和常驻长说明，失败保留，未人工接受。原193/111/70/9分别属于搜索/指引/原页面/代表表单覆盖，193完整业务false。修复展示并注册销售与维修后继后，当前27场景automatic-business08/人工02运行中，尚无新联合结果；财务与保险候选不在镜像白名单。完整点击有限时限30分钟，CI作业40分钟，未远端运行。下文旧结果按其原指纹留存。

历史注册记录（已被上方新记录取代）：2026-10-01 当时注册23场景：售前、采购、主档、客服、交车/退订、报表、物资、维修和系统管理。最新完整成功仍是历史指纹v3的16/16；21项automatic-business05执行20通过/物资装置失败，整体failed；后续物资9项和系统2项分别选定通过不能拼成一次全套。automatic-business06正在新镜像运行全部23，结果待出。会员及交车后四项是未注册候选，不参与复制或成绩。人工体验、真实环境及193全部业务验收保持pending/false。下文历史记录按各自原指纹理解。

从当前源码建立全新的外部合成实例，再用浏览器真实登录、输入和点击。模型响应是确定性模拟；页面、Cookie、CSRF、CSP、SSE、原业务 API、worker 和数据库均使用当前代码。此入口没有页面桥接或浏览器失败后的替代模式。

automatic-business06现已结束：23项完整执行22通过/维修证据bytes装置失败，退出1；60项自动业务完整check与维修两项局部诊断分别记录，全部accepted0。失败原件保留；只修附件报告metadata及证据原子合并，business-repair01新镜像定向复验中。上一段“结果待出”属该轮启动时记录，本结果取代其现状，不改变193与人工pending。

在独立 Python 环境安装根 `requirements.txt` 和 `playwright==1.56.0`（与本轮实际脚本环境一致）。使用已安装 Chrome 时传 `--browser`；使用 Playwright 固定版本自带浏览器时先执行 `python -m playwright install --with-deps chromium`。浏览器未安装或显式路径无效时直接拒绝，不自动换浏览器。

```powershell
# 自动点击；Windows 默认产物位于 C: 的独立 NTFS 验证根。
python tests/browser_click/run.py --browser "C:/Program Files/Google/Chrome/Application/chrome.exe"

# 为交互式浏览器审阅启动一个独立实例。
python tests/browser_click/run.py --serve --browser "C:/Program Files/Google/Chrome/Application/chrome.exe"

# 业务增量定向验证；只报告所选场景，不声明全套或193项通过。
python tests/browser_click/run.py --scenario sales-presales-hk001-007 --browser "C:/Program Files/Google/Chrome/Application/chrome.exe"
```

`--source` 选择被测源码。`--output` 必须是仓库外尚不存在的新目录；Windows 必须位于 NTFS。默认 Windows 路径为 `C:/Users/tiefu/.codex/HuaKangOS-agent-validation/runtime-v1/browser-click/<UTC时间与随机标识>/`，Linux 为 `$RUNNER_TEMP/huakangos-browser-click/` 或 `/tmp/huakangos-browser-click/`。入口仅复制 `app/`、`web/`、`migrations/`、`requirements.txt` 和 `alembic.ini`，跳过环境文件、数据库、缓存和日志，不读取原预览配置。

`--serve` 会打印真实 URL、manifest 路径和随机合成用户名。密码仅在外部 `runtime/credentials.json`，不会写入日志、manifest 或 CI 产物。按 Ctrl+C，或在该实例外部 `runtime/` 内创建 `stop-requested` 文件，可正常关闭 Web/worker并记录 `stopped=true`；未收到请求的服务退出仍报失败。数据与失败证据保留，不覆盖历史目录。交互启动和正常停止均不产生自动通过结论。

合成指令：`查询本店张姓客户`、`新建客户 浏览器客户Demo`、`浏览器接待计划`、`慢速查询本店张姓客户`、`模拟异常`。客户卡片需要员工点击确认；接待计划使用两个真实合成接待单，开启跟进和每次业务确认分别由员工点击。接待分派沿用原岗位规则，使用合成管理员；普通客户场景使用合成销售。

统一评价标准见 `rubric.json`。自动结果与人工显示、文案和流程判断分别留证。390/768/1440 三种宽度、原业务导航、草稿保护、切店/退出隔离、准备前零业务写入、确认后唯一写入和页面错误都绑定同一次源代码与脚本指纹。自动脚本通过不替代 PostgreSQL、真实模型、HTTPS 部署、员工效率试用或发布验收。

原需求表清单为 `requirements_manifest.json`：10 模块、193 项、111 个发布工作流、70 个共用页面。桌面新提供的表与仓库原表字节一致。除九组关键助手场景外，四组扩展通过原 UI 检索全部需求编号、选择业务分类、打开每条指引、点击所有共用原人工页面，并打开九个代表表单后取消。金额、库存、退款和月结等完整操作没有足够合成前置时留待对应业务验证，不由列表或空表单代替。

每项结果记录于仓库外 `evidence/requirements-coverage.json`，分别显示搜索、指引、页面、代表表单和已实际执行的业务子动作。HK-098 仅验证客户新增与历史唯一性，HK-002 仅验证第一张接待分派确认；夹具预先创建原单不计员工点击实测。会员和套餐详情的补充 Cookie GET 单独计数。清单自身始终标记 `unexecuted`，没有历史成绩继承或 193 项完整业务验收结论。

每次输出包含 `source/`（被测生产镜像）、`scripts/`（执行脚本）、`runtime/`（合成数据与凭据）、`evidence/`（报告、截图和日志）与 `manifest.json`（无密码的实例信息）。初始化应用前核对源码与脚本复制前、复制内容、复制后三份逐文件指纹；发现并行修改则保留 `snapshot_stable=false` 证据并拒绝启动。CI 只上传 `evidence/`，不上传凭据、数据库、配置和附件。

当前追加目标为193项实际业务验收，清单 `business_acceptance_catalog.json` 记录每项真正通过所需UI/API/后端事实；清单本身不保存执行成绩。先以原接待/意向操作推进HK-001—HK-007，随机接待、主管和第二销售账号仅作为身份前置，业务结果由UI生成。文案依据 `docs/文案标准.md`，个人风格检索无可用样本时不声称取得个人档案。

全部193源合同已审阅；注册新增 `vehicle-purchase-hk171-177-178-026-021-018-029`，覆盖原供应商、品牌车型、仓/库位、两行采购、独立付款、两VIN发运/验收及非空筛选。新增库管/财务仅为随机身份前置；车辆、采购、款项、凭据和入库结果均由可见原表单产生。无占用来源时对应条件分支留未测，结构扫描不称ClamAV或真实实物/银行完成。原注册场景现15组，数量会随已审阅真实链路追加；当次最终成绩以报告完整注册清单及稳定指纹为准。

`--scenario` 可重复指定不同注册场景，重复/未注册名称失败；报告必须标明 `scope=selected`，只验证当前增量，不合成全套通过。未选择时原全部注册场景及193UI覆盖门槛继续强制执行。原UI覆盖、实际业务检查点与完整193业务验收分别记录，未执行项不继承上一轮成绩。

已审阅主档候选 `master-data-hk170-172-173-174-175-176-179-180-181-182-183-184-185-186-187` 接入同一入口，当前注册16组。七类字典分别维护两店同名项；保险公司、班组、作业/代办项目、材料品牌/分类/专用仓库与零库存物资关联均走原表单、启停及有效引用守卫。主档配置不制造库存或现金结果，后台金额/数量使用原精确换算。分项自动检查、人工体验与完整业务仍分别记录；脚本存在及注册不等于执行通过。

客户服务候选 `customer-service-hk098-107-108-109` 已短审并接入，当前注册17组。原客户新增/修改、同号明确另建、撤回联系及独立主管恢复；同一实际客户分别办理咨询/投诉/救援原单、本人接手、两次跟进与有据结案。客户车辆/两次日期里程及本店历史仅作为HK099 partial前置，不向汇总提交该项完整通过。合成服务日期明确使用fixture业务时区Asia/Shanghai。首次实际点击待执行，登记不等于运行通过。

客户Fresh03同次4/4自动检查通过（selected、退出0），原拒绝仅新增精确真实refusal、各客服办理仅新增精确原审计，全部旧行及无关业务保持；Fresh01/02装置对原拒绝/审计漏计的失败证据保留。

销售交付和独立退订两场景、同轮11项报表场景已短审接入。依赖顺序售前→采购→销售→退订→报表；只取当前runner及通过的固定checkpoint有限真实ID。原报价版本/合同下载字节及签回、本人岗位实际收款/检查/出库/提车和原款退款均分别核对。Fresh05同次所选5/5退出0、实际30项自动检查，HK136严格核对真实intent→converted与订单/车型来源。先前失败原件保留，原拒绝、下载审计及展开折叠的装置适配不改产品守卫。该轮源码5394dedb…、脚本7fbb2c7b…，不与后续导出事务修复指纹混合。

追加`materials-hk069-045-054-083-070-072-073-051-061`后当前注册21组：原物资零库存启用、预付/分批采购验收、原款实退、正负零盘点及真实期间桥接、分批店内移库与非空库存/补货查询九项；真实业务结果均由原UI产生。必须依赖同次已通过主档及采购checkpoint，不继承demo余额或历史来源；完整运行成绩待新镜像报告。维修预备technician只增加外置随机身份与本店UserStore，fixture不增加工位、维修、库存或现金成果，所有密码沿动态列表脱敏。

IAB原CSV导出间歇503已保留真实失败证据；显式审计GET依赖在SQLite鉴权/报表读取前保留writer，普通GET及PG沿原路径，不重试。无app的外部scratch只用于定位读快照升级并发原因，不计业务成绩；原IAB未记录扩展错误码，不冒称原517。修复后IAB单次原点击成功、后台恰好一条审计；三类导出的全CSV与业务保护仍须同指纹完整注册复验。

退出码：`0` 自动点击完成且证据完整，或交互服务正常被停止；`2` 预检拒绝；`3` 执行、超时、空场景或证据失败。自动通过以 `evidence/run-summary.json` 的 `complete=true` 且 `passed=true` 为准。


2026-10-02 main接续：53项注册保留，脚本白名单46个文件。`pending_ui.py`在当前followup/完整来源报表内复用本轮真实卡和原来源，增加390/768/1440主卡、抽屉焦点/Tab草稿及768单次可信横滚末列；导航先点真实窄屏菜单。security以Chrome原生资源终止和实际Network.loadingFailed证明已断流，再核精确非零after_seq补读及独立Chrome重启。该装置不代表OS网卡/TCP RST演练；不替换fetch/响应/事件，不直接赋scrollLeft或改CSS。

main-resume28同轮selected10/10、CLI0，完整报告与provider17/0/0在外部证据根；源码cf34fb8d、脚本2e5eb6e6。原失败、定向通过、GitHub完整53和正式193接受分别记录，详见`docs/implementation-checkpoints/M8-1-main-resume-checkpoint-v1.md`。此定向结果不代表完整53或发布验收。

持续交付的当前增量按`PATCH-M8-1-PREPARATION-PROCESS-CRASH-01`追加`runtime-preparation-process-crash`，原53保留，当前注册54/脚本白名单47。无`--scenario`的完整模式及选择该故障场景时，隔离Web由独立原worker CLI进程执行，合成turn预算180秒；其它定向/`--serve`沿原嵌入worker/60秒。原90秒租约、首次30秒恢复退避和生产配置不改。故障点只在已提交真实卡后中断登记的隔离PID，不重发聊天、伪造回执、改时钟或SQL状态；子进程provider账本均汇总。新场景动态结果另登记，文件存在不等于恢复通过，原53 CI成绩不继承给新54。

2026-10-02 在途停止增量按PATCH-M8-1-INFLIGHT-STOP-01注册第55场；原54顺序和名称保留。定向此场沿原embedded worker，完整55沿原process模式（先完成提交后崩溃/重启，再测原UI停止）；两个执行面分别记录，不冒充完整独立worker部署演练。生产不改，合成provider只新cancel_前缀在inspect成功后的第二轮准备响应设置有界阶段。必须原点击停止200、真实stop_requested后释放并记录returned_after_stop，最终原Run取消且无卡/准备WorkItem/确认/原业务变化；heartbeat先中断单记，不能算迟到响应已返回。新增代码实施/审阅和动态结果分别登记，不因注册即记通过。

2026-10-02 虚拟候选当前注册57/48文件，新增本组自然原业务409及真实native提交后结果丢失两个故障。原UI逐张confirm而非后端batch API：真实A成功、Bfailed/uncertain后暂停C，C pending全行保持不写成skipped；后端显式skipped列表另待测。33优化前在途停止单场完整pass（4.78秒、11动作5点击、合成2/真实外部0、实际CLI0），source cf34fb8d/script afe419f2；停止前原getRun版本优化后属于新生产候选，旧局部不继承，原stop/crash核心函数保持。当前新增脚本/前端优化动态未计通过，正式发布门槛继续待测。

后续34/35原批量各1/1及36同轮关键6/6已通过生产06109c76/脚本0559ff42；微秒created_at保持同秒不同微秒A/B/C原顺序，停止一次点击使用原最新版本且CAS保留。又补原卡核对按钮接线和会话迟到守卫，既有unknown场直接点击原execution-result GET：客户Master回执族unsupported不意味着失败/未提交/成功恢复，卡仍uncertain、无业务重放。迟到验证只有限暂停精确浏览器GET派发，再continue原请求，由原服务器返回；不fetch/fulfill或改headers/body/响应，切新对话仍须原待卡交接选择。原UI、DB完整行和业务摘要分别核对，新最终指纹结果另记，57注册不代表正式M8.1全部故障或193业务验收。

最终Windows候选635生产/48脚本指纹5d728c524580631c079b9759126ec4a67e4b6b3a8ee5ba73c37d0cbac2987c95/de675618841a4dc4425b8fdc72a2d3bce7b9e2897570e71b1ee75494768e4b4d：sidebar39两场、critical40六场、critical41四场完整通过。两原收尾复用workspace.load，脚本仅等真实sidebar proposal key与原服务器状态，不主动load或猜总数。关键故障两个fresh实例独立重复，原业务零变与批量实际追加分别核；完整57 CI另记，不把定向局拼全量或正式故障验收。

日志独立审计修正：40/41原业务断言绿色但scenarios.log SDK finished()遗留Target closed任务，使独立audit false。仅将runtime_batch迟到GET完整读取等待改为原body()，后续原JSON/断言保持，SDK及原日志不改。新48脚本指纹a51069184869f712f4fc99ceccc0208632f45fbd0d3c909c849e84ca1742aabc、生产仍5d728c52；receipt-observer42受影响两场2/2、实际CLI/服务0未强杀、provider6/0/0且无该遗留异常。最终完整57由当前Git blob的CI另验，不把旧片段改成新全量。
