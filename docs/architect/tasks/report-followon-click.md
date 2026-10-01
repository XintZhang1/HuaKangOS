# 任务：维修与物资报表后继七项原点击、两项局部来源

**负责人／日期**：`remaining_audit`，2026-10-01。原依据 `PATCH-M8-4-BUSINESS-193-17.md` 和冻结 scope `11d8af2e07c43e5fc073333f99365d0998fb92d2d52ed894d7dc1742439b692a`；本次追加按 `PATCH-M8-4-PROCUREMENT-HISTORY-SCOPE-01.md`，只改本人 `tests/browser_click/report_followon_business.py` 与本页。生产、夹具、日期、目录、runner、注册和计划均未编辑，不导入 app、不运行候选。原失败与旧指纹保留。

**目标／架构合同**：沿原业务模块、原日期和现有统计定义，把同轮真实输入至结果来源用于七个独立完整统计检查；HK152/153 明列 partial、无完整 business check。193 原目标不删、不降低完整报表验收条件。不能把空表、入口可开、读导航、另一项通过或源码审阅当作本项验收。金额为整数分、数量为整数千分之一；预约日期、原采购申请日、实际领退日和交还客户日分别保留。人工体验、文案与外部条件不由自动结果替代。

**旧候选指纹**：703 行 Python，SHA256 `b1c9a226e5f7abe9c44dc839f826021a52e53877bda02eb0827b0121be886385`，独立只读短审完成；根已接入 runner。当前修订 SHA 在本次静态交接另报。导出 `REPORT_FOLLOWON_SCENARIOS`；原唯一场景 ID `report-followon-hk146-147-148-149-150-151-153-155` 保留，其中153代表本次 partial 原读取范围，执行窗口720秒。修订后使用全新镜像运行，未重放失败旧库，不拼局部成绩。

**首次真实结果与根因**：根的 `business-report-followon-20261001-01` 所选六场景五前序通过、报表失败并退出1；该报表 HK146/147/148/149/150/151 仅 local passed，HK155/152 未执行，不能记整个场景通过。原采购页显示本轮两行和五实际到退货原账已核对，同时列四条本店当日 kind=purchase/v2 历史简表，`procurement_analytics` 正确返回 complete=false、七全范围金额指标null、charts=[]。脚本错误要求全期间 complete=true，与真实来源条件不符；没有生产统计缺陷，也未删除、改日期或伪造这四条历史行。作者只读 SELECT 核对了外部合成库四来源，不导入被测 app。旧失败保留。

## 原检查与有限来源

| 独立 check_id／原标题 | 原 UI 与本次必须核对的事实 |
| --- | --- |
| `HK-146-business` 维修预约分析 | 统计分析目录检索146→`table/service_appointments`→实际日期。以明确 appointment 的 `starts_at` 转 Asia/Shanghai 日选批次，当前converted、mode、实际Arrival和关联维修编号核对；全本店批次明细与当前状态图基数独立从DB核算。CSV原dataset，同原接待单钻取。 |
| `HK-147-business` 维修工单分析 | `table/repairs`；首维修kind=repair/v4、business_date、amount、当前完成态、多方承担、原Customer Allocation→RepairPayment→PaymentLink→CashEntry逐一关联。全范围 `repair_state` 和new_repairs核对；另实际交还日 `repair_settlements/repair_value` 全范围核对，权益优惠、已应用原售后折扣、套餐capture及既有已审核维修按当前原定义保留。原图点击其结算明细并实际下载，不能把开单日当结算日。 |
| `HK-148-business` 维修项目分析 | `table/repair_projects`；真正released_date的最终服务Settlement/Quote、冻结客户授权与原work行revision/code/name/quantity/unit/amount核对。全范围作业金额图和指标；配件不混成作业，核价不是现金或作业耗用成本。 |
| `HK-149-business` 维修领料分析 | `repair-materials`，原`/api/repair-material-reports`。先明确原维修，再依次选item/history model/work；组合筛选三笔领1250、退250、补领250，净1250。原StockMove与RepairStock反向数量/成本、original_id、Quote授权摘要与Binding对应唯一schema1车型冻结事件。只本原维修要求complete/model_complete=true；汇总、明细、差异三表及成本图，原单钻取，三张原CSV保持同四筛选。作业包含筛选不解释为耗用分摊。 |
| `HK-150-business` 物资入库历史统计 | `table/movements`；单独非空入方向：两个原采购分批验收、维修实际退料、正盘差的实际StockMove。全本店原库存行多重集与DB一致，物资成本图全部日期入/出原成本分别求和；原CSV及本维修入方向原行钻取。 |
| `HK-151-business` 物资出库历史统计 | 相同原明细另独立检查，非空原采购退、负盘差及两笔维修领料负方向；原退引用原收货，原领引用同维修/Quote。再次走原入口/CSV/出方向钻取，不把150入方向证据替代本项。 |
| `HK-155-business` 物资移库明细统计 | `table/warehouse_local_moves`；同轮primary有限entry_ids找到明确local_move原单，真实发出2、分次接0.75/1.25的六行库位/在途配对数量价值净额零。原average_revaluation另列，不能多造门店收发StockMove；全部本店期间明细和净图独立DB核算。零净图按原“当前范围暂无可绘制数据”显示核对，非空配对表/CSV及原单仍实际点击。 |

**HK153仅partial**：原 `procurement-cohort`、`/api/inventory-reports/procurement` 保持完整本店日期范围。严格核本次唯一采购 A8/B2 两行、各两次原验收及 A退1共五原账，原 amount/quantity、case/line/source/StockMove、原退original_id及发生日/单位逐项DB一致；ordered/received/open/closed/pending/returned/retained 原行守恒。另有限读取并核确切四条本店当日 completed kind=purchase/v2、创建本地日与登记日、原编号及原差异说明“历史简表采购：仅按原登记日期列出，缺少不可变逐行订货来源，不混入新订货履约合计”；API差异与原明细逐行多重集相等，不接受任意 complete=false 或其它缺口。whole metrics 必须1新采购/2行/4差异、complete=false、七金额全部null；三表且没有单位图/动态图表，原UI真实中文差异提示可见、图及图导出按钮不显示。仍逐页核三表、一次点击各下载真实CSV、原新采购钻取、全部旧行/唯一精确export审计保护。完整全期间汇总、各单位完整图和动态图原始行CSV保留 not_tested；没有`HK-153-business`或完整通过成绩。

**HK152仅partial**：七项之后从原152入口选本次Item和material Warehouse，核当日桥接 `complete=false/closing_complete=true`，opening/in/out=null、当前有据closing；真实筛选、三表CSV和期末图留证。没有启用前真实历史窗口，不改时钟、回填午夜期初或造历史。单独 `partial_requirements`，没有`HK-152-business`。两项局部观察分别由running到partial，当前局部失败标该partial失败而整场仍不完整，后续not_tested；finish必须七完整check均passed且两partial真实观察完成，人工及business接受仍false。

## 最短同轮前序

1. `vehicle-purchase-hk171-177-178-026-021-018-029`
2. `master-data-hk170-172-173-174-175-176-179-180-181-182-183-184-185-186-187`
3. `customer-service-hk098-107-108-109`
4. `materials-hk069-045-054-083-070-072-073-051-061`
5. `repair-selfpay-hk031-034-044-049-053-079`
6. 本候选。

只读本次固定evidence_root的runner报告及五份complete/passed checkpoint，要求当前catalog与provenance一致，镜像snapshot_stable，十个实际依赖脚本/目录文件指纹一致。不扫描旧目录、不SELECT latest、不同名猜原单。客服099仍为local_scope_passed/partial且business_accepted=false，没有本check，不提升其范围。第一维修精确11个report_sources键；material primary/secondary的有限receipt_ids/stock_move_ids/entry_ids和purchase/item/warehouse IDs原样绑定。当前库存/余额现场重读，不硬等于前序当时数量。

日期取原预约本地日、原维修business/released日、原库存business_date和原采购事件本地日的范围；若预约仍未来，明确拒绝不能纳入当前报表，不造时钟。仅本店真实manager登录，普通原GET/分页/图/钻取后全数据库摘要保持；真实登录合法AuditLog在登录完成后建立baseline，不排除整个审计表。

## 原UI、下载与保护

从原统计分析目录检索准确编号和唯一workflow入口，实际填日期、原表全部分页（flow50／专用25）、真实图SVG/零图提示和精确原单。HTTP只观察原UI产生的GET、原生Cookie及X-Store-ID、完整参数，不用fetch/context.request/直接HTTP替代。原图与表共享整包的数据，不能只把目标来源金额硬等于全范围图。

复用既有Evidence及少量report、sales、vehicle、material helpers；本人候选显式适配维修领料、采购、仓库三类专用CSV，防止旧helper落入visit分支。每次原按钮一次click、原下载事件、实际保存文件核所有headers/rows/顺序/公式防护；不调用导出response.body/CDP重新读取原URL。普通查询JSON只读原响应。结果不明停止，不重放。

导出只准精确一条新增本人本店export审计，原entity_type、entity_id=null、reason、before/after=null均核对；全部旧AuditLog原始行保持，所有其它表完整摘要不变。flow为`flow_analytics`/原table.title；维修领料为`repair_material_report`，采购为`procurement_inventory_report`，仓库为`warehouses_inventory_report`，后三者reason=`date_from至date_to table_key`。不粗排除audit_logs、放宽多条或只比较条数。DB访问四处均SELECT-only；有限表标识白名单、本店范围、25001探测上限明确拒截断，Binding主键精确case_id。

每check的状态只记录本次自动UI/API/DB结果；未开始not_tested、当前failed即停止，已执行局部证据保留。six criteria中simple_flow/concise_copy人工pending；自动passed不能设置business_accepted或full193，集团跨店、历史完整仓库期间、PG/Linux、真实模型/银行/实物及员工验收继续独立。

## 静态审阅与待测

- 作者人工逐函数核原UI、API和models：预约批次／入出／报价与库存方向、专用表键／导出、原发生日期／事件日、全范围图和单审计合同一致。修正本候选Binding排序主键，补实际接车日完整金额图，来源099保留partial。没有生产修改。
- 原703行AST/独立短审通过不继承为运行成绩。修订保持全部直接DB.rows调用SELECT、无app导入；新增仅准确partial状态处理、原历史四差异/全范围unknown/图不可见及原五账精确字段核对。旧七完整check、普通读/实际CSV审计保护无放宽，修订 AST/差异/指纹在交接另报。
- **待实测静态条件**：`app/repair_material_api.py`导出仍依赖get_db，读取后写audit+commit，未采用已有get_audited_read_db。这是同型SQLite事务风险，尚未在本路径捕获错误，不能称517。严格保留一次导出一条审计，若真实失败由根另登记生产修复，不由候选放宽／重试。
- 真实复验仍需原目录DOM、日期、四筛选、所有分页、完整七项图表及真实下载；采购partial只接受已核确切四历史来源，其余缺口仍失败。完整采购图和单位动态图CSV不计通过，也不删除历史来源求通过。三种宽度/人工体感未由本候选替代；未测分支不记通过。

**当前位置**：原注册候选首次运行失败已保留；全部关联实例结束后按根登记补丁窄修，作者静态核对及新指纹交接，不自行运行。根负责独立短审、新联合镜像与实际复验，不把首次六个local passed拼为整场通过。
