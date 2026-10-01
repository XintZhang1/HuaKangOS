# 原维修核赔五项点击候选

2026-10-01，精确范围 PATCH-M8-4-BUSINESS-193-27。只新增 `tests/browser_click/repair_claims_business.py` 与本页；生产、fixture、原 helpers、目录、runner、注册及计划保持只读。当前是未注册、未运行候选，没有业务通过或人工验收成绩。

导出 `REPAIR_CLAIMS_SCENARIOS=(("repair-claims-hk035-036-039-040-041", repair_claims_business, 720),)`。每项独立稳定 check 为 HK-035/036/039/040/041-business，题名与原193目录一致。失败记录当前项并将其余 running 终止为 partial；全部五项真实通过后才输出 complete/passed 与有限 `repair_claims_sources/report_sources`。

## 本轮固定前序与原输入

只读当前 `evidence_root/browser-click-report.json` 与七个固定同根完整 checkpoint：售前、整车采购、主档、客服、整车交付、物资、首维修。每个父必须在本次 expected 列表中且 runner passed、checkpoint complete/passed、目录和 provenance 一致；候选及复用 helper 文件逐个核对本次镜像指纹。不扫描别次数据库或找旧 demo 单补来源。

原客车取首维修十一键中的 customer_vehicle_id/customer_id/VIN，再对客服 HK099 的本店局部源逐项核稳定身份；CV 版本、里程、当前材料余额即时重读，不要求旧整行或旧库存余额相等。首维修必须 completed，原车辆绑定保持。取主档 HK172 的 insurer、HK175 原 WorkItem，物资 primary 的有限 item；本次只做三项纯作业，不额外消耗材料。原账户取采购 HK021 实付 account_id，并核与首维修原款同源、本店启用 bank。

现有本店 service、manager、technician、finance、inventory 身份/UserStore 必须真实对应；缺父、缺身份、旧版本或未知响应立即失败。原任务若分给 demo 员工，仅由主管经原可见交接控件选择已知员工本人；核价人与复核主管不同，不使用管理员代办。

## 员工输入到结果

1. 主管从原主档 UI 新建三个真实 job WorkItem，各1000千分量、明确30/40/50元；原 `master/references` 新建启用 `category=厂家` 档案，另建真实维修工位。没有 fixture 或 SQL 创建主档、余额或结果。
2. 服务顾问实际现场登记普通维修、选择本店原客车和新工位，原 Arrival 核VIN及明确合成35000公里。实际转换唯一 regular v4 维修，再原 UI 三行报价120元；不同主管复核，本版客户授权。技师实际开工/完成三项，服务顾问独立质检，本版原行、摘要、原授权和真实工位入位分别核对。
3. HK039：保险第一行核30元，独立批准→原提交→`need_documents(lines=[])`→精确引用该 result_id 补件→`rejected(lines=[])`；再新增第二版 assessment、独立批准、第三份提交及 `partial`20元。两版核价/批准、三提交/结果及补件反向关系全部保存；核价阶段无承担绑定或现金。
4. HK040：厂家第二行独立核40元、不同主管批准、实际外部提交及 approved40元；厂家category/ID、当前报价行/数量/金额/提交/结果分别核对。HK041：内部第三行核50元、不同主管批准直接 ready，零外部提交/结果/报销/现金。
5. 原维修 manager allocate 客户10、保险20、厂家40、内部50元，合计120元；明示本批合成人工成本30元。核真实 `bind_after_allocation` 同事务三份 ClaimBinding 的当前 Assessment/Result/Allocation。内部应收为零，外部当前应收70元；不额外点击重复 bind。
6. finance 按三个原 repair_receive 待办本人，分别原 UI 登记10/20/40元，三份不同本单凭据、原账户及独立流水；每笔 RepairPayment→PaymentLink→Cash 单独对应。内部不生现金，核价批准不代到账，原核赔按真实承担到账结束。service 另点原 release、实际工位释放/接车，刷新原单无重复写入。

## 原合同与保护

原页面为 `#service-intake/appointments`、`#repair-orders/{id}`、`#claims/{id}`、`#masters/work_items`、`#master/references`；正向写入全部原可见控件，只有原生同源 Cookie/CSRF 网络观测，SQLite SELECT-only，不注入 fetch、隐藏选择器值或 app state。

核赔封包严格原 request_id、Claim.version 与当前 source.version；`claims_request_receipts` 按 claims_create/assess/approve/transmit/result 原家族重算 digest/保存原 result。Transmission schema 的 supplement_result_id=None 默认保留。原维修回执仍为 `repair_v3_` 家族（也用于v4），仅关联原 Case，不能误当带 result 的核赔回执；四 payer 的原默认 payer_id/payer_name 进入 canonical schema 后重算。原 Case/Task/事件/回执和每步成功后的真实 GET/DOM 对应。

每次真实登录后建立动作基线。复用首维修有限 Guard；核价及承担联动用候选内 ClaimsGuard：全原业务摘要比对、只允许有限声明 append 表和当前维修/三Claim/原Task/本次账户的明确旧ID/列更新，其余旧现金、库存、会员、文件、主档和他店行保持。原核价/结果/报价/授权/施工/收款历史均追加，不覆写旧版。文件原 bytes 只留内存保护，外部证据只记录原 sha256/size/stored_blob length；各提交/批准/结果/收款使用不同内容，原 structure_only 状态不称 ClamAV。

成功顶层有限来源包括 customer/CV/VIN、新 intake/appointment/Arrival/repair/quote、三个 WorkItem/Line、insurer/厂家、三个Claim、全部Assessment/Approval/Transmission/Result/Binding、四Allocation、三PaymentLink/Cash及70元实收/50元内部/30元成本。来源只在五完整 check 全部通过后输出。

## 验收边界

当前仅静态代码候选。首次真实浏览器时序、目录/lookup、独立岗位任务交接、三方付款与刷新待根统一镜像运行；复杂返修、PDI、代办/销售款、更正以及重复/并发/取消条件未执行。真实保险公司/厂家手续、真实客户现场/银行、ClamAV、PostgreSQL、Linux、员工试用和生产门槛未验。六类人工标准保持 pending，business_accepted/full_193_business_acceptance=false；四功能开关仍默认关闭，不更新目录成绩或实施门禁。

静态自审已完成：800行候选 AST、三元导出、空白检查通过；无 app/scenarios/runner/fixture 导入、SQL mutation、evaluate/route 或直接正向请求。脚本冻结 SHA256 `82f66f195cb313df6bab71184ffb3c5e2bdbd14eacbe5668213778231d10baa7`。原API/model对照中明确保留 CashEntry.account 原名称及 PaymentLink.account_id，而非不存在的现金 account_id；外部维修收入按原 Allocation 与 API 动态 revenue_cents 核对，不猜 Case 存储列。本次未导入业务应用或运行实例/浏览器/测试；独立短审及第一次真实执行仍待根安排，静态结论不计 passed。
