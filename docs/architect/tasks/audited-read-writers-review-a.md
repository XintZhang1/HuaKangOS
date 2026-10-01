# 同步审计读取接线与下载/普通采购候选独立审阅 A

2026-10-01；当前 M8.1 同一浏览器交付子审阅。依据 PATCH-M8-1-REMAINING-AUDITED-READ-WRITERS-01、PATCH-M8-1-CLOSED-SHORT-WRITERS-01（整文件逆向范围校验）、PATCH-M8-4-REPORT-NO-PREPAYMENT-TOTALS-01。只读生产源码和原字节留档，维护本报告与本任务上一份报告；未修改源码、测试、runner、CI或共享索引，未导入 app、启动服务、运行浏览器/测试、访问真实配置/数据。结论是静态源码审阅，不是动态 passed。

## 8 个 GET 依赖改动

独立读取 `V/browser-click/launches/audited-and-closed-writers-before-20261001/app/` 原字节，而非采信 edit-record 的布尔结果；以 `audited-read-writers-candidates.json` 的8项路由反向核对实际源码。

8项均保持原同步 def、原 method/path、原 decorator/schema、db→get_user 顺序。逐项比较完整 decorator/def至end_lineno 原文本：仅将当前 `db=Depends(get_audited_read_db)` 还原为原 `db=Depends(get_db)` 后，与留档函数原文完全相等；另比较 body及decorator原文相等，函数内无 await/yield。当前实际审计来源均保留，不改变原读取/业务权限或失败合同。

| 原函数/完整路由 | 当前依赖 | 保留的实际写入与 commit |
|---|---|---|
| `flow_api.download:215`；GET `/api/flow/files/{file_id}` | get_audited_read_db→get_user | 原单/逐文件权限、扫描、字节解析后 audit(download,flow)，原223 commit |
| `dossier_grant_api.record:114`；GET `/api/dossier-grants/{grant_id}/record` | get_audited_read_db→get_user | service.read_record→_record_access；DossierAccess(record)+AuditLog，service553 commit |
| `dossier_grant_api.files:119`；GET `/api/dossier-grants/{grant_id}/files` | get_audited_read_db→get_user | service.received_files→_record_access；DossierAccess(directory)+AuditLog，service553 commit |
| `dossier_grant_api.download:124`；GET `/api/dossier-grants/{grant_id}/files/{file_id}` | get_audited_read_db→get_user | 原批准逐件范围/源店/原文件核验后 _record_access；DossierAccess(file)+AuditLog，service553 commit |
| `stock_report_api.export:20`；GET `/api/stock-reports/period/export` | get_audited_read_db→get_user | 原同期间数据/CSV，audit(export,stock_period)，原27 commit |
| `material_value_api.export:23`；GET `/api/material-value/export/{key}` | get_audited_read_db→get_user | 原同范围收入成本数据/CSV，audit(export,material_value_report)，原34 commit |
| `repair_material_api.export:21`；GET `/api/repair-material-reports/export/{key}` | get_audited_read_db→get_user | 原实际领退料数据/CSV，audit(export,repair_material_report)，原31 commit |
| `main.export_csv:425`；GET `/api/export/{module}` | get_audited_read_db→get_user | 原require_full/legacy查询、最多10000行与CSV防公式，audit(export,module)，原439 commit |

整6个生产文件逆向 AST 另核对本次已登记的全部15依赖名称（8GET、main六管理入口、flow.master_list）及只在原来没有别名的文件移除新 get_audited_read_db import，结果与before整文件 AST相等；不是只比较8函数后忽略同文件额外修改。imports新增严格为 dossier_grant_api/stock_report_api/material_value_api/repair_material_api/main 的 `.db get_audited_read_db`，flow原已导入。整文件当前hash同时与外部 edit-record 相同；无未登记body、decorator或异步函数改动。本报告仅对8审计GET业务语义负责，其他7项独立审阅由其主审报告负责。

`get_audited_read_db` 仍为 db.py 中既有 get_write_db 别名，取原cached get_db Session，在 get_user 首次读前为SQLite请求bind设置OptionEngine并取得connection，跨原commit保持该请求begin合同；PG、原鉴权/门店、Dossier独立批准/角色/access_version/逐件授权/到期撤销、文件扫描/摘要字节、原审计唯一提交和错误转换全部body未改。没有重试、提前返回数据、增加模型确认能力或业务写入。

## 异步边界补充修正

已修正本任务 `audited-read-writers-current.md` 的work-status行。实际 `business_assistant_api.work_status` → workboard.work_status:307 → business_tools.native:156 → service.run_tools/registry → `_run_registered_tool(read_data)`：service.py:933先 `db.commit()`结束原读取事务，再await gateway；返回status>=400时调用record_issue:381–389，新增AssistantIssue并经commit helper提交诊断。成功读取不追加原audit/access，不代表所有路径无commit或失败写入。该含await诊断闭面不混入8同步成功审计GET，也不给外层async/SSE持续持writer。另有Runtime既有DG_RECORD调用原dossier record的子入口访问审计，仍由原子请求自己的依赖负责；不扩大已审阅能力目录。

## 最新生成文档下载候选

检查当前 `tests/browser_click/sales_order_business.py:345 generate` 与HEAD脚本原文差异：只有该函数SELECT补原 `media_type` 及原expect_download中的同一文件GET响应监听/即时核验；其他函数AST一致。原文件生成POST、快照/报价revision与digest、VIN/金额、下载保存、全字节SHA256/size、DOCX XML原单/VIN/金额、全旧业务行不变、旧审计逐行不覆盖/删除与新增恰一审计的本人/本店/原单/原文件/action/reason/空before/after全部保留。

真实生产类型链是 `flow_api.download` 返回 `Response(media_type=asset.media_type)`，`flow_documents.generate_document:189` 保存标准 `application/vnd.openxmlformats-officedocument.wordprocessingml.document`。最新候选已将HTTP Content-Type（去参数）同时精确比较原FileAsset.media_type与标准DOCX，**不使用旧summary误写的octet-stream**，也不修改生产类型。200、Cookie存在、X-Store-ID=1、X-App-Request=1均核对原当前店销售场景；观察记录只保存cookie_present，未保存Cookie值。请求仍由原UI的downloadfile按钮触发；无测试fetch、Cookie桥接或额外GET重放。

即使503无download事件，内部expect_response先获得同一GET并记录status/content_type/当前店/Cookie存在，require失败会退出外层expect_download。已静态读取本验证venv的Playwright1.56.0 `_impl/_async_base.py:44–59`：AsyncEventContextManager.__aexit__在exc_val存在时取消事件future，仅无异常才await事件；因此该结构不会以下载等待超时覆盖已经观察到的HTTP拒绝。仍须新浏览器实际验证失败/成功链；静态阅读不写动态通过。

## 普通采购最终合同断言

当前 `tests/browser_click/report_complete_source_business.py:716 procure` 与原reports-complete-source-07/scripts原字节比较，全文件差异仅最终守恒require这一处：原以不存在的prepaid_cents为0进行下标读取，改为保留paid_net_cents=1500、payable_cents/supplier_refund_due_cents均0，并明确 `body['prepayments'] is None` 且 `'prepaid_cents' not in body['totals']`。登记补丁的目标函数名已核对为实际procure。

原 `procurement_prepayment_service.adjust_totals:45` 在未启用Facility时直接返回普通采购totals，`describe:198` 返回None；原 `procurement_service.totals:49–62` 提供普通净付款/应付/应退字段。候选与此实际合同一致，直接索引保留应有字段；没有 `.get(...,0)`、造预付款来源或将未知默认为0。原完成状态、库存量/价值1500、两批余额500/1000、现金方向2000支出/500收入、同原付款/同账户、原退款/库存来源、各次唯一回执与全旧行守卫均未改。生产服务未因测试缺字段添加prepaid_cents。

## 静态结论与未执行范围

所审精确生产接线与最新两处候选符合已登记范围，没有发现阻止新隔离运行的源码问题。解析与原文/AST对照已完成，不启动业务实例、不运行测试、不将旧父成绩拼为full53。新镜像仍必须实际通过受影响销售生成下载、采购原退款与同范围CSV、Dossier成功与原拒绝路径、并发writer/下一事务；193/111、单次同版本full53、真实Date、101/283真实模型、PG/Linux/员工试用/生产条件及四开关默认关闭继续保留。

## 审阅指纹

| 文件 | before SHA256 | 当前 SHA256 |
|---|---|---|
| app/flow_api.py | e6b2a3b8442da3bcef3b45d701e0304930ff5127f5fca22a613e00c43b9139c3 | ffbc5f2074bcabac473f66416263a7df2d45843d5e8201624b217d306ba83697 |
| app/dossier_grant_api.py | a8ec3e4c56cc36d1c3dd8069c7f4dcbcd5a3691f1de2e34a31505d60692dd8b6 | 5f92d42af37afbbf98d51673f4cf16171402c9eb72c1090b0664c322f428be7f |
| app/stock_report_api.py | a061442aaea938a8e9817528d74439e5392c8e4927d1945e5b896ddd640f3684 | 6c76d2c093354720ce97c12aa1e49877c73bd1b43c354830a16a71d34ce1e968 |
| app/material_value_api.py | 610876f43c2d14ce5e28eb007896a544f67fa8f016c428e53de8bb099167061d | dea4d989c55b6a79a88ed85fbed0ca46f9bb8fdd7bae29e1c25171a1ac07d98e |
| app/repair_material_api.py | ce2c7799385ba5bc6cbeba23ddde5e288f151591ebe8424a89cb1ba8d289c33d | 6af567e6e50e839a5f56e85be4bb427d55fecbb3552859a9b9ab42dfab72d349 |
| app/main.py | 9f21f180c1c53513dae2bfcb55b14e43f677d46a776ef0a694a2124e1e09e274 | c6df782f65a95ce6d24ffd4cde18b1e8a2581b9c57835341be90a9c02777862d |
| tests/browser_click/sales_order_business.py（before为当前HEAD） | 4cd5e5b2468e1cd9f40884033f614342a9633bd0afab46393a20ce01fdf0cb92 | 13cd965f134aa1848f83d4ff7b71501f5c548cb5459e5566d4a2a4d7fbb949f0 |
| tests/browser_click/report_complete_source_business.py（before为reports07原run脚本） | f5a001fb75240afa993a7d3e9720e4963f2639994f6cd36cb9d3ab06c3bd1b00 | 4a9b0fb1f45fc4aa42ed1605708ceff28fa50e8601b7d6678f414e0861f25af2 |

外部8项候选JSON SHA256仍为 fcea48139db0128f40cc76358847efd1afd72536b86fa588ba158940f7e3063d；本子任务未改它。源码原字节SHA与上述目标之外的已有修改不互相替代。
