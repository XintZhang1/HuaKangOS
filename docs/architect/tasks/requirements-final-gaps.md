# 193 项需求最后覆盖缺口：只读清点

2026-10-01，负责人 `click_scenarios`。本页只核当前目录、注册源码、原业务合同和有限外部报告；没有启动应用、浏览器或测试，没有修改目录、计划、夹具、生产、runner 或冻结候选。HEAD 为 `8993ca8c755194a42a48e7323fe355e80c6bf9ae`，工作树另有根代理与其他作者的未提交改动，以实际字节为准。

## 当前清单与成绩边界

当前 `scenarios.py` 静态解析得到 **49 个唯一有效场景**：原关键点击 9 组、需求入口 4 组、业务场景 36 组。注册业务脚本声明 **180 个唯一完整 `HK-xxx-business` 检查**；另有 **10 项已落盘但未注册的候选**及 **3 项 partial**，合计 193。180 是源码覆盖声明，不是当次 49 场景或 180 项实测通过数。解析完整合同时必须排除 `PARTIAL_CONTRACTS`，不能把 `report-followon` 场景名中的 153 算成完整检查。

原 acceptance catalog 仍为 193 项 `execution_status=not_tested`、`business_accepted=false`，源审阅 193/193。这是源合同，执行结果由外部同轮报告汇总，不将历史结果回写目录。完整 business check、场景完整通过、六类人工标准、全部 193 业务接受及环境门槛分别判断。

本次读取时，`business-sales-pdi-20261001-02` 是 selected 8/8、complete/passed=true；`business-roles-dossier-20261001-01` 是 selected 5/6、complete=true/passed=false；`business-member-retail-reports-20261001-09` 与 `business-repair-packages-claims-rework-20261001-06` 尚 complete=false。四份报告均 `full_registered_suite_complete=false`。此处是读取快照，终局以根代理后续原报告为准；不相加为一次完整 49 场景或 193 项结果。

## 已注册完整检查的静态归属

下表的编号均带 `HK-` 前缀；只列完整合同，不表示本轮执行状态。

| 注册业务脚本 | 声明完整需求编号 |
| --- | --- |
| sales_business | 001–007 |
| vehicle_purchase_business | 018、021、026、029、171、177、178 |
| master_data_business | 170、172–176、179–187 |
| customer_service_business | 098、107–109 |
| sales_order_business | 008–011、022 |
| report_business | 134–138、142–145、160、167 |
| material_business | 045、051、054、061、069、070、072、073、083 |
| system_management_business | 189、191 |
| repair_business | 031、034、044、049、053、079 |
| membership_business | 089、094、117、118、128 |
| repair_followon_business | 032、033、042、080 |
| sales_followon_business | 012、015–017 |
| finance_business | 087、090、091、093、096 |
| insurance_business | 013、014、077、113–116 |
| finance_followon_business | 095、097 |
| system_followon_business | 192、193 |
| report_followon_business | 146–151、155；152/153 单独 partial |
| member_followon_business | 123–125、129、130、132 |
| finance_report_business | 141、161–163 |
| vehicle_operations_business | 019、023、025、027、028、030 |
| warehouse_operations_business | 046、048、050、056、057、059、060、085 |
| boutique_business | 052、058、062、064、074、082 |
| member_points_tier_business | 119–122、131、188 |
| customer_followon_business | 100–104、110、111；099 单独 partial |
| repair_packages_business | 043、126、127、133 |
| interstore_business | 020、024、047、055、084 |
| repair_claims_business | 035、036、039–041 |
| repair_rework_business | 038 |
| report_remaining_business | 139、140、154、156、164–166、168、169 |
| customer_reminders_business | 105、106、112；099 单独 partial |
| sales_pdi_business | 037、065、075 |
| retail_remaining_business | 063、066–068 |
| roles_dossier_business | 190 |

HK030 原题为 **车辆店内移库**，不是库存查询。原 `VehicleOperation.local_move` 新建→不同主管批准→库管实际发出→目标位实际接收，核同 VIN/代次、源位/在途/目的位数量价值守恒和店总量不增；完整合同已在 `vehicle_operations_business.py`。历史 `vehicle04` 所选 3/3 曾整场通过，但不继承为当前源或当前 49 场景的通过。

## 尚未注册的 10 项

| 原题 / 完整 check | 已有未注册候选与最小真实来源 | 当前边界 |
| --- | --- | --- |
| HK071 机构库存查询 | `inventory_scope_business.py`：同轮有限系统员工、两店真实非空物资及原跨店来源；原管理 UI 加二店 auditor→本人切店读取→新店内移库实际在途→接收→恢复原授权 | 不是空目录/集团总数。依赖当前完整 HK190/系统/库存父；当前 HK190 整场失败不能借局部或旧 run 顶替。 |
| HK076 代办服务收款 | `finance_remaining_business.py`：同轮 agency 实际 fee2500/pass1000、Tender 与原 disburse1000，原领域页面和历史实际 native 提交逐一核对 | 已全部收齐也可核真实已收事实，不造第二笔费用或以代缴代店内收入。 |
| HK078 整车收款单调整 | 同候选：同轮 PDI 首款事前 BANK≠ENTRY 声明、原 Cash/Payment 与有限签回；原财务申请→另一主管批准→本人实际执行更正 | 第一款错误编号预先声明；第二款/交付与原库存不变。已交车 correcting 窄修尚须本批新镜像实际验。 |
| HK081 维修收款单调整 | 同候选：同轮核赔客户10元事前声明；更正引用该客户原款 | 保险/厂家正确款、原承担和完成维修不冲回；不事后把正确账称作误记。 |
| HK086 物资收款单调整 | 同候选：Retail A gross2500/refunded1000/net1500，原财务更正及原退款 immutable | Cash 原金额与有效收款分配分别核对，不再执行退款或出库。 |
| HK088 其它收入单收款 | 同候选：同轮客服客户6000实收；厂家10000实际到账→目标7000→原账户实际退3000 | 两张原单、收入/回款/原退款独立事实；不能用净数替代原流水。 |
| HK092 收款单退款申请 | 同候选：同轮取消定金300000和引用 original_id 的原账户实退300000 | 实际取消父完整通过、原申请审批及财务回执逐项核；PDI 后继复用 VIN 不意味着旧取消单实物交付。 |
| HK157 物资应收账统计 | `receivables_business.py`：新普通 Retail 真出库/接收，仅部分实收，保留正欠额 | 采购应付、供应商应收退款不是本题来源。 |
| HK158 整车相关应收账统计 | 同候选：新已复核当前 VIN/签回订单及关联代办，部分实收后保留正欠额 | 既有交付/取消全部结清来源不能冒称非零待收；当前可用 VIN/代次须原重读。 |
| HK159 维修应收账统计 | 同候选：新到店纯 work 维修，经施工质检和承担冻结，客户部分实收、内部承担另列 | 未结清不能接车；原技师移出工位与客户实际离场不同。 |

三类应收均用现有 `#analytics/finance`→KPI“当前尚待收取”→`#table/receivables`、`/api/flow/analytics` 及原 `dataset=receivables` CSV；全授权范围 oracle、全表分页、原单钻取和精确单条 export 审计，不造不存在的应收专图。以上 10 项候选不在当前白名单/注册，不计任何成绩，也不因代码存在自动满足其动态/人工条件。

## HK099：剩余真实日期到期，不换授权模型

原题 **车辆档案**，check `HK-099-business`。`customer_service` 已有本店新增/编辑、真实观察日/里程与原车身份来源；`customer_followon` 补本次实际交付 VIN 的本店 CV/服务历史；`customer_reminders.share_partial` 又实际新建二店客户/CV、明确同一客户集团身份与车辆身份，再从源店主管 UI 授予最小摘要、目标本人读→撤销→目标再次读空、本店摘要保持。三处都明确 partial，没有完整 HK099 check。

还未闭合的硬条件是 **真正到期后不能读取**。原 `HistoryGrant.valid_until` 为业务日期，创建只允许今天至今天+365天；`customer_service.service_history` 仅查 `status=active AND valid_until>=today()`。今天到期仍有效，须真实下一业务日。HK190 `DossierGrant.expires_at` 秒级实际到期是不同表/不同权限合同，不能替代它；也不能用撤销后的空结果证明到期。

最短下一步骤：在同轮明确 CV 对上另经原 UI 创建今天截止的新摘要授权，保留 active、不撤销；当次真实下一日由同目标本人原页重新读取，核外部摘要消失、源本地摘要/原 Grant 截止值与身份关系保持。真正时间越界必须有实际业务时区、前后读取和源/脚本/manifest 指纹记录。若分阶段续验，须根另明确同库延续和完整清单条件；不能新 run SQL 造昨天授权或拼两份不同 run 通过。原单快照/逐件文件共享仍单独走 dossier 原授权，摘要授权不给原 case ID、电话、金额或文件权限。

## HK152：原功能正确的未知分支与完整历史窗口分开

原题 **物资仓库入出存统计**，check `HK-152-business`。准确目录要求 `warehouse_period_balances/baselines/entries` 与 Enrollment/OpeningStock/Entry/StockMove 一致，`complete/closing_complete/period_gap` 分开、指定仓只本库位及本仓发在途。`wf-report-152` 第二步 expected 明确为：“**未知期初与有据期末分别提示；没有来源不能补成零库存。**” required source-integrity 是非空原来源、UI/API/DB/导出同范围、未知保留、查询零业务写；**没有写 `complete=true` 是完整功能 check 的必需值**。

当前 `warehouse_partial` 已核真实 Item/仓选择、当日 `complete=false/closing_complete=true`、opening/in/out null、当前有据期末与原余额相等、三表分页/CSV与期末图。此前精确补丁明确把这一段记 partial，不能直接改旧报告或靠措辞晋级。

可供根另登记的原功能完整检查：保留上述当日来源不足分支；补独立逐库位/在途/基准/原 Entry 的全范围 oracle、所有精确来源缺口与 `period_gap`，实际指定仓/物资筛选及原单钻取、真实图和图原始行 CSV、停用历史选项在有该真实来源时验证、原日期/权限及所有旧行保护。未知列与真实 closing 必须继续分别显示，不能为“完整检查”硬写完整期初。按原合同可把 **功能 check 的闭包** 和 **`period_complete=true` 的未来数据条件**分别记录；本页仅建议，尚未授权实施或执行，业务人工接受仍 pending。

真正完整期间来源的条件不能假造：`warehouse_period_analytics.py` 只在 `start > local_date(实际 warehouse_approve occurred_at)` 且原来源守恒时 `period_complete=true`；原 period 拒绝未来结束日。因此今天刚启用的物资今天无法有完整午夜期初。即使原 OpeningStock 有较早 business_date，也不覆盖库位实际批准桥接时刻。若要额外验证完整期间正分支，应保留原库和指纹，真实下一日从已启用有限 Item 选择合法期间，再原 UI 产生该日真实收/发来源、查期初/收发/期末与图表/CSV；不改钟、回填批准事件或午夜余额。

## HK153：新空白门店的原 UI 正向批次可立即补齐

原题 **物资采购订货统计**，check `HK-153-business`。当前一店 partial 的 four legacy `kind=purchase/v2` 缺不可变逐行订货源，原报表正确 complete=false、全履约金额 null/无单位图；本轮新采购两行/四验收/原退五 posting、三表 CSV 仍真实核对。不能删除旧四行、改登记日期、填零或把已有完整金额声明代替来源。

**源合同可行的最短正向方案不需要改 fixture、日期或权限：**

1. 同轮 `system-management-hk189-191` 完整 passed 的 HK189 `store_actions` 给出原 UI 创建并重新启用的 third Store。`POST /api/stores` 只建 Store/Audit，没有 seed 旧 purchase；先只读断言该有限店 ID 无采购/库存业务，并核 `active=true`。不要猜数字3或重新扫描“最新门店”。
2. 由原系统管理 UI 在现有员工原 store_roles 上 **追加**这家店、保留原店/岗位：一位 manager、一位 inventory、一位 finance 足够；若申请由 manager 创建则必须另一个 manager 批准，改由 inventory 申请可少需第二主管。manager 无 PHYSICAL 权限，`warehouse` 创建/执行及 `procurement.receive/return_dispatch` 不接受 manager，不能借 admin 或临时注入岗位减少真实库管。
3. 每人按原登录及店选择读取本人当前一店投影。UserStore/access_version、原合法 receipt/audit、受影响旧 session 撤销和权限变更信号逐项核；不能在改权后继续用旧会话。当查验结束按原 UI 恢复原角色/店集合，代次只递增，不回写旧 access_version；其他账号/密码/原业务保护。
4. 新店没有原 flow Account，manager 必须原 `#master/accounts` 新建 active bank；另原 `#masters/suppliers`、物资目录、materials 仓及库位创建有限新主档。新 Item qty/value 为0，inventory 原 warehouse activate 明确真实零数量 allocation location，manager 独立批准 Enrollment；不是 fixture 预置采购/实物/款。
5. inventory 原采购新建已声明合成行，例如 2升、10元/升；manager 独立 approve；inventory 原凭据/逐批实际 receive，finance 本人原账户实际 pay20元。再 inventory 对明确原 Receipt 申请退0.5升、manager 独立批准、inventory 原批次实物退、finance 原退款到账5元。期望 ordered/received2000、returned500、retained1500，量值及 original_id 精确守恒；附件按原 security 状态核，仅 metadata/hash入报告。付款与实物仍分开。若只需最低非空正向闭包，可少一批验收，不为报表凑多行或新价格规则。
6. manager 本人明确该店，原 `#procurement-cohort` 填真实采购申请本地日，GET `/api/inventory-reports/procurement`；原日期范围只有新 Order/Line/Receipt/ReturnPosting/StockMove，无 legacy。独立 DB oracle 核 **整店** counts/单位数量/七金额、`complete=true`/issues空、单位图、三表分页与各真实 CSV/图原始行、原新采购钻取和 export 单审计。退货不增加待到货，累计履约截至 as_of，不误称期间到货图。

`procurement_analytics` 按 `procurement_create` 原事件本地日选新单，legacy 只按原 business_date 报差异；缺唯一创建事件的其他新单会无条件列 source issue。因此空白店应保持全范围源干净，不只是过滤掉旧一店行。此方案隔离的是合法原当前门店范围，不是删历史、绕角色/实体规则或在 URL 伪造 store_id。当前无主体策略的合成环境允许原 freeze 无 context，不代表生产经营主体/账户归属验收。根须另登记、实现、审阅并同轮实际执行；本页没有新增 HK153 通过。

## 建议收尾顺序与共同门槛

先完成当前 49 所选运行的终局/失败分类；在同轮有实际完整父后接三类应收、金融六及机构库存，不能复用不同 run 片段。下一最小新增范围为 HK153 空白店采购正向和 HK152 原功能未知分支闭包；HK099 真日期到期保持明确时间条件。全部来源必须当前 runtime/evidence_root 的有限父 ID/版本/附件元信息和真实角色、原任务/CAS/回执，每登录后建立基线，正写只 UI，所有无关/他店旧业务行不变，未知结果停止。

本清点没有发现剩余 13 项缺少原产品入口：主要是未注册候选、来源完整条件、实际时间边界及尚待闭包。应收没有专图属于原界面边界；源不足与已结清不能制造金额。整体 193 仍须六统一标准各自留证：前端正确显示、流程简单、文案简洁、后端匹配、硬 bug、来源完整；人工未审部分不自动填 passed，不声称员工效率提升。原真实模型/PG/Linux/ClamAV/恢复/员工与银行、生产条件和四开关默认关闭均保持独立。

## 本次只读字节锚点

| 文件 | SHA256 |
| --- | --- |
| business_acceptance_catalog.json | eeea5ea2088ac932fe9f725ef1d4bd68073507bd23f695df360ef0036ba8a3ff |
| requirements_manifest.json | 19840f4fc5fd816d94ea35a4602a31bde4674105e44621eeb4cfe42bdad27a1f |
| scenarios.py | 88a6497428d1442fc218109dec23b444c6294ae047f6468bbaa843d86e3c046b |
| run.py | 5693d630a4a63051d0bacc8807fdfe80537e34adcd0f6300a4071bc6ff6b6e53 |
| customer_reminders_business.py | b16cb44633043585d1f9693041bc7cf956891334ee333b0d66894821ba31093a |
| report_followon_business.py | e5a64e700bcb2be119cdbf482b511f1a43c28fc8c793425a969764636900e1d2 |
| roles_dossier_business.py | 1fff6da504507a3b75559f7affdc7cd9478f050e670567abae97730e529c182c |
| inventory_scope_business.py（未注册） | 3801fa5d45cbb727070831b87cc7544388498b3faa014ed6b5a96dcce4cd1b32 |
| receivables_business.py（未注册） | aea7d95803a21a9b0a90c023e83e4f762d07219c60a123835498702c501a4379 |
| finance_remaining_business.py（未注册，保持冻结） | 574a09b697599ed46970330e656bc11600b7433d21e5e71c5f29525391e32096 |

检查方式是静态 AST/JSON、原源码/UI合同对照和外部报告有限字段读取；没有导入候选/app 或执行其场景。各候选变化后须重新以字节核对，不继承本文静态结论为实测。
