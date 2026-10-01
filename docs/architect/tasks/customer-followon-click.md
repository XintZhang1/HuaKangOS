# 客户回访、问卷与其它收入原生点击候选

2026-10-01，精确范围为 `PATCH-M8-4-BUSINESS-193-24`，依据已冻结的 `customer-remaining-scope.md`（SHA256 `30dff1c913c432b11d5db1e6742447a7c9d4c76e7970a273bf4621916d9fa148`）。本批仅新增 `tests/browser_click/customer_followon_business.py` 与本页；生产、夹具、共享 helper、runner、注册、原需求目录及计划保持只读。本页是候选交接，没有登记浏览器实测通过。

## 入口与同轮有限前置

`SCENARIO = customer-followon-hk100-101-102-103-104-110-111`，函数 `customer_followon_business(e, context, credentials)`；导出 `CUSTOMER_FOLLOWON_SCENARIOS = ((SCENARIO, customer_followon_business, 1200),)`。根代理在相关验证进程收尾后负责镜像和注册，作者未启动应用或浏览器。

固定读取当前 `evidence_root/browser-click-report.json` 中已注册、实际 passed 的七个父场景，以及各自同 root 的完整 passed `business-checkpoint.json`：

1. `sales-presales-hk001-007`。
2. `vehicle-purchase-hk171-177-178-026-021-018-029`。
3. `master-data-hk170-172-173-174-175-176-179-180-181-182-183-184-185-186-187`。
4. `customer-service-hk098-107-108-109`。
5. `sales-order-hk008-009-011-022`。
6. `materials-hk069-045-054-083-070-072-073-051-061`。
7. `repair-selfpay-hk031-034-044-049-053-079`。

同时核外部 `provenance.json` 的稳定镜像、当前脚本/目录及父 helper 哈希、原需求目录 SHA、相同 source/runtime/evidence/database 路径。没有父场景实际通过即明确失败，不扫描旧单、取“最近一张”或拼不同运行。有限数据来自销售 `report_sources` 的已交付 order/customer/Vehicle，首维修十一键中的 CV/customer/repair，以及采购 HK021 明确 payment.account_id；客服 HK099 本店 partial 只证明该原维修 CV 的来源。当前 CV、客户及账户重新读指定 ID，不要求后继业务合法变化后的 version 或余额仍等于旧 checkpoint。

已有本店 service、manager、finance、sales_peer、reception 和不同于 manager 的 admin 有效身份可复用，没有新夹具或业务成果前置。admin 仅独立复核问卷；不代办回访、收款或本人意向任务。两个 VIN 必须不同；原交付和维修均已完成，客户联系意愿及合成电话明确。当前无经营主体策略的本地合成路径不等于生产实体/账户归属验收。

## 七项逐合同路径

| 完整自动检查候选 | 原输入到结果路径 | 原证据 |
| --- | --- | --- |
| HK-100 其它收入单 | manager 原 UI 首建本次60元收费项目；service 新 `other_income`，数量1次、60元净费→另一 manager 核价→客户当前版授权→service 实际办结→finance 原银行账户实收60元 | 原 Quote/Line/独立 PriceApproval/Authorization/Fulfillment 完整保留，只有最后真实收款生成一笔 Cash、PaymentLink、fee TenderSlice；客户原款、履约与两个审计分别核对。旧服务单不再次收费，无代缴、预收抵用或额外资金批次。 |
| HK-101 问卷设置 | manager 提案三道明确必答题，另一 admin 展开逐题后批准；service 发放A并接手；再提案/独立批准另一版并发放B；A先真实缺答拒绝，再完整0/否/choice结案，B完整1/是/另一choice结案 | 两版 Version/Review、各发放 Binding/原题/hash及两个不可变 Response/CareRecord。旧A不改为B；原空回答422未留下答卷或任何业务变化，同一原表单明确补充答案后提交，不重放未知结果。 |
| HK-102 车辆销售回访 | 原已交付 VIN 经原客户车辆 UI 登记，再选择对应 delivered order，service 本人接手、电话与当面两次联系、按已解决结果结案 | 原 CareCase/source_case_id、责任 Task、五条 CareRecord/FlowEvent，本人/本店/日期/方式/结果一致；交付单不被修改。 |
| HK-103 意向客户回访 | reception 原 UI 新客户接待→manager 明确原候选分派给 sales_peer→本人转 intent→两次本人 follow→今日原待办打开同单 | 原新 Customer/lead、精确 current version/request_id 回执、两条追加 FlowEvent、同一 open follow Task。旧已 converted 销售父 lead 不回退，Care 回访不替代意向记录。 |
| HK-104 维修工单回访 | 只取首维修指定当前 CV 和已完成 repair，service 本人新建、接手、电话/当面两次联系、原结果结案 | 对应另一 VIN/客户的 CareCase、五条实际记录/事件与已结束责任 Task，原维修、Cash、领退料及接车事实全部保留。 |
| HK-110 客户回访查询 | 分别原列表 subtype/status/单号查两类已结案回访，再点唯一原办理入口 | 原 GET 参数、非空唯一 Case、原客户/VIN/源单/责任人/期限与七列 DOM 精确对照，查询零业务变化；q 仅单号/主题，不声称姓名或电话搜索。 |
| HK-111 跟进记录查询 | 两类原回访逐条查 actor/time/channel/result/note，并原生刷新；另由本人打开新 intent 单、真实展开“操作留痕”及两条独立详情，再刷新 | API/只读 DB/可见时间与正文逐项一致，全部原记录只追加、不覆盖、不重复；CareRecord 和原意向 FlowEvent/Task 分开。 |

问卷原报表使用同一当前业务日（Asia/Shanghai），独立 SELECT 全部本店获权 Binding/Response/CareRecord 计算发放、结案、逐原题回答及分布；原 API 的完整 tables/charts/metrics 严格对照。真实点击每图同源明细及所有分页，核原 SVG 每个条形数值；三个整表 CSV 与两版整数/布尔题的精确版本/hash/key CSV 实际下载，逐行核全部字节解码内容与原范围；每份导出只允许一次准确原审计。再从原答案表钻取本次实际问卷。不同发放与结案集合不相除冒充回收率，未回答不当作否或0。

## HK099 本店子范围与明确未测

本批经原 UI 登记新交付 VIN 的客户车辆、维护已知车型与空车牌，并登记本次明确合成交接里程表读数0公里和实际交付日期。0是明示合成输入，不从价格、库存状态、保险或另一 VIN 的观察推算。关联本次原销售和原销售回访的最小本店服务摘要，保留真实原编号与确认人。只记录 `HK-099 status=partial/local_scope_passed`，不提交其完整业务 check。

跨店双方身份/CV、摘要授权、原单快照与逐文件独立授权、撤销/过期及有据原观察纠正未执行；HK105/106/112仍下批。本批没有外部短信、真实客户电话、公司真实合同批准、正式支付/到账或员工试用验收。浏览器里联系及收款是明确合成输入对应的原事实，人工和生产门槛保持。

## 旧行与身份保护

全部正向写只使用真实登录、可见原选择器/原生 enum 与唯一原确认点击；没有正向 API request、SQL 写、app 导入、前端 state 注入、fetch 替换、force、sleep 或写入重试。每次登录审计落盘并收到真实原 GET/h1 后，再建立业务基线。

本人 `Guard` 对全原业务摘要和有限表逐旧行比较，仅放行本动作准确 append 数、指定 Case/Task/CV/Policy/账户必要列；所有其他旧资金、库存、会员、附件、问卷版本/Binding/Response、CareRecord、身份和他店均保护。新原单/客户/责任人/门店/原 source 及原 receipt digest 单独核，角色交接沿已验证原 helper 的本人任务/独立主管路径。其它收入复用 helper 的原附件只报告 hash/长度/security 元数据，不持久化 content bytes；内存旧行保护保留真实原 bytes 比较。

拒绝、输入草稿、查询、刷新、原记录展开均零业务变化；问卷发布只允许当前 policy 的必要 CAS/发布列，新旧版本不可覆盖；CSV仅追加一次原审计。金额使用整数分，日期明确 Asia/Shanghai，SQLite JSON字段先解码，0/False按原类型分别核对。

## 外部结果和登记边界

外部 `business-checkpoint.json` 七项各保留稳定 check_id、实际动作区间、UI/API/DB事实与保护结果；失败准确归当前项，已局部通过不把整场补成 passed。只有七项全部实际 passed 及HK099本店子范围完成时才写顶层 `report_sources`：交付/维修客户与 CV、新收入单/Cash、两回访、新 intent 和两问卷原 ID；没有成功前提前输出成果。`business_accepted=false`、`full_193_business_acceptance=false`，simple_flow/concise_copy及其他人工体验判断继续 pending，不虚构效率成绩。

本候选已逐原 `customer_service_api/service/models`、`questionnaire_service/schema/models/analytics`、`service_orders_api/service/models`、`flow_api/engine/customer_choice` 和实际 `customerservice/customerchoice/serviceorders/app.js` 核合同。轻量检查只 AST、稳定原题名/checkIDs、三元导出、SELECT-only、无app导入和空白，不执行候选或应用；实际动态时序、可见折叠/分页、角色候选及下载仍待根新镜像复验。

2026-10-01 作者静态冻结：脚本1225行，SHA256 `c3b649bffb9919d2f0c8df5f43a84501220f931a64db65ccb592e755785ca787`。AST、七个原标题及稳定checkId、1200秒三元导出、无app导入、直接SQL均SELECT、无注入/force/sleep/正向API请求及空白检查通过。仅此静态结论；候选未注册、未镜像、未执行，七项尚无本批passed成绩。根安排独立短审和首次实际点击，作者两文件在冻结后不继续写入。
