# 客户提醒三项浏览器候选

2026-10-01，M8.1。按 PATCH-M8-4-BUSINESS-193-31 及冻结研究页 customer-reminders-scope.md（e5471d56bbec57044c92e295f05c80a914a371eb2cbe996589bf5ea21359c578），仅新增 tests/browser_click/customer_reminders_business.py 和本页。候选尚未注册、未运行；没有导入 app、启动服务/浏览器、修改生产、夹具、helper、runner、目录或计划。静态检查不代表三项业务通过。

## 原范围和真实链

只有 HK-105 保养提醒、HK-106 保修提醒、HK-112 首保提醒回访三个完整 acceptance check。HK-099 车辆档案仅 partial，不注册重复 HK-099-business、不声称真正过期。本批统一 SCENARIO 为 customer-reminders-hk105-106-112，导出 CUSTOMER_REMINDERS_SCENARIOS 单个三元组，固定 1500 秒。

- HK105：本人登记新 VIN 的 D−30/1000 公里交付资料及独立 D−1/4900 公里实测资料；主管原 maintenance 周期30天/提前0 → 全店实际生成 → 原 service 接手/内部跟进。原 delivery 有据更正为 D−29，申请人本次原件提交、另一主管独立批准；开放旧提醒 cancelled、原 Task 关闭而原观察/跟进历史保留。规则实际改提前1天 → 有效基准生成精确 Replacement → 本人接手/两跟进/预约结果结案 → 再检查同周期不重复。
- HK112：first_service 仅公里周期4000，提前99时4900未到4901阈值，原维护为100后恰触发4900；本人接手/两次跟进/预约结案。另行原 UI 登记本车 D/5000 公里、独立合成现场资料的首保完成观察；再次检查抑制后继。回访预约不冒充已完成首保，实际观察与联系分别留据。
- HK106：warranty 本车 D/5000 公里、明确截止 D+9。规则只提前天数，8不触发/9触发，原办理至结案并核同周期去重。对该人工误登记 warranty 原观察另建 retract 申请/本申请原件/独立批准；旧 completed 提醒保持 Case/Task，仅追加 Effect/Invalidation/跟进，失效期限不再生成。

原提醒 UI 在基准待复核时确实只提供内部跟进并隐藏结案。候选核对原可见选项和实际内部记录；不从不可见 phone 选项制造请求，不声称已执行原服务器 phone 409。所有日期来自 Asia/Shanghai 同一业务日并与实际日期输入默认值、生成 as_of 核对；执行跨日整体失败，不能拼接临界值成绩。

## 同轮闭包、身份和资料

直接父 customer-followon-hk100-101-102-103-104-110-111 与 system-management-hk189-191 必须在本轮原报告/checkpoint 完整 passed，目录及镜像指纹一致。读取父客户/已交付 CV/原订单及非空 HistoryLink、HK191 原创建 receiver 的有限 ID/逐店岗位。若本轮 system-followon-hk190-192-193 已执行，也要求完整 passed 和临时审计授权真实恢复，并重读当前原 UserStore。

原销售 sales_peer 对本人客户登记并编辑另一新 VIN；本店 service 办理原观察及提醒，manager 配置规则和独立复核。二店接收员工是系统父真实 UI 创建且已实际修改初始密码、启用的账号级 sales/current-store service，不借 admin 办理。仅读取本轮 runtime 私有指针内当前密码阶段，整份私有账号密码字符串进入 secrets，密码、User.password_hash/会话 hash 不入证据，也不重置原员工。

HK099 partial 用父已交付 CV 的原非空本地摘要：二店本人原 UI 独立新增同姓名/电话的客户，明确来源页集团客户身份编号及交付 VIN；客户身份与车辆身份分别匹配。来源主管原 today 截止的 history/grants → 接收员工原 CV 页面读取仅八个公开摘要字段（无外部 case_id、金额、电话、原单按钮或文件）→ 最新 grant version 明确撤销 → 再读无外部摘要。本地摘要不动。真正截止日次日的到期、原单快照及逐文件授权继续 planned_pending；没有改时钟、SQL造过期或把撤销称为过期。

## 有限事实守卫和原合同

每次 generate 独立 SELECT 本店全部 active CV（最多500）、全部 active Rule、有效原 Observation/CorrectionEffect/InsuranceInvalidation、待复核 Correction、旧 CareCase/Task/Basis/Invalidation/Replacement。按原日期或独立公里阈值、有效首保抑制、旧周期状态与 closed_open_task、真实经办/批准当前岗位、reminder_key 重算完整应生成和 skipped 集合。对实际已 terminated 的每条关联保险源核对同报价 issued/原观察、独立 review、匹配 consent/方案摘要、Application/原件及已有精确 InsuranceBasisInvalidation；未知待同步来源直接停止，不豁免保险表或猜来源。

全店生成仅允许枚举 CV 的 version/updated_at touch；每个新提醒精确 Case+Care+Task+Record+Basis、两 Event/两 Audit，Replacement按准确旧取消单追加，整体一条 CorrectionReceipt。即使0生成仍逐车核版本前进和唯一回执。冻结 Basis 完整 baseline/current/effects/规则快照、每个原 Task 和创建责任、所有后台合成候选一起核对，不能只看本批一车。

所有正向写均实际原可见表单点击一次；创建响应绑定新 POST ID 后的正确原 GET，不接受旧实体响应；Cookie/CSRF/当前店头/原 request_id、输入/CAS、CareReceipt 与 CorrectionReceipt `[action,payload]`摘要及完整结果分别核对。纠正审批有限关联 Case/Task 允许原列，已结案提醒不更新，原观察/原记录/原回执不可覆盖。独立主管按原动作权限复核，原自动复核 Task 的不同 assignee 如实保留，不借 admin 或改任意权限。

每次 Guard 核全部业务表哈希与全部旧行，不删除旧行、只给有限 ID/列和精确新增数。库存、Cash、会员、原销售/维修、其它店全部保持；原登录审计完成后才取业务基线。附件由原 UI 上传本申请 evidence，真实 structure_only/本单可用、字节/length/SHA核对；BLOB只内存比较，报告仅元数据，不用 default=str/base64。结构扫描不代表 ClamAV 验收。

## 静态收尾与待测

根补核：REMINDERS-REGISTER-01将optional系统后继名称精确对齐实际system-followon-hk192-193，以保证联合已执行时重验passed/权限恢复；独立窄审全店集合/纠正替代/双身份摘要/私有指针脱敏通过。仅静态接线，不登记任何业务passed；后继新镜像优先最小依赖闭包。

本候选已完成 AST、所有数据库读取 SELECT-only、有限表名白名单、三个原目录题名/check绑定、既有 helper 符号及三元导出形状静态核对；空白差异检查通过。源码和文档 SHA256 在交接消息单独记录，避免自包含哈希。未执行任何应用、业务或浏览器，所有 checkpoint 初态 not_tested；只有后续真实整场成功才可输出三项自动 passed，人工体验/简洁文案仍 pending，全193/PG/Linux/并发/超过500车、未知保险待同步、真实联系和现场服务、跨日到期、原单逐文件权限、ClamAV与生产门槛不变。

静态来源14文件（同研究页路径清单）本次指纹 a22848717ffc203105131e2aa8259f53f2b5cced2c94e5679e4c0c03caa5f431，原目录仍 eeea5ea2088ac932fe9f725ef1d4bd68073507bd23f695df360ef0036ba8a3ff；这不是父场景 passed 证据，实际执行仍读取当次 provenance 和完整 checkpoint，不能继承研究时旧镜像。候选1176行、11处数据库调用全部 SELECT-only，五个既有 helper 模块的被引符号经 AST 核对。
