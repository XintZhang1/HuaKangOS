# 当前正欠额三项原生点击候选

2026-10-01，M8.1，按 PATCH-M8-4-BUSINESS-193-36、PATCH-M8-4-RECEIVABLES-MATERIAL-SOURCE-01 和 receivables-remaining-scope.md 编写。仅新增 `tests/browser_click/receivables_business.py` 与本记录。未注册、未导入应用、未启动实例或浏览器、未执行测试；静态核对不登记业务通过。

入口 `receivables-hk157-158-159`，导出 `RECEIVABLES_SCENARIOS`，单三元组 timeout=1500 秒。三个完整自动合同分别为 HK-157-business「物资应收账统计」、HK-158-business「整车相关应收账统计」、HK-159-business「维修应收账统计」。人工体验、文案及其余六类标准保持 pending，`business_accepted=false`、`full_193_business_acceptance=false`。失败停止当前 check，其余未执行项保留 not_tested；结果未知不重放。

## 同轮有限前序

固定要求原采购场景 `vehicle-purchase-hk171-177-178-026-021-018-029`、主档十五项、首维修六项、精品六项、原整车销售交付场景整场在同轮通过。使用各父 `business-checkpoint.json` 的明确 report_sources / check evidence；核外置 provenance、脚本及目录 SHA、源码与执行器指纹、当前数据库与 evidence_root。若当前批注册清单存在 Retail 四项父，该父也必须整场通过，不借它的失败或局部结果。

有限来源包括：BT 的 `item_ids[0]`、`profile_ids[0]`、`enrollment_ids[0]`、supplier/warehouse/location/account；首维修的 customer/customer_vehicle；原销售的销售本人 customer；主档 HK175 WorkItem 与 HK179 AgencyProject；采购 HK177 brand/series/model、HK178 实际整车 warehouse/location。提交前重读本店启用关联、车型版本、实际员工岗位；不是使用旧库存快照假定余量足够。

## 本次原界面输入至结果

| Check | 新原事实及明确正欠额 | 原页面/API与岗位 |
|---|---|---|
| HK157 | BT 原 item0 另采 1000 数量、单价1000分；原独立批准、全额请款/实际预付、原库位实际收货。新普通 Retail 商品1000，约定2000、实际收500、待收1500；不安装、不选会员价/权益。 | 原 procurement 创建/approve、prepay_request/approve/pay 与 receive；库存员工申请/收货，主管独立批准，财务本人实付。原 Retail create/approve/authorize/prepare/dispatch/accept/receive，各当前 Task 本人；不复记 HK074。 |
| HK158 | 原 UI 另购一台新17位VIN，实际成本8000、售价10000，原请款/实付/发运/本店实收车。新销售10000独立复核、该 VIN 配车、当前合同真实生成字节/签回确认，实际收3000、待收7000。另建同客户同销售当前版本的 fee 服务1000、独立批准授权、实际收300、待收700；未冒充外部办结。 | `/api/vehicle-procurement/orders` 原动作；`/api/sales-quotes/orders` 与 `/api/flow/cases/{id}/actions/{action}`；`/api/service-orders`。采购库存/主管/财务，销售本人、独立主管、库存配车、财务原款；关联服务源允许已签回但未交付原销售，实际服务履约未执行。 |
| HK159 | 主管新建独立 repair 工位；服务顾问原现场 walk_in → 原 VIN/独立读数实到店 → convert v4。纯作业3000、独立核价和授权，技师开工/完工、另一员工质检；客户承担2000/内部1000，真实客户到账500、待收1500。技师原 UI 实际移出工位；未客户接车、未记内部现金。 | `/api/service-intake/resources`、appointments 原 arrive/convert、`/api/repair-orders/{id}/actions/{action}`、`/api/service-intake/orders/{id}/resource/release`。当前原 Task 本人、同单 CAS；不改父维修领料/现金或占用他人工位。 |

HK157 实采后的成本沿真实新收货和原账面均价分配，不猜零成本、不缩销售数量求通过。HK158 新 VIN 不复用已交付/退订父车辆；生成文件和签回件保持原字节/源 hash/快照指纹。HK159 内部承担不进入客户应收；实际释放工位与接车出厂为独立事实。

## 报表与旧行保护

每个 check 都从原统计目录检索对应需求，进入 `table/receivables`，使用上海业务日同范围 GET `/api/flow/analytics`。财务当前尚待收取 KPI → 查看明细，全分页的原八列/原单按钮/CSV 与来源匹配，再进入各新单通用原单和领域原明细；HK158 两单分别钻取。原合同无专用应收图，不新增图、不用 cash_category 冒称应收图。

独立 SELECT oracle 读取有限46原表，计算当前本店全部正 gap；包含当前详细维修各外部承担、Retail 原退/C-P-S核销、本店 fee 与 pass 切片、有效保费与已确认佣金、加装、厂家收入/原退货、通用原单和已有 legacy 原款。分别保留本金/权益/现金及现金定义7，不以本次四单金额充当整店总额，不把日期选择重建成历史余额。整表 Counter、总额、逾期额与 UI/API 一致，四个新来源的约定/实收/欠额均为非零且独立核对。

原业务 Guard 在真实登录完成后建基线，保存全部原业务表 hash 与动作许可表的全部旧行（BLOB 字节只在内存比较）。仅允许本次明确 Case/Task/Account/Vehicle/CV/Resource/原库位和有限列变化，原现金/StockMove/其他业务不粗排除。新 FlowReceipt/IntakeReceipt 的员工/本店/request/digest 与实际原提交、实际响应相符； generic Task assign 只使用原三字段，没有虚构 request_id。附件 checkpoint 仅 metadata/长度/SHA，不写 bytes、base64 或 default=str。

CSV 只原按钮下载一次，整表/范围/安全文本与下载字节匹配；仅允许精确本人、本店、entity_type=flow_analytics、action=export、reason=当前待收款的一条新增审计，全部旧审计逐列相同，其余业务 hash 不变。查询、分页和钻取为零业务写。

## 静态审阅与待测

自审：Python AST、原 helper 调用必需参数/关键字、所有直接 SQL 的 SELECT-only、有限表名、三元入口 shape、目录三 check/title、原单位、时间区/权限/Task/CAS/原请求摘要、文件元信息与旧行 Guard；仅这两 owned 文件空白检查。没有 import app/helper、没有 suite、没有 UI 或业务执行。

实际原 lookup/折叠/任务交接、multipart 可观测性、文件生成/下载、全店 oracle 在本轮全部父与更正/权益边界下的对应、三次原 CSV 唯一审计仍待 root 新鲜实例执行。逾期、再收/退款、并发/占额、跨店汇总、超过有限读量、其他承担和客户实际接车另列 not_tested。真实银行/实物、人员体验、PG/Linux、ClamAV、外部来源和生产门槛不由合成自动检查替代。
