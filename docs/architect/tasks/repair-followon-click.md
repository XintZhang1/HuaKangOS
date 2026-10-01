# 洗车、快捷维修及客户直接报销候选

2026-10-01，依 PATCH-M8-4-BUSINESS-193-12 及冻结设计 `repair-followon-scope.md`（SHA256 `e3f3f2dc3d3c2092b05e324781dff83080d163c5cb49f2b891f6369c6c97c985`）新增独立 `tests/browser_click/repair_followon_business.py`。本任务仅写这份候选及本页；生产、fixture、目录、首维修、注册和其他脚本未修改，没有启动应用或浏览器。

## 两个入口

导出 `REPAIR_FOLLOWON_SCENARIOS`：

| 名称 | 函数 | 超时 | 独立完整检查 |
| --- | --- | --- | --- |
| `repair-wash-quick-hk032-080-033` | `wash_quick_business(e, context, credentials)` | 300 秒 | HK032 新洗车完整原链；HK080 同洗车真实收款；HK033 另一新快捷维修完整原链。 |
| `repair-customer-reimbursement-hk042` | `reimbursement_business(e, context, credentials)` | 180 秒 | HK042 首单原自费款的客户直接报销，核价、独立批准、外部提交/结果、另一主管报销批准及实际客户支付。 |

负责人把候选加入同次外置镜像 SCRIPT_FILES 和现有场景清单，按首维修→洗车/快捷→报销排序。候选复用首维修小型 UI/只读 Guard、原主档保存及现有登录/候选选择助手，不新建 runner、服务或通用测试框架。代码存在与静态审阅不表示这些检查通过。

## 硬前序及有限来源

两个入口均先确认同一 evidence_root 的父 `browser-click-report.json` 注册且记以下场景 passed，再读取其固定 complete/passed checkpoint、目录 SHA 和运行 provenance：

- `repair-selfpay-hk031-034-044-049-053-079`：六项原检查须全部通过，顶层 `report_sources` 精确 11 键 customer_id/customer_vehicle_id/vin/appointment_id/intake_case_id/repair_case_id/quote_id/allocation_id/payment_link_id/cash_id/material_item_id。只按这些 ID 重验本店原客户、原 CV/身份、接待、唯一 Quote、真实客户 Allocation→RepairPayment→PaymentLink→Cash 及唯一实际 release；原付款行须仍与 HK079 实际证据一致。
- `master-data-hk170-172-173-174-175-176-179-180-181-182-183-184-185-186-187`：只取 HK172 原 UI 生成、当前启用的保险公司 row。
- `materials-hk069-045-054-083-070-072-073-051-061`：其 primary.item_id 必须是首单材料源；只记录当前物料/余额/历史。不继承原主档零库存或旧 current_version/余额相等。

报销入口另要求 **本次洗车/快捷场景 passed**，按其 wash_sources/quick_sources 的有限维修/工位 IDs 重验两单已实际接车、唯一 release、工位已经释放。缺来源、未注册、前序 partial/failed、不同目录/镜像/运行一律明确失败，不扫描数据库挑旧单，不跨 fresh 复用结果。

原 CV 已由首单到店、开工和离场改变版本；当前按有限 ID 重新 SELECT，核稳定客户/VIN/身份，不把客服旧行或首单早期版本整行相等当条件。每次登录/原岗位交接后再取得该动作的业务基线；原 CAS 以页面真实当前版本提交。

## 洗车与快捷各自输入到结果

manager 原 `masters/work_items` 表单新增本批明确作业：洗车 10.00 元、快捷检查 20.00 元，均 job/数量 1.000；标准工时 20 分钟、质保 0，未虚构配件。manager 原 `service-intake/resources` UI 新增 wash/repair 两工位和 profile=wash/quick 的两个 QuickPreset，每组合仅本次 WorkItem 一行 1000 milli。原 POST 返回 IDs，组合/原作业在转换期间不改变；不把这些配置重复计成 HK175。

service 依次对同 CV 新建两张 walk_in 原接待，选择真实工位及对应组合，明确页面当前排队时段、客户诉求；原文件上传、实际 VIN/里程 32101/32102 的 arrive、convert 各自产生事实。没有 fixture/SQL 创建 ArrivalFact/GateVisit。第一新单实际 release 后才开始第二次到店；原 guard 继续校验同 VIN 无重叠，不依据计划时间自动离场。

转换由原业务生成初版 RepairQuote/RepairLine：本次 profile/preset/appointment/resource/CV/VIN、作业 ID/编码/名称/单位、1000 milli、原参考费/逐行金额、唯一 Quote 和 digest 全部核对。转换结果必须 approval，不能再提交一个 quote 覆盖预填。manager 独立核价→service 本版客户授权→technician 实际 start/acquire 和 finish→service 本版 quality 合格→manager 客户全额 allocate→finance 原账户/独立凭证实际 receive→service 实际 release。

两单合成人工成本事先明确为 2.00/3.00 元，按整数分核原 Settlement/Case，不从收费反推；无配件组合不得生成领退料或材料变动。每个报价/审批/授权/施工/质检/承担/到账/接车分别留原事实和原任务本人身份。

HK080 在实际 receive 后独立记录客户 Allocation、RepairPayment、PaymentLink、Cash、当前原启用银行账户、精确金额/凭证/日期及 actor；此时尚未 release。HK032/HK033 完成必须实际接车、唯一工位 acquire/release、原任务结束。两单刷新全业务摘要零写入，原 Cash/Link/Quote 不重复。原普通维修及其材料当前行/历史在整组前后保持，不把普通维修六项重复计入新增通过数。

## HK042 客户直接报销

从首单 `repair-orders/{明确ID}` 原“建立核赔申请”按钮建立新 customer_direct Claim，明确原客户/首单当前 version、本轮实际保险公司。只选择原首单作业行，数量 1.000、核价金额为该原行实际金额（不得超过原款），配件行取消选择。不是把上传或外部文本当核准。

service assess→不同 manager approve→service transmit 独立合成受理号/实际日→service result 当前 transmission/assessment 的逐项 approved 金额及实际结果日→另一身份 manager reimbursement_approve→finance 当前 claim_reimburse 本人 direct_confirm。manager 不得等于申请/核价/result 经办人；demo 任务负责人只由 manager 原 UI 按原 version、assignee_id、reason 交接，不借 admin。

每步原 Claim.version 与首维修 source_version 都用当前原页面返回，SourceGuard 只允许新 Claim 事实、该 Claim Case/Task 的明确状态列，以及首维修 updated_at/version；首维修旧报价/授权/领料/质检/承担/款/历史、其他客户或门店均不允许改变。已批准/已付占额按原 `customer_reimbursement_available` 校验，会员权益不折现。

核价审批、提交、实际外部结果、报销审批的每份独立字节文件原上传类别 authorization；实际第三方付客户文件为 receipt。`claim_file_choice` 同时要求原表单 data-file-requirement 与正确类别一致。负责人已登记 PATCH-M8-1-CLAIM-PROOF-FIELD-01 精确修动作提示，后端 `_proof` 不放宽；结果表单原 select 选择本次正确原件，其他动作原可见 lookup 选择正确文件 ID。

direct_confirm 的原字段只有实际 amount/evidence，没有门店账户或 reference。核唯一 `claims_customer_payments(purpose=reimbursement)` 及 amount/day/actor/evidence、原审批与 Claim completed；不允许新增 Cash、PaymentLink、RepairPayment、ClaimCash 或原第三方承担绑定。源码会 touch 原维修当前版本，但其已完成状态和旧款保留。刷新不能重复客户支付。门店转付、拒赔/补件、调减、返还、跨店均为 conditional/not_tested。

## 保护与报告

正向业务全部实际原 UI 提交；网络只观察同源 Cookie/CSRF/当前店的原响应，数据库只 SELECT。每个原 submit 的全业务摘要和旧行保护限定本动作 append 表及有限旧 ID/列，不粗排除现金/库存/会员或整表。文件检查保留原 structure_only、实际存储长度/哈希，不记录原字节正文；候选依赖首维修 upload 的窄修接口。`note` 先验证证据 JSON 可序列化再更新当前 check，避免 BLOB 污染阻止失败终态保存。

每个入口自己的 `business-checkpoint.json` 含逐 HK/check 状态、实际 action 区间、原 UI/API/DB 证据和失败，失败时活动项 failed、其他运行中项 partial，整场景 incomplete。空入口或未执行不可通过。两组分别输出：

- wash_sources/quick_sources：customer_id/customer_vehicle_id/vin/resource_id/preset_id/appointment_id/intake_case_id/repair_case_id/quote_id/allocation_id/payment_link_id/cash_id。
- claim_sources：source_repair_case_id/source_quote_id/source_allocation_id/source_payment_link_id/source_cash_id/claim_case_id/assessment_id/transmission_id/result_id/reimbursement_approval_id/customer_payment_id。

HK081 只有原接口设计，无已声明误记事实，本批不注册、不冲正确现金。报销已批准占额后不能为补覆盖冲原款。人工 simple_flow/concise_copy、真实保险审批、真实银行/物理履约、保安进出厂、ClamAV、经营主体策略、PostgreSQL及员工试用均未验收；business_accepted=false/full193=false。静态检查只说明候选可交统一实际运行，不登记四项通过。

## 静态冻结交接

候选 737 行，SHA256 `0bfa02d61b3e38499a5b9c95f9ede320d23d859991cd6105a0e8c983b27ded00`。AST、所有本地导入符号的源码解析核对、空白检查通过；未出现 app 导入、直接 HTTP 写、SQL 写、evaluate/route 注入、固定 sleep 或 force/trial 点击。未执行任何业务实例/浏览器。原 repair helper 此时由负责人维护的 SHA 为 `66aa1e43195d915314262a91ccd06d887209c966343f20b52a8c38dd33d441db`，候选在统一运行中仍以该次 provenance 实际值重验，不把本静态值当后继通过。

已逐项核对原 enum/select 的 native value；原 claim-new/交接如位于关闭 details，先真实点击祖先直系 summary 再点原按钮。既有原 command 等成功 POST 与对应 GET 的 JSON/body 完成、modal 隐藏和原业务标题显示后再读事实，不以瞬间旧 h1 可见当渲染完成。实际动态时序、源条件变化、金额/占额拒绝、岗位转交及超时只能由本轮真实执行判断，首次失败原件保留。

## 注册前独立短审

2026-10-01，test_inventory 对上述冻结候选与本页完成独立只读短审，核对时脚本 SHA256 仍为 `0bfa02d61b3e38499a5b9c95f9ede320d23d859991cd6105a0e8c983b27ded00`，当时文档 SHA256 为 `c0fef4adfbdede8498548655a0e76501605aed283d8910c0a260b0142bfc5d08`。未发现本批明确静态合同误配，没有编辑候选、导入应用或运行实例。

短审逐源核对了 QuickPreset 转换自动生成原报价、同 CV 原到店转换与真实工位 acquire/release、洗车收款及客户接车的独立事实、原任务接手人与 CAS。HK042 的 Direct schema 不含账户和流水；原 `direct_confirm` 只追加 ClaimCustomerPayment，不生成门店现金。候选的有限 Guard、无新增 Cash/PaymentLink/第三方承担绑定，以及首维修旧事实保护与该合同一致。

这次登记只补充注册前代码审阅证据。首维修或其它既有场景的通过不转为 HK032/HK080/HK033/HK042 通过；四项仍等待负责人在同指纹隔离实例实际执行，并保留各自人工体验及真实外部条件边界。本次只更新本页，候选脚本冻结不变。
