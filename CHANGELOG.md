## n46a-fix1 续开发检查点（2026-09-22）

- 统一找回往来 `material_found` 的运行模型与已有迁移约束，修复反向实际清算误报版本冲突。
- 新增月结定义9的六类本店找回来源及恢复校验；保留历史定义1—8，原赔款关联不重复现金入账。
- 修复旧数据库尚无车辆观察纠错表时恢复统计返回空值的问题，部分 schema 仍拒绝。
- 精品集团混合支付原生产链路尚未完整接通，公开写入口及相关旧入口隔离，保留权限内只读和普通现金精品流程。
- 本轮22个显式模块共273项通过，44个网页脚本语法、Python编译及需求台账校验通过。浏览器受本机访问策略阻止、真实PostgreSQL未跑，不扩大历史证据。
- 仍为0.4建设版；数据库head仍为n46a_operations_extensions，未改历史迁移。详见《续开发交接_2026-09-22》。以下记录为原项目历史。

## m359 物资运输差异与实际清算（2026-09-21）

- 新物资调拨v3将短少、拒收坏件、退回在途分别追溯原批次；双方各自观察、独立批准、实际处置和原成本核销，旧v2保留。
- 各店按原承担独立确认外部追偿目标、实际收款及原账户退款；损失承担往来通过双方实际清算核销。
- 在途、原损失、双方承担、追偿和店间往来使用同源图/明细/CSV；月结v8冻结本店原事实，1至7范围保留。
- 真实Chrome五条手机场景与PostgreSQL m359 342表非空迁移恢复通过；77模块整轮1024项通过、1项Windows符号链接权限跳过，源文件运行期间无变化。损失后找到原物资的原路恢复尚未交付，公司验收与正式启用未通过。

## 0.4 建设检查点：采购、精品、对账与期间库存（2026-09-21）

- 新增整车采购计划/核价/请款/分笔实付/VIN收发/采购退回原款退款；默认关闭旧裸录车辆写入。
- 新增精品多明细授权、跨业务库存预占、真实出库/安装/接收、原单部分退货及退款。
- 新增门店期间来源快照、差异处理、独立封存/复开；两店实际清算保留未收在途并配对冲销原往来。
- 新增物资期间入出存与可用量；精品跨期退货、整车采购和内部现金使用同集合图/明细/CSV。
- 477项完整测试、各模块真实Chrome员工场景、PostgreSQL q117 124表非空迁移与独立恢复通过；仍为未正式启用的建设版。

# 0.4.0-dev · huakangos 建设中

- 产品改名、193项稳定需求追踪、独立Python开发环境，重跑原152项测试。
- 逐门店岗位、集团只读、明确流程版本与PDI整改复检、未发生事实的取消出口。
- 集团共享身份/本金/赠金/积分/券/套餐、冻结规则、跨店核销和原款退款；内部往来与现金分开。
- 类型主档与新空店期初、多行物资采购退货、物资和整车跨店交接、库存代次与在途账。
- 维修v3报价和逐版授权、原领退料、质检返工、四方承担与后续到账；客户车辆、服务任务与独立规则提醒。
- 附件隔离和ClamAV协议适配、独立日报、恢复校验；真实PostgreSQL17.11非空转库/备份恢复验证。

本版仍在建设，未完成193项或正式启用。准确验证边界见 `docs/验收与限制.md`，后续批次另行追加。

# 0.3.0 · 流程试用版

- 删除自动改代码、Git提交、飞书代码审批和自动发布运行链路；兼容保留历史表，不保留执行入口。
- 新增15类流程业务、任务交接、并行订单办理、客户关联、结构化动作目录与记录。
- 新增受权限保护的文件上传、4类文字模板与DOCX生成、模板版本及业务快照、签回关联。
- 独立数据可视化栏目，9视图、14图表、中文明细导出；新旧业务合并日报。
- 新增物资库存价值流水、储值余额流水及退款占用、费用和责任分离的维修办理。
- 旧销售/维修/保险单默认只读，避免绕过新流程。新增0.2数据保留迁移及验证记录。
- 逐项需求覆盖表、默认流程蓝图、动作清单、统计口径、AGENTS.md及本地试用说明。

范围和验证限制见 docs/验收与限制.md。不是原需求表的全量完成声明。

## 2026-09-21 建设批次：库位、会员生命周期、接待与票据

新增独立仓储作业及库位原账、会员卡/续会/消费积分追回、维修预约与原单内部责任返修、外部发票协同与部分冲红；迁移链r218→s319→t420→u521。共用过账保留原业务版本与实际凭据，新增当前及期间经营明细。月结以显式来源定义保留历史范围；各域加入非空恢复校验。完整回归568项通过，后续新增派生来源恢复修正另有专项验证。未部署、未全量业务验收。


## 0.4 construction — k137

- Order/v4 creates independent insurance/v3, addon/v3 and agency/v3 tasks only after current VIN/quote consent. Parent cancellation, children, original money and physical facts remain distinct; new cancellation approval is independent of the latest requester.
- Procurement/v3 reserves approved return quantities and separates original supplier credit from actual moving-average stock cost. Published v2 semantics remain intact.
- Insurance keeps principal/direct payment/pass-through/confirmed commission/cash separate. Addon keeps authorized lines, stock, installation, inspection, acceptance and original returns attributable.
- Actual repair material reports, role-safe finance/event/file views, user access CAS and monthly source definition7 are included. Definitions1–6 remain frozen.
- Synthetic PostgreSQL17.11 k137 migration/transfer/restore:312 tables,5941 rows,317 files,291 sequences. Company/production acceptance remains outstanding; see validation records.

## 0.4 construction — l248

- Approved legal entities and actual account channels are frozen into new cases and cash; original responsibility/returns retain the original entity revision. Formal invoice issuers and generated document snapshots use that revision.
- New formal-store opening now follows entity/account approval and reuses explicit approved account IDs. Trial rollback, independent physical/finance verification, original baseline dates and source restore checks remain separate from cash movements.
- Actual presales contact/vehicle gate reports and detailed material income/cost reconciliation share chart, table and CSV populations. Missing source facts and whole-order adjustments remain explicit.
- Synthetic PostgreSQL17.11 migration and restore:328 tables,6701 rows,367 files,298 sequences. Long legal fields and approved-policy opening are included. Six short/long document samples were rendered and every page inspected; this is not company template approval.
- Requirement tracking remains94 implemented/99 partial, with no company-wide acceptance or production activation. Final regression evidence and remaining exceptions are tracked in the validation and progress documents.

- l248 frozen regression:988 passed,1 Windows symlink skip,1185.87s across74 explicit modules; recorded source files were unchanged during execution.
