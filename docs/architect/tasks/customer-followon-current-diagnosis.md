# 客户后继 finance08 首次失败诊断及窄修审阅

2026-10-01，M8.1。只读诊断当前外部合成实例和静态源码；只写本页，没有修改生产/测试/runner、导入 app、启动服务/浏览器、执行 SQL 写入或重放请求。SQL 仅读本轮 synthetic.sqlite 的明确有限编号，URI mode=ro、query_only=ON，没有读取凭据、Cookie、密码散列或真实数据。

## 原实例和终局边界

外部原件：`C:/Users/tiefu/.codex/HuaKangOS-agent-validation/runtime-v1/browser-click/business-finance-remaining-20261001-08`。provenance.snapshot_stable=true；生产 SHA256 `a2cd8704e5e02aa0c24a72bec269497e62554adc8284300098ae4191e8e6a9f7`，脚本 SHA256 `02c316bac9eb1903554159c9bfab92620610ff7613ae0fd7d059a1da8fcd5307`。

自动报告为 selected，complete=true、17执行/15passed/2failed、passed=false。`customer-followon-hk100-101-102-103-104-110-111` 终局失败，406动作/158点击/60.0秒；后继财务六项严格因这个父场景失败而不办理。不能从本场景局部事实或另一 run 继承完整父通过。

业务 checkpoint 中 HK100/102/104/103 各自 passed；HK101 failed，HK110/111 not_tested，checkpoint.complete/passed=false，没有最终 report_sources。实际失败保存在 `215-failure.png`、actions/network/observations 和 scenarios.log；原件没有覆盖。

## 首个真实失败及原事实

动作405真实点击 `care-q-export`，GET `/api/customer-service/questionnaires/export/questionnaire_issued` 返回200、text/csv。已保存 `questionnaire-questionnaire_issued-405.csv`，247字节/2条原发放行，SHA256 `71d65a7d683a7407f4ce138043d30bdb7edf453094b850a3d6af87b8e55b718f`；原全表/旧行 Guard 已确认只新增本人本店 Audit1385。

动作406点击第二张原表导出，GET `/api/customer-service/questionnaires/export/questionnaire_answers` 实际返回 **503/application/json**。请求仍为本人同源 Cookie、当前店头1、原 GET；没有出现第二个 CSV 下载。失败不是POST来源字段、原业务身份、问卷版本或已提交答案不匹配。

旧候选 `questionnaire_csv` 979–983 的结构先退出外层 `expect_download`，然后才取得并检查 response，所以原503被15秒下载等待超时覆盖为 `TimeoutError waiting for event download`。页面原 `download()` 经 `api()` 先校验HTTP，503时不会制造 blob或触发下载，前端拒绝失败导出本身正确。该实现中没有从响应体取得并保存503原JSON；network保留 status/content-type，不能凭源默认文案伪造当次捕获的 response.detail 或完整原URL查询字符串。

问卷原业务早已真实发生，且独立于失败导出：

| 原事实 | 本轮有限证据 |
|---|---|
| 原问卷127/128 | 两单均 store1/customer41/CV2，created_by=owner16，当前 completed、version5、completed_date2026-10-01；原 Care.result=resolved |
| 原 Task334/335 | 同两单，customer_service角色，本人assignee16/done_by16、statusdone、version2 |
| 原 Binding1/2 | 分别绑定 Case127/128、Version1/2；原发放 number2/3，三题 visits/resolved_feedback/next_step；两个不同 schema digest 保留 |
| 原 Response1/Record30 | actor16/runtime，答案严格 `{visits:0,resolved_feedback:false,next_step:'none'}`，原题number2 |
| 原 Response2/Record31 | actor16/runtime，答案严格 `{visits:1,resolved_feedback:true,next_step:'confirmed'}`，原题number3 |
| 原 POST close | `/cases/127/actions/close`、`/cases/128/actions/close` 各HTTP200、本人的Cookie/CSRF/store1、submitted_version3，并等待对应当前GET。新 Receipt44/45 的原JSON result.case 为对应 completed Case |
| 原导出审计 | 唯一 Audit1385，actor16/store1/actionexport/entity_typequestionnaire_report/entity_idnull/reason=`2026-10-01至2026-10-01 questionnaire_issued`；没有 questionnaire_answers 成功审计 |

成功第一CSV前后原业务摘要：4576行/SHA `400abd410de7e476a532aaba0e217357a6df8c805afd78a045d46cc4865268c8` → 4577行/SHA `8c8c6d0533b4b7326e930478479022595256f77288b3f7a7a7c59e80cf1f8baa`，唯一新增 Audit1385；45个 CareReceipt/2个原 Response 各表摘要保持。第二CSV前基线就是后者，失败后未执行原 Guard.finish/全库 after 快照，故本诊断不声称已独立证明失败前后整库摘要相等。只读有限查询确认原两回答/回执存在且无第二成功导出审计；不补写任何原事实。

## 产品原因与最窄修法

失败镜像和诊断当时当前文件一致：customer_service_api `280164918803c8eb3421d4c60f4c4165115fe2dc96600e20f2918359a2278d8b`、CF `a550e24088bff8facb9c8d60ae044f301f89e8ebc5fedc33203c27998352ea18`、questionnaire_analytics `88b74d0f737d027013b816d024768c4596a7c781a97e6276735a0432eba7b424`、db `d7d9143dcfec6eb663dc1fe9f3aad77aa79462b4bd06e685fcd517803399ed89`。

原 `customer_service_api.questionnaire_export` 290–307 仍 `db=Depends(get_db)`，先认证/授权/统计读，再实际 audit+db.commit，是会追加审计的同步GET。SQLite实际WAL；独立Worker并发下该DEFERRED读取快照存在升级写入竞争。原127同步POST/PUT业务写补丁没有包含此GET，不应声称已覆盖。server.log 有 OperationalError code5和517以及全局 Database operation failed；当前 main.operational_error 固定返回503。日志不带SQL/路径/时间，不能将每条517逐一配到本请求，但原503和该路线缺少writer预留的事实已明确。

最窄生产修法是该唯一导出GET采用既有 `get_audited_read_db`，在get_user前沿同缓存Session预留请求级SQLite审计事务；普通 report/其它GET保持，CSV期间/原schema/答案/转义/BOM/权限/单条审计/commit和PG行为不改。不重试、不重放、不关闭Worker或放宽原数据/权限合同。候选只将真实response取值、脱敏状态记录、200+CSV严格判断移入外层expect_download，在未成功时按真实HTTP立即失败；成功分支全部原断言保持。

## 根窄修后的独立只读审阅

根确认三个当前实例终局、对应Python和64950–64952监听无存活后，先登记 `PATCH-M8-1-QUESTIONNAIRE-EXPORT-WRITER-01`，实施以下两文件。原字节可恢复于 `launches/current-three-fixes-before-20261001/<file>`，与上述失败镜像SHA相同。

| 文件 | 原 SHA256 | 新 SHA256 |
|---|---|---|
| `app/customer_service_api.py` | `280164918803c8eb3421d4c60f4c4165115fe2dc96600e20f2918359a2278d8b` | `eb500bead91e3e8584d9c603e3e8830b0adffb5a451aa4d2b895af911b760857` |
| `tests/browser_click/customer_followon_business.py` | `a550e24088bff8facb9c8d60ae044f301f89e8ebc5fedc33203c27998352ea18` | `c4fc0e4077811135cf79ae77e5777bbaa7127f03e0ea2fbb3726fa533c8c8029` |

API仅补 `get_audited_read_db` 导入和唯一 questionnaire_export 的 db默认依赖；db仍先user。逆向规范化后二者以外整模块AST与原一致，函数体、decorator、schema、原report和其它入口未变。当前别名是原 `get_write_db`，其依赖原get_db，在当前Session首次认证连接前设置请求bind的SQLite写选项；PG不进入SQLite分支。

CF只改变 questionnaire_csv 的响应诊断顺序，新增观察仅 table_key/status/content_type/Cookie存在性/store_id，没有原头、密码或令牌。非200或非CSV在download context内部抛出原require；读取本轮Playwright `_impl/_async_base.py:51–60` 确认 `AsyncEventContextManager.__aexit__` 遇异常调用future.cancel而不等待download，所以不会延长超时或把无下载当成功。成功时仍须真正download事件。Cookie/X-Store-ID/X-App-Request、失败检查、BOM/实际CSV字节、全范围逐行、原筛选、唯一本人本店Audit及旧行Guard尾段AST精确与原一致；其它所有模块AST不变。

两当前模块AST解析和增量比较完成，未发现确定静态阻断，可以新隔离目录复验。此结论不是运行通过；原finance08和CF失败保留，不能把本次已保存的问卷回答当下一run的夹具或继承父passed。新实测须用新镜像/同轮完整父，财务依赖按原门禁保持；全53、193体验、Date、PG/Linux、真实模型/员工/生产条件仍分别待满足。
