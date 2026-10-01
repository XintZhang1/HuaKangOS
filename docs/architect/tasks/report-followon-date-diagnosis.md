# report-followon 原预约日期阻断只读诊断

本报告只读核对 automatic-business13 的原 JSON 和冻结源码；未导入 app、执行测试/SQL、启动浏览器、修改时钟、原业务记录或测试源码。结论不是动态通过。原 13 轮证据与已有 7 张保险 PNG 部分审阅保留，所有人工 accepted 仍为 false。

## 结论与最小处理

原 API **不允许未来结束日期**。`app/flow_analytics.py:31–34` 的 `build_analytics` 明确以 `end > today()` 拒绝，并要求开始不晚于结束、跨度不超过 365 天；`app/flow_api.py:404–409,435–439` 的查询与 CSV 导出都调用此函数。因此只删除 `report_followon_business.py:239` 或把 date_to 扩到未来，会把当前的 0-action 脚本阻断变成真实 API 422；不能这样修，也不能改变历史报表口径。

本轮原预约真实保存在上海 **2026-10-02 00:53** 开始，不是假过去日期。优先且最小方案是在真实上海午夜之后，对保留原来源的同实例做独立原 UI 报表补充，或在午夜之后开始全新完整 full53；此时包含 `2026-10-01` 和 `2026-10-02` 的来源期间合法，原 helper 的期间构造及今天守卫都无需放宽。不必等待 00:53：API 限制的是结束**日期**；预约分析选该开始日批次，显示截至当前的真实状态，而不是等待预约时刻后才统计。本轮原预约已经按原动作实际到店、转换并关联完成维修。

同实例补充必须独立留路径、原候选/脚本指纹、实际时间、动作与报告引用，保留 13 轮失败原件；它不能把该已失败 parent 或 original full53 反写成 passed，也不能把片段拼成一次全量通过。新的完整 full53 必须按新 run 自己的全部注册、source/runner/provider 门禁判断。

若必须在预约开始本地日到来之前验证，唯一业务来源办法是使用原员工页面新增**今天合法未来时刻**的真实预约；为保留当前 HK146 原断言，还须使用原到店/转维修动作产生相应原事实，并登记独立有限来源指针。不得把原未来预约改成历史、把 HK146 改为任意 scheduled 行、改日期统计为创建日、截断成今天后忽略原行。已有未来预约仍保存。此方案需要明确新增 HK146 接待来源与原其他六项维修/物资来源的关系，改动比真实午夜后保留唯一原源更大；接近午夜没有足够合法同日时段时，等待真实午夜，不回填。

## 本轮原证据

- evidence 根：`C:/Users/tiefu/.codex/HuaKangOS-agent-validation/runtime-v1/browser-click/automatic-business13/evidence`。
- `provenance.json` SHA256 `a1a91dbed7c2e03c71ad72d754fb88152843d945a7f0a76ae3d18c43f200e856`，source `a58ab81b1274881e238db5175c39a38b1830057074ef03a2bb6fdb9f255b56ec`，script `d27fc3ed67392cac7fef7c6a40bd7ad7370eec0284da5fd3e1ab45d68e2d4084`，snapshot_stable=true。下表相关当前文件 SHA 与原 provenance 对应项一致。
- 原 `report-followon-hk146-147-148-149-150-151-153-155/business-checkpoint.json` SHA256 `fd4ca000b54a9b5a10921ba5fa1e9ff8aa5a0498dfc6747d1a8fd8c59c74ce6e`：complete=false、passed=false、executed/passed_requirements=0、source_preconditions=null、failed_requirement=null，error=`原预约来源还在未来，不能造当前期间`。
- 原 `browser-click-report.json` SHA256 `004ba64b1f99db3a12a48d50bf017701a31324d6412ef16e6bfc714d86b5fad1` 的该 scenario：failed，0.34 秒，actions/clicks/readonly_http_checks=0，page_errors/external_attempts=[]。这是来源预条件拒绝，未真正访问报表 API，不能写 API 实测失败或报表通过。
- 前序 `repair-selfpay-hk031-034-044-049-053-079/business-checkpoint.json` SHA256 `fb0795cc18e8b9a8eaa6af25de7e7026631ba8128324e18fa92f258590ffba69`，complete/passed=true。`/report_sources` 唯一来源为 customer=43、customer_vehicle=1、appointment=1、intake_case=99、repair_case=100、quote=1、allocation=1、payment_link=18、cash=119、material_item=9。
- 精确原指针 `/requirements/0/acceptance_checks/0/evidence/book_event/detail/starts_at` 为 `2026-10-01T16:23:00Z`（上海 10-02 00:23）；`.../reschedule_event/detail/starts_at` 为 `2026-10-01T16:53:00Z`（上海 10-02 00:53）；`.../appointment/starts_at` 为 UTC-naive `2026-10-01 16:53:00.000000`，ends_at 为 `17:53`。该 appointment 快照是改约时 scheduled，最终 converted 状态来自前序后续实际转换断言及 report 来源关联，不把改约快照误写为最终状态。
- 诊断时 clock 工具实际值 `2026-10-01 15:53:54 UTC`，上海 23:53:54；真实午夜尚未发生。这是当前实测时间证据，报告不把稍后日期提前当条件满足。

## 源码日期链与有限修复边界

`report_followon_business.py:198–216` 先读取本 run 五个 complete/passed 前序，客户的 HK099 仍严格保留 local_source_only_not_business_accepted；原接待预约来源来自 **repair-selfpay** 的 `/report_sources`，不是 customer_service 自动种入或 fixture 的历史预约。`repair_business.py:659–684` 员工从原“维修预约与到店”页面创建；665–667 原样明确页面默认时段；686–700 从真实原表单增加半小时并确认改约；703–777 之后使用原到店、错误 VIN 拒绝、唯一转工单动作和守卫。`fixture_server.py:42` 指定 Asia/Shanghai。

`web/serviceintake.js:8–11,43–46` 默认预约 starts=实际 now+1小时、ends=start+1小时，datetime-local 转真实 UTC 提交。因此本轮 23:23 左右创建的默认预约自然落次日本地日，加半小时后为 00:53；没有 fixture 硬编码未来日，也没有从 customer_service 生成过去日期。`service_intake_service.py:138–151,181–223` 拒绝早于当前的预约/改约，允许真实提前到店（arrive 依据状态、岗位任务、VIN、凭据和门禁事实；没有必须等 starts_at 的条件），之后须实际 arrived 且唯一才能 convert。保留这些业务守卫。

`report_followon_business.py:233–239` 收集原维修 business_date、released_date、原预约 starts_at 本地日、原领退料/采购库存业务日期及原 procurement_create 事件本地日，再取 min/max；正是预约 10-02 使结束日超过当时 10-01。其他六项原来源不应换成新增预约的空白业务，也不能从日期集合删除预约后仍宣称统计含原预约。`source_preconditions` 的保存位于守卫之后（243–245），所以失败 JSON 的 null 是预期，不能推断它未读取前序。

`app/db.py:9–15` UTC-naive 存储时间、today() 按配置本地时区；`operations_analytics.py:16–18,110–124` 按 starts_at 的配置本地日筛预约批次，图和表同 cohort，展示当前状态/是否实际到店/原维修单，caption 明确不得与实际到店日的记录相除作转化率。`report_followon_business.py:297–316` 对全 cohort 明细、当前状态图计数、原接待单唯一行及“已转维修工单/是”都作核对；这些断言完整保留。

库存与专用报表也不能靠未来日期绕开：`inventory_report_common.py:15–23` 明确 end<=today；同一 `src.period` 被后继查询、图、CSV、明细追溯使用。只在事实本地日期已经产生后查询实际 union 期间，保留 HK152/153 在该 parent 的 partial 边界；完整 HK152/153 仍由固定 reports-complete parent 验证，诊断不转为完整 acceptance check。

| 文件 | SHA256 |
| --- | --- |
| tests/browser_click/report_followon_business.py | e5a64e700bcb2be119cdbf482b511f1a43c28fc8c793425a969764636900e1d2 |
| tests/browser_click/repair_business.py | 66aa1e43195d915314262a91ccd06d887209c966343f20b52a8c38dd33d441db |
| app/flow_analytics.py | dde62d794a4ea194ea8dd93988362d2a5c1ef2d3df2962be78b52ac8527745bc |
| app/flow_api.py | ffbc5f2074bcabac473f66416263a7df2d45843d5e8201624b217d306ba83697 |
| app/operations_analytics.py | 1f3f0298339eaaec9b9e245b94d5fbe065c4f9c0387a1510c291e62959bd1b66 |
| app/inventory_report_common.py | 5eb10d5e698799fe88484a8750bd06636869c81648c9c983c0ba9e00ccf6ba65 |
| app/service_intake_service.py | 6752792d72efb211be1d407e9d5c3c44dc301fde6d6ef94c16b5931affc551f6 |
| web/serviceintake.js | 188a00daefea1b51d0bfd23165427ab06f885fec88e3e33b4d63099491bb5840 |
| app/db.py | d7d9143dcfec6eb663dc1fe9f3aad77aa79462b4bd06e685fcd517803399ed89 |

结论边界：已确认源日期与 API 历史范围合同冲突；没有执行补充或新 run，没有将午夜后方案记 passed，没有关闭 full53、HK099 Date 或 193 条原验收门槛。

## 后续 CI 短提前合成输入候选：只读核对

根在 full13 全部收尾 CLI3 后提出将唯一原 UI 合成预约创建时刻改为真实 now+2 分钟，再从真实原表单明确延后一分。只读判断：**原业务合同允许，有限修复范围成立**；本报告没有实施。生产业务、UI 默认、预约 mode、原 API/版本/容量/权限/幂等和报表未来期守卫都不需要改。

精确候选仅 `tests/browser_click/repair_business.py` 的 `async repair_business`（当前 639–959）：

- 665–667 当前读取默认两字段再原样填回，替换为在完成客户车辆/工位选择后，现场读取真正宿主本地 `datetime.now()`，start=now+2min，end=start+1hour，以原 datetime-local 的 minute precision 明确填两字段。不能用先前启动时刻或固定日期；minute precision 向下截秒，实际提交提前余量约 60–120 秒，应紧靠填写取 now。
- 687–688 两个 `timedelta(minutes=30)` 改为 `minutes=1`，仍读取改约原表单上的已保存 starts/ends 后增加同一分，保留一小时长度；691 理由相应改“本次合成客户要求延后一分钟”。原改约确实改变时段，不能只改理由或保留旧半小时值。
- 其余函数、原源码与已生成证据保持原字节；既有 imports 已有 datetime/timedelta，不需加依赖。checkpoint 合同两条只要求真实预约/改约、实际到店、唯一转换和原事实守卫，没有规定必须提前一小时或改约半小时。

时区须按原表单契约处理：`scenarios.py:841` 的 Playwright context 无 timezone_id，浏览器继承同宿主本地时区；`web/serviceintake.js:46` 对 datetime-local 使用浏览器本地 new Date 后转 UTC。建议 `datetime.now()` 的真实本地无偏移值再以 `timespec="minutes"` 填写，保持原浏览器实际时区转换。不能给 datetime-local 填带偏移字面，也不能强行把 Asia/Shanghai 的无偏移时分填给 UTC CI 浏览器，否则会形成额外八小时的未来时间。服务 APP_TIMEZONE 仍 Asia/Shanghai，报表仍按实际保存 UTC 的上海本地日统计。

原服务已核：`service_intake_api.py:31–45` Slot 只要求带时区，AppointmentSave/Reschedule 没有最小提前时长；原 UI 会原样生成带 Z 的真正 request。`service_intake_service.py:142,188` 只拒绝 starts<真实 utcnow；`_slot:68–75` 限 ends>starts、时段<=12h、同工位 live 重叠，改约排除同 appointment。本 helper 为本 run 新增专用工位，不挪旧工位或绕容量。两分钟提前、一小时长度、再延后一分均满足该规则，但若真实操作耗时使提前量过期，必须让原 API 真实拒绝，不改钟、不回填、不盲重放 request_id。

全部引用断言保留：创建 native 201、原客户/车辆/工位/employee/book_event；改约 native 200、changed.version>old、API request 与保存 starts/ends 严格一致、唯一新改约事件；错误 VIN 409且业务不变、真正 ArrivalFact/凭据/门禁、唯一转 repair、原任务完结和最终 converted（703–777）；后继精确有限 `/report_sources` 未变。`report_followon` 的原预约开始本地日、全 cohort表/CSV/图、唯一原 intake 行的 converted/实际到店断言及 date_to<=真实今日（233–239,297–316）全部保留。`report_remaining:693–715` 继续按实际到店与实际接车事件核期间/顺序/数量；`repair_claims` 和 `finance_report` 继续核原已完成维修与有限来源，无半小时或一小时提前量硬编码依赖。

本轮原浏览器报告的固定执行位置：repair-selfpay 在 scenarios[21]，report-followon 在 [31]；原 repair 起点到报表起点累计 587.95 秒，其中中间九个 parent 552.67 秒。因此原运行确实在九分多之后访问报表；新短输入在类似实际用时下，即使开始本地日跨午夜，也已经是真实今天。该时长是原 run 观测，不是未来 CI 的最小时长保证；保留原 future-date 守卫，使极快运行/真实时间突变时不假 pass。不能用该原耗时宣称新候选已动态通过。

## 独立审阅结论与实际定向闭包

根提出的最小测试输入变更可按上述有限范围登记 PATCH；本独立审阅接受其业务合同与范围依据。当前 `repair_business.py` 仍为原 SHA `66aa1e43195d915314262a91ccd06d887209c966343f20b52a8c38dd33d441db`，尚无落盘后新字节可审；因此这里不记“实施已核”或“测试通过”。实际修改后应以原字节备份为基准检查只有该函数内预约填写、双一分钟和理由变化，其他 AST/原 Guard/所有断言不变；重新冻结的新 source/script/runner 指纹用于新 run，不复用原13成绩。

单独运行后继报表缺真实来源；需要**完整递归父依赖闭包**，但实际为 6 个业务注册场景，不是必需 11 个。按当前 runner 注册顺序列如下，名称、函数、超时均由源 AST 的导出 tuple 读取，没有导入模块：

| 顺序 | 实际注册场景 id | 原函数 | timeout 秒 |
| --- | --- | --- | --- |
| 1 | vehicle-purchase-hk171-177-178-026-021-018-029 | vehicle_purchase | 300 |
| 2 | master-data-hk170-172-173-174-175-176-179-180-181-182-183-184-185-186-187 | master_data_business | 480 |
| 3 | customer-service-hk098-107-108-109 | customer_service_business | 360 |
| 4 | materials-hk069-045-054-083-070-072-073-051-061 | material_business | 420 |
| 5 | repair-selfpay-hk031-034-044-049-053-079 | repair_business | 300 |
| 6 | report-followon-hk146-147-148-149-150-151-153-155 | report_followon_business | 720 |

精确边：target `source_facts:198` 读 1/2/3/4/5；repair `source_facts:282–284` 读 customer/master/material；material `source_facts:276` 读 master/purchase。purchase/master/customer 不读其他业务 checkpoint。这也与原13 JSON吻合：前三无业务 dependencies 字段、material 精确两个、repair 精确三个、target 精确五个。此闭包验证 source_id、员工/门店、原创建/改约时间、实际 Arrival/converted 和后继全 cohort 表/图/CSV；共享 helper 的导入不等于必须执行该 helper 所属独立业务场景。历史 `report-followon-click.md` 亦记过所选六场景五前序的真实失败，保持该证据边界。

如果根另选 11 个实际注册场景扩大回归，须明确额外五个目标及它们各自递归依赖，不能将其写成这个 target 的必需父依赖。六项 selected 新 run 完整正常结束后只能记这条定向修复结果，full_registered_suite_complete/full193_business_acceptance 继续 false，HK099 保留 partial/local_source_only，HK152/153 的该 parent 诊断不变；完整53和193门槛仍由以后全量本轮真实证据满足。此独立任务未执行任何定向验证。

## 已落盘独立原字节/AST复审（2026-10-02）

根已事前登记 `PATCH-M8-4-APPOINTMENT-REAL-LEAD-01` 与 `PATCH-M8-4-BUSINESS-SNAPSHOT-READY-01` 并落盘。上述“未落盘”段是此前审阅时点，当前结论更新为：**这两个被分派文件的实际改动精确符合登记范围，静态复审没有发现扩大差异**。不等于动态业务通过；根选择最终完整53复验覆盖真实闭包，不额外执行六项定向。

原件根 `C:/Users/tiefu/.codex/HuaKangOS-agent-validation/runtime-v1/browser-click/launches/business-render-and-appointment-before-20261002/`；登记文件实际路径 `.../launches/business-render-and-appointment-edit-20261002.json`，SHA256 `01319fa7ea8754eaea7bff0e3a58f3449124a7aa52161b9dfefc3ca042e184f0`，33条前后指纹。此任务只深审 repair_business 与 report_followon；不把另31文件记作本审全部通过。

`repair_business.py` 原 SHA `66aa1e43195d915314262a91ccd06d887209c966343f20b52a8c38dd33d441db`，当前 SHA `00151fe0eb2303c22c527b641b3d8cd074eb7eb0f31fe77e19581ebaf97f4445`；与登记该条 before/after 完全相符。完整文件原字节严格仅有四类替换：Checkpoint.passed 的唯一 snapshot 增 `business_ready=True`；创建原三行循环变为真实本机 local datetime.now()+2min/end=start+1hour 的四行原 UI 填写；两个真实原改约表单值的 +30min 改 +1min；理由“延后半小时”改“延后一分钟”。把这四类替换应用于原字节后，与当前整个文件逐字节相等（包含所有其余内容、行尾及终末换行）。

AST 单独解析与函数原文交叉核对：30个函数/方法键及签名未改变，恰有 `Checkpoint.passed` 与 `repair_business` 两个原文/AST发生变化，其余28个函数/方法原文完全相同。passed 的状态标记、condition/action_end/save 等仍在原位置；repair_business 原所有 Guard、响应状态、状态/版本/原来源/材料/现金/错误 VIN/实际到店/唯一 converted 等断言保持原字节，函数范围原639–959、当前639–960。没有 app导入、直接HTTP、API提交替换、SQL新增、Clock mock 或不确定重放。

`report_followon_business.py` 原 SHA `e5a64e700bcb2be119cdbf482b511f1a43c28fc8c793425a969764636900e1d2`，当前 SHA `c1f598c105ef3b8c61e8d2b34a9af7dea6f408de3ec0a7cbc23277d88cc6799a`；与登记该条 before/after 完全相符。整个当前文件逐字节等于原文件仅一次将 passed 的 snapshot 添加 `business_ready=True`；`source_facts` 完整函数原文完全相同，239 的 `require(period["date_to"] <= datetime.now(ZONE).date().isoformat(), "原预约来源还在未来，不能造当前期间")` 原样。期间 min/max、全 cohort、CSV/图/原行断言以及 partial 边界均未修改。

原服务创建/改约、容量、时区和统计期间相关 app/UI 文件指纹亦仍与上表相同。仅AST、字符串/原字节和指纹读取，没有执行脚本/应用/浏览器/SQL；最终53新run、人工六rubric及193仍待真实证据，不将本静态审阅写成自动或人工 passed。
