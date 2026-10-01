# 同次原业务来源的 11 项报表点击候选

2026-10-01，范围依据 `PATCH-M8-4-BUSINESS-193-06.md`。只新增 `tests/browser_click/report_business.py` 与本页；未注册、未执行，不修改生产、fixture、run/scenarios、共享目录或计划。沿既有 Evidence、SELECT-only 数据库证据与外置 business-checkpoint，不新增运行框架。

候选导出 `REPORT_SCENARIOS`，场景 `reports-hk134-135-137-138-142-143-144-145-160-167-136`，最大窗口 360 秒。仅使用本店真实 manager。先读取同一 `manifest.evidence_root` 的稳定 provenance 与售前、采购、销售交付、独立退订四份完整逐 check checkpoint；绑定镜像脚本/193 目录指纹。售前来源取 HK007 明确原 Case/Customer；采购来源取 HK021 原采购、付款、两车验收。销售 `sales-order-hk008-009-011-022` 的顶层 `report_sources` 必须明确提供 lead_id/customer_id/delivered_order_id/delivered_vehicle_id；独立 `sales-cancellation-hk010` 的同四键须一致，另有 cancelled_order_id。不能从交付 checkpoint 推测尚未办理的退订。缺前序或缺 ID 即失败，不从旧 fresh、demo 成交或 SELECT latest 猜来源。前序原单进入后继时允许其真实状态推进，不要求旧阶段快照仍等于当前全部行。

| 逐项 check_id | 原入口与独立核对 |
| --- | --- |
| HK-134-business | table/leads；本轮接待客户、接待日、曾转意向与明确订单 parent；同门店完整批次独立 SELECT 基数，与 cohort 指标、原图、明细、CSV一致。背景只用于本图口径核算，不继承业务成绩。 |
| HK-135-business | 相同原表另留证；区分 current converted、原 intent 事件和截至本次的订单后继，不虚构 intents dataset。 |
| HK-137-business | table/orders；同次交付与退订单各自业务日、原累计实款、约定金额、成本及订单计数；取消仍是建立过的订单，不能按交付计数。 |
| HK-138-business | table/deliveries；仅真实交付原完成日、金额与原单，排除未履约退订，原交付图与导出一致。 |
| HK-142-business | 同 deliveries 原表单独核原采购成本快照、交付金额减直接成本；全范围缺成本仍 null、待核对，不把直接毛差称净利润。原 sales 毛差指标与交付金额图分别核对。 |
| HK-143-business | vehicle-period；两台本次原 PurchaseMovement receive 与 Receipt 的 VIN/库存代次、日期、数量、价值；非空入方向独立原单及 CSV。 |
| HK-144-business | 同原期间入出库；本次销售实际 dispatch 事件与 PositionEntry 唯一来源，非空出方向，不能复用入记录替代。 |
| HK-145-business | 同原日期入口，没有 UI VIN 筛选；本轮两 VIN 逐代次期初0/入2/出1/末1与整数成本守恒。新 VIN 缺源必失败。历史背景缺源保持 complete=false、合计null、图抑制；在途 complete 分列，非空在途及全店完整来源仍未验收。 |
| HK-160-business | table/cash；同次采购支出、交付实收及未履约原款退款各独立 CashEntry/PaymentLink，日期、方向、账户、凭据、金额和原单；现金定义7，原分类图/指标与全部原现金明细同范围。 |
| HK-167-business | table/customer_value；明确 GroupIdentityLink 或 store+local_id token；本客户交付净额、原单、详情和本客户 CSV；取消订单预收及原退款不成为成交收入，不按同名/电话归并。 |
| HK-136-business | 最后打开 visit-activity 并原 UI 选择同次 lead；真实 remind/intent/follow 事件与发生日、内容、次数；未来 due_date 不额外增加沟通；原 intent→converted 迁移、4个已闭阶段/精确时长、阶段均值和原 CSV。当前 converted 不得继续挂意向开放阶段。 |

UI 从原统计分析模块按 HK 编号检索并点击真实入口，实际填日期，逐表核原分页、原图 SVG 数值，点击明确原单；客户价值从本客户归集行点击钻取。正例 HTTP 全部由原 UI 产生并观测同源 Cookie、实际店范围，未使用 context.request 或 fetch 替代点击。原日期口径分别为接待/订单 business_date、实际交付完成日、库存实际出入日、现金发生日与沟通当地日。

CSV 通过原页面导出按钮和 Playwright 原下载事件保存于本轮外置 evidence/exports；按 UTF-8 BOM、csv.reader 解析全部行、保留表头/顺序/原导出公式防护差异。flow 原 CSV 对负数字符串也加引号，库存/沟通导出保留可识别负数，不擅自统一格式。导出 GET 合法写审计：每次核唯一新增本 manager/本店 export 的 entity_type、reason、entity_id、空 before/after，旧 AuditLog 原始每行保持不变，其余业务全行摘要保持。未粗排除整张 audit_logs，未只用计数掩盖覆盖。

HK136 当前存在静态源码缺口：`sales_quote_service.create` 把 lead 改 converted，`sales_quote_convert` 的 before_state 默认空；`visit_activity_analytics` 与 `presales_stage_analytics` 未识别该动作。候选严格断言本轮连续原迁移及已闭阶段，先保存实际报表/缺源提示/截图再失败；前10已做证据保留，整场不得 complete/passed。不以缺源提示保护代替本轮新事实通过，不在此测试补丁修改生产。后续需真实报价后复现，由根另登记修复。

其余25项本候选不执行：HK139/140/141需实际加装客户验收、代办履约、保单/独立佣金及实款；HK146–149需预约到店、维修报价/结算/领退料；HK150–156及157/159/161需物资采购到退货、实物流动、精品实际履约/施工、应收与原成本；HK158需销售真实尚待收阶段，本次全款交付及退款结束后空表不能通过；HK162真实 FinanceAdvance 不是销售定金 PaymentLink；HK163需实际对账 Batch/Issue/Event/Receipt；HK164需原人工登记的有效 CustomerVehicle，销售/采购本身不会代建；HK166需实际服务进出厂来源，PDI与销售出库不是进厂。HK168/169需真实积分/券变动与原规则版本。HK165另待核：原 deliver 在客户允许联系时可能自然建立 parent=销售原单的 callback，可由同次真实原来源后续验收，不一概认定无源，也不把 HK006/007 售前提醒充当回访任务。首批保持11项不扩。

逐 check 状态只记录本次自动 UI/API/DB 结果；simple_flow/concise_copy 人工审阅 pending、business_accepted=false、full_193_business_acceptance=false。全36、集团、非空在途、其他历史期间、真实银行/实物、PG/Linux、真实模型及员工验收保留独立边界。尚未执行候选，源码审阅不记 passed。

根后续实际记录：销售/报表Fresh03观察到页面一次CSV GET但两条精确原export审计，随附驱动在响应正文缓存为空时可能CDP重新带Cookie读取原URL。根移除下载完成后多余response.body，保留原完整文件/行数与单审计守卫；Fresh04前10项CSV均通过，HK136严格失败，原迁移来源生产缺口真实成立。PATCH-M8-1-PRESALES-QUOTE-SOURCE-01修复真实before/model及两原读取；Fresh05同次所选5/5、11项本报表全check通过、退出0，生产5394dedb…、脚本7fbb2c7b…。不把前三次失败或10项诊断拼为整场成功。

IAB新serve01原导出出现503/OperationalError、零审计；02一次正常，不覆盖已知间歇问题。原错误没有扩展码，不冒称517。PATCH-M8-1-REPORT-TRANSACTION-01四文件显式审计GET在SQLite鉴权/读前保留writer，PG/普通GET不变，不retry；无app外部scratch仅诊断同类WAL升级517，不计业务。短审核FastAPI缓存同Session及依赖顺序；03实际IAB原点击成功/一条export审计、正常退出。automatic-business05同新生产6be81a7b…/脚本1f2bbfb4…当前本报表已全11通过，完整21联合运行尚未结束。人工评分及193验收继续pending/false。
