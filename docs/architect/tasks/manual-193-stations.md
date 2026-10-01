# 任务：193 项原生浏览器人工验收站点

**任务 id 与负责人**：manual-193-stations；remaining_audit。本文只整理人工验收合同，不登记运行或评分结果。

**目标与依据**：沿原 193 表、`business_acceptance_catalog.json`、当前注册业务候选和 `rubric.json`，合并可共用的人工页面入口，保留每个需求、check、条件及六项评分。使用 DSH Architect 的代表实际样例方法；原完整验收门槛仍保留。

**原编制快照与范围**：2026-10-01，HEAD `8993ca8c755194a42a48e7323fe355e80c6bf9ae` 加当时未提交工作树。原编制时 root 三个定向实例冻结生产 `1c4b9767…`、脚本 `2920f97a…`；它们不是 full53 通过报告。以下补充只更新查看合同和准确入口，不复写各 run 原结果。生产、测试、runner、目录和共享记录未修改，未启动应用或浏览器。

**当前结果与下一步**：原表 193 项可按下列 15 个页面族站点组织；它们不是 15 张实页，也不等于逐项人工已通过。当前注册声明为 192 个完整功能 check，HK099 为 partial。等待 root 取得同一指纹完整 53 场景终局成功，再以该轮原件建立人工实例并按优先站点实际点击；尚未观察的评分均为 pending。

## 进入人工实例的条件

- 完整自动报告必须属于同一次全新隔离运行：53 项完整注册、53 项实际执行、全部 passed、报告完整、退出正常、稳定 provenance。三个 selected 或不同 run 的成功不能拼成 full53。
- 人工实例须由 root 的外置审阅入口打开同轮镜像和合成库；使用真实原生同源 Cookie。记录 origin、生产/脚本/依赖指纹和人工起止时间。不能打开公司库、原预览库或公司 `.env`。
- 以下 `{E}` 是这一次成功 run 的 evidence 根。需求来源取 `{E}/{scenario}/business-checkpoint.json`，并确认该父场景 complete/passed、对应 `HK-xxx-business` 或首七稳定 check_id passed。所有编号从该文件和当前原 GET 解析，不抄旧 run ID。
- 凭据只在该实例私有外置文件中，由 root 按实际账号阶段加载；本文不记录密码。每次登录核本人、当前店、当前岗位。账号默认角色不代替当前店岗位。
- 自动最终状态可能已被同轮后继合法更正或消费。读当前 GET/DB，并以原引用重建关系；不能要求当前行等于较早父 checkpoint 的整行快照。
- 本站点首轮以读取、展开、搜索、分页、跳转和导出为主。已结束业务不重复提交；新写流程人工重演必须使用新的明确来源和原员工确认，未知结果不重放。

## 六项人工评分与硬门禁

### 当前真实浏览器路径

IAB 是此前组织人工查看时选定的工具方式，用户要求的是实际浏览器点击，并未限定仅用 IAB。本轮 CUA/IAB 的运行资源路径报错时，可以使用已可用的原生 Chrome/Playwright，对同轮外置镜像和合成库做真实原页面点击、同源 Cookie 原 GET、截图与只读事实核对。不能降级为 fetch 页面或 Cookie 桥接。

真实原生 Chrome 操作记 `native_chrome_review_click`；自动运行 PNG 的模型审阅记 `automatic_png_review`。曾经真实进行的 IAB 操作保持其原证据标签和结果，不把新 Chrome 行为写成 IAB、员工试用或旧失败通过。工具路径错误与产品缺陷分别记录。

统一使用 `rubric.json` 的 1–5 分制，每项至少 3 分且有具体观察才通过。某项无实际观察或未遇到适用条件，保留 pending/not_tested，不以默认 3 分补齐。

| 评分 id | 人工需看到或操作的事实 | 证据边界 |
| --- | --- | --- |
| visual | 390、768、1440 宽度下实际页面主次、金额、状态、表格和按钮可读；展开后无溢出、遮挡或布局跳动 | PNG 审阅可以评价当时可见布局；真实浏览器调宽、滚动和展开分别留证，不从一张截图推断隐藏区域 |
| simplicity | 从业务入口检索到原单、当前待办或报表，步骤容易理解；同一原单不用重复猜编号、岗位或附件 | 终态只读路径只能评价查阅；原建单、交接、审批及提交的便利程度仍需本人实际操作 |
| conciseness | 按钮、状态、错误和提示简短准确；保留门店、对象、金额、真实拒绝和下一步，没有多余介绍 | 可对实际可见 PNG/页面原文作模型审阅并说明理由；字数断言不代替判断，未出现的提示仍未评 |
| fact_clarity | 清楚区分约定、实收、库存实发、安装/质检/客户接收、会员权益、在途和助手准备；未知成本/不完整期间明确 | 对照同轮原 API 与只读 DB；“完成”标签或任务消失不能代替这些事实 |
| recovery | 合法拒绝、换店、退出、冲突或未知结果后，提示说明下一步且不误报成功、不重复款项 | 只读取旧拒绝原件是辅助证据；只对真实浏览器本次实际遇到的分支评分，未遇到的分支仍 pending |
| accessibility | 鼠标、键盘焦点、可点击区域、标签及窄屏操作易用；可搜索候选必须明确选择，关闭/返回保留合理上下文 | 原生 Chrome 点击/Tab/Enter/Escape 可成立；窄 viewport 不是实手机，系统输入法与真实员工效率仍独立待测 |

此外，目录每个 check 的 `front_end_expected/simple_flow/concise_copy/backend_matches/hard_bug/source_integrity` 仍逐项记录。无意外 5xx/未处理异常、无越权或错店、金额数量/原 Task/CAS/回执/唯一提交、旧现金库存文件保护属于硬门禁，不能用平均分抵消。`business_accepted` 只有该项必需合同、六项人工和硬门禁均有证据才可判定；全表不直接继承自动 checkpoint 的 passed。

每条人工记录至少包含：原需求 id/原标题/check_id、站点、本人 id/current_role/store、实际 URL、宽度、时间、实际动作与所见原文、六项分数及理由、硬门禁、证据类型和路径、当前原 GET/DB 来源、未测条件。结果存该 run 外置 `evidence/manual-review/`，不覆盖自动报告。当前证据类型明确写 `native_chrome_review_click`、`automatic_png_review`、`supplemental_readonly_api`、`readonly_db`；看图不能写成本人点击。

同源原 GET 与 SELECT 可以辅助 `fact_clarity/backend_matches/source_integrity`，并不把未观察的交接、审批、实际款项或原件签字替换为人工操作。`simplicity` 只评价实际走过的读取/办理路线；`recovery` 不从自动旧日志继承评分；`accessibility` 不把 Playwright 输入当作真实操作系统输入法或真实员工使用效率。

## 优先站点的准确来源与操作

### P1 财务更正三类原款

父场景 `finance-remaining-hk076-078-081-086-088-092`。`report_sources.store_id=1`；按 `report_sources.corrections[].requirement` 分别找 HK078、081、086，读取 `finance_case_id/source_case_id/correction_id/original_cash_id/original_payment_id/new_cash_ids/new_payment_ids`。事前 BANK/ENTRY 声明在该项 check 的 `evidence.declaration`，不能从顶层臆造字段。

财务本人在 1 店打开 `#business-finance-order/{finance_case_id}`（h1“财务业务办理”；原 GET `/api/business-finance/orders/{finance_case_id}`）。实际展开“冻结申请与原款”“资金记录与原单分配”，辨认原误记凭证、正确凭证、原到账日，逐条点击原单按钮 `#case/{source_case_id}`，然后沿原领域入口读销售、维修或零售明细。

| 原 check | 页面资金事实 | 必须保留的区别 |
| --- | --- | --- |
| HK-078-business 整车收款单调整 | 两行 gross 各 50,000.00 元，业务分配各 50,000.00 元；当前更正原现金、PaymentLink 和来源单关系一致 | 原销售已 delivered 仍只能沿更正合同办理；不是重新开放普通收款或重做交付 |
| HK-081-business 维修收款单调整 | 两行 gross 各 10.00 元，业务分配各 10.00 元；原维修及核赔关联保留 | 更正不重领料、不重复客户付款，不把内部承担当现金 |
| HK-086-business 物资收款单调整 | 两行 gross 各 25.00 元，分配各 15.00 元；原已实际退款 10.00 元及其 reference 可见 | 旧退款原件不改、不再退款；反向更正与正确重记不叫新增真实退款 |

自动两行资金与 immutable 原件可以辅助 backend/source 门禁；人工仍需看原单按钮是否易发现、gross/net 是否可理解、中文提示是否准确。首次查阅不点击 approve/execute，不重复已经结束的三张更正。

### P2 HK071 机构库存的真实正页面

父场景 `inventory-store-scope-hk071`。来源键：`employee_id/current_store_roles/current_access_version/private_source_scenario/private_account_key/current_password_stage/first_store_item_id/second_store_item_id/local_move_case_id/source_location_id/destination_location_id/transit_balance_id/dispatch_entry_ids/accept_entry_ids`。私有身份来自同轮 `system-management-hk189-191` 的 manager，新密码阶段按外置私有记录解析。

该员工已恢复原店授权：在 1 店以其真实 manager 岗位经 `#warehouse` 搜索物资，进入 `#warehouse-item/{first_store_item_id}`，原 GET `/api/warehouse/items/{id}/stock`。核页头 name/SKU、“门店库存”“库位及店内在途”“不可变库位流水”；展开并点击本次移库的原单 `#case/{local_move_case_id}`。账面、可用、占用及价值必须读当下同 Item/Balance/有效占额，不固定旧的数量合计。

本次实际发运的 500 千分位已接收，最终在途为 0。当前人工可核非空实际库位、独立 dispatch/accept Entry、completed 原单及释放占额；不能称当前看到了非零在途。二店非空原物资仅合法二店读取身份可复看，不能给已恢复的甲重新勾二店。未授权/汇总只读/非零在途中间态的真实浏览器体验若未另外实际复现，仍 pending；自动旧阶段证据分开列。

### P3 第三店 HK152/153 原来源

父场景 `reports-complete-source-hk152-153`。精确来源取 `report_sources.store_id/item_id/warehouse_id/location_ids/enrollment_id/activation_case_id/purchase_case_id/receipt_ids/payment_ids/cash_ids/stock_move_ids/warehouse_entry_ids/period`；该第三店不是固定数字 3。候选完毕后 manager/inventory/finance 已恢复原权限，不能继续以失去第三店权限的员工读取。人工可由具有真实全店只读权限的 admin 在当前第三店查阅，或另取得原 UI 明确授权；不借 admin 办理员工业务。

先用原店选择器切第三店并核 `/api/auth/me` 当前范围，再经统计目录搜索原标题分别进入：

- HK153“物资采购订货统计”：`#procurement-cohort`，GET `/api/inventory-reports/procurement`，日期严格用 `period`。一行计划 2000、两个实际批次各 1000、第一批实际退 500，原付款 2000/原退款 500，最终库存与有效付款均 1500。核 complete=true、无 issues、全店数量/金额及原单位图，不将“本新批次”总额冒充整店范围。
- 三表为 `procurement_cohort_lines/procurement_cohort_postings/procurement_cohort_issues`，动态图表原键 `procurement_cohort_unit_0`，图 id `procurement_cohort_0`。各原 CSV `/api/inventory-reports/procurement/export/{table_key}`；实际点击下载，列和行与同范围原表匹配，且每次仅追加一条本人本店 export audit。点击 posting 原单核 `#case/{purchase_case_id}`，再原 `#procurement/{purchase_case_id}`。
- HK152“物资仓库入出存统计”：`#warehouse-period`，GET `/api/inventory-reports/warehouses`；明确选择本 Item/仓库，日期仍用同 `period`。三表 `warehouse_period_balances/warehouse_period_baselines/warehouse_period_entries`；图 `warehouse_period_closing`。原 CSV `/api/inventory-reports/warehouses/export/{table_key}` 保留同 item_id/warehouse_id/日期。点击 baseline 到 `#case/{activation_case_id}`。
- HK152 必须清楚显示 **complete=false、closing_complete=true**：本店零启用形成唯一原 Allocation/Line/Approval/Enrollment 与 1 Balance、0 Entry、0 StockMove；已知真实期末 1500 不证明未知期初已知。完整历史期间仍 not_tested；不能改时钟/日期或“修”成 complete=true。

原定义、CSV及日期口径均不改变。各次导出会合法追加一条审计，其余业务行及旧审计必须保护；不用“整库零写”误判合法导出。

### P4 HK157–159 正欠额

父场景 `receivables-hk157-158-159`，`report_sources` 有 `retail_case_id/sales_case_id/associated_service_case_id/repair_case_id/account_id/actual_cash_ids/payment_link_ids/positive_due_cents/current_whole_store_receivable_cents`。财务本人在 1 店进入 `#analytics/finance` 点击真实“当前尚待收取”KPI到 `#table/receivables`，使用该 check `evidence.report.period`；全表包括同店其它原来源，不能只断三张目标单的金额。

核四个有限正来源：Retail 约定20/现金5/欠15元；车辆约定100/实收30/欠70元；关联服务约定10/实收3/欠7元；维修客户分配20/实收5/欠15元，内部承担另列。金额仍逐项对照原 check、当前本版 Quote/分配及真实资金，不从当前欠额反推约定或实收。

逐行点击原单，再到 `#retail/{retail_case_id}`、`#sales-quotes/{sales_case_id}`、`#service-orders/{associated_service_case_id}`、`#repair-orders/{repair_case_id}` 核金额/来源和原账户现金；GET 分别是 `/api/retail/orders/{id}`、`/api/sales-quotes/orders/{id}`、`/api/service-orders/{id}`、`/api/repair-orders/{id}`。原整表 CSV GET `/api/flow/analytics/export?dataset=receivables&date_from=…&date_to=…` 与 KPI/全表/原单同范围且仅一条原 export audit。

原合同没有专门应收图，`cash_category` 不是应收图。当前终态零欠额不能替代上述真实正差额。不要在人工查询中追加收款使本次正来源消失。

### P5 销售加装与代办/双源其它收入

父场景 `sales-followon-hk012-015-016-017`；来源键 `delivered_order_id/customer_id/vehicle_id/addon_case_id/agency_case_id/customer_other_case_id/manufacturer_income_case_id/material_item_id/material_location_id/work_item_id/agency_project_id/account_id`。

1 店用原 service/sales 查询身份从 `#addon-orders/{addon_case_id}`（GET `/api/addon-orders/{id}`）读本销售、VIN、当前报价及授权、物料原出库与成本、真实 technician 安装、独立不合格检查→整改→合格复检→客户 accept 和实际收款35元。展开这些记录并沿原销售/资金按钮跳转；质检、接收、Cash是不同事实。不能把最终 completed 作为已经人工操作过各前序。

同一销售关联 `#service-orders/{agency_case_id}`：两报价及独立批准/本版授权、代缴收/付、need_documents补件及逐项履约分别查看。HK017须另读 `#service-orders/{customer_other_case_id}` 和 `#vehicle-income/{manufacturer_income_case_id}`（GET `/api/vehicle-income/{id}`）；客户8元来源与厂家100→70元批准目标、实际到账100/同原账户实际退30元不能互相代替。零价赠送/取消拆回等未执行分支保留 not_tested。

## 首轮22个实际查看入口矩阵（均未执行）

这是最小优先查看路线，不是新增测试或22项通过声明，更不是193逐项人工验收。M01–M15先闭合财务、当前库存、期间报表与正欠额/销售后继；M16–M22补助手、系统、会员、精品和客户原来源。按同轮完整父与当前真实岗位取舍，父失败或缺键则该站点保持 pending，不能借另一 run 编号补齐。

下表的 `{s.*}` 指该行父 `business-checkpoint.json.report_sources`；FIN按 `corrections[].requirement` 找唯一项。只有助手使用自身 `observations.json` 的 `followup_database/dependent_pending_card_identity`，不虚构 business-checkpoint。每次导航需先等**同一原 GET 200、响应有限 id/current version、`#main h1/.pagehead` 与原单**，再展开/点击；已在同 hash 时不用假定 anchor 会再 GET。登录产生的合法审计与业务读取分开留证。

可用原只读 helper 简称：SYS=`system_management_business.open_page(e,route,title,api_path)`（身份由调用方原 UI 登录/切店）；FIN=`finance_remaining_business.correction_rendered`（需从该项 evidence 解析实际 spec）；INV=`inventory_scope_business.stock_read`；AR=`receivables_business.domain_drill`及`report_business`读取/表/CSV/钻取 helper；SRC=`report_complete_source_business.open_report/export`；SF=`sales_followon_business.read_as`；MEM=`membership_business.ready_member`；PTS=`member_points_tier_business.wallet_view`；BT=`boutique_business.retail_read`；REM=`customer_reminders_business.read_page/care_read`；AUD=`system_followon_business.audit_open/audit_filter/audit_detail/audit_viewports`。这里只提供现有合同参照；不得调用整场作者函数、write/action helper 或复演旧确认来完成只读站点。

| 站点 | 父/有限来源键 | 当前身份与原 route / GET | 准确可见控件与可用 helper | 本站点要判读的事实 |
| --- | --- | --- | --- | --- |
| M01 售车款更正 | FIN父；HK078唯一 `finance_case_id/source_case_id` | finance，1店；`#business-finance-order/{id}`，GET `/api/business-finance/orders/{id}` | SYS；`.panel`内 exact heading“冻结申请与原款”“资金记录与原单分配”；`[data-act="open"][data-route="case/{source_case_id}"]`；参照FIN | BANK/ENTRY及原日期，两50000元 gross/分配；只是登记更正，不再普通收款 |
| M02 维修款更正 | 同FIN父；HK081唯一两case键 | 同M01 | 同M01，有限当前原单按钮 | 两10元 gross/分配；保留核赔、原库存和原客户款 |
| M03 精品款更正 | 同FIN父；HK086唯一两case键 | 同M01 | 同M01；原冻结面板保留原退款 reference | 两25元 gross、各15元分配，原已退10元不重做 |
| M04 HK071正库存 | `inventory-store-scope-hk071`；`employee_id/first_store_item_id/local_move_case_id/source_location_id/destination_location_id` | 同轮SYS私有manager，已恢复1店；`#warehouse-item/{id}`，GET `/api/warehouse/items/{id}/stock` | INV；原`#filters [name="q"]`输入本SKU→`[data-act="open"][data-route="warehouse-item/{id}"]`；panel exact text“库位及店内在途”“不可变库位流水” | 当前账面/可用/预占/价值，真实非空库位；已完成500移库最终在途0，不冒非零现态 |
| M05 HK153完整新店采购批次 | `reports-complete-source-hk152-153`；`store_id/purchase_case_id/period` | admin合法读取实际第三店；`#procurement-cohort`，GET `/api/inventory-reports/procurement` | SRC；`#mux-query`检索HK-153→`[data-mux-open="wf-report-153"]`；`#datefilters [name=date_from/date_to]`；`[data-act="inventory-report-export"][data-key="procurement_cohort_lines"]`及postings/issues/unit_0 | 本店完整批次2000、两收各1000、退500/原款500、终1500；三表及原单位图同范围，不把新批次数当全店 |
| M06 HK152期末与未知期初 | 同SRC父；`item_id/warehouse_id/activation_case_id/period` | 同实际第三店；`#warehouse-period`，GET `/api/inventory-reports/warehouses` | SRC；检索HK-152→`[data-mux-open="wf-report-152"]`；同datefilters；精确export key `warehouse_period_balances/baselines/entries` | complete=false与closing_complete=true分别可见；期末1500，不宣称期初/完整历史已知 |
| M07 整店正应收表 | `receivables-hk157-158-159`；四case键、`positive_due_cents`；日期取 check.evidence.report.period | finance，1店；`#analytics/finance`→`#table/receivables`；GET `/api/flow/analytics` | AR/report_business；`#datefilters`；原“当前尚待收取”KPI；`[data-act="exporttable"][data-table="receivables"]` | 整店KPI、非空全表、同范围CSV；没有额外应收图，不把cash图顶替 |
| M08 正销售欠额 | AR父；`sales_case_id/new_vehicle_id` | finance，1店；`#sales-quotes/{id}`，GET `/api/sales-quotes/orders/{id}` | AR.domain_drill；先表内原单→`[data-act="open"][data-route="sales-quotes/{id}"]` | 100/实收30/欠70及本新VIN，本版签回/实款分别 |
| M09 正关联服务欠额 | AR父；`associated_service_case_id/sales_case_id` | finance，1店；`#service-orders/{id}`，GET `/api/service-orders/{id}` | AR.domain_drill；原领域按钮；`#main .pagehead`核原单号 | 原销售关联、服务约定10/实收3/欠7，fee与pass区分 |
| M10 正维修客户欠额 | AR父；`repair_case_id/customer_vehicle_id` | finance，1店；`#repair-orders/{id}`，GET `/api/repair-orders/{id}` | AR.domain_drill；`.kpi`含“客户尚欠” | 客户分配20/实收5/欠15，internal独立；未释放不能写已交车 |
| M11 正精品欠额 | AR父；`retail_case_id/item_id` | finance，1店；`#retail/{id}`，GET `/api/retail/orders/{id}` | AR.domain_drill；`.card`含“尚欠”；核原单号 | 20/真实现金5/欠15；实际出库成本来自本轮追加采购 |
| M12 实际销售加装 | `sales-followon-hk012-015-016-017`；`addon_case_id/vehicle_id` | service或本人sales，1店；`#addon-orders/{id}`，GET `/api/addon-orders/{id}` | SF.read_as；`.panel`heading“商品、安装与真实资金”“冻结报价与授权历史”“实际安装批次 {id}”；`details > summary` | 本VIN领料/实际安装/不合格→整改→复检/客户接收/35元实收，事实互不替代 |
| M13 原代办项目 | SF父；`agency_case_id` | service或本人sales，1店；`#service-orders/{id}`，GET `/api/service-orders/{id}` | SF.read_as；panel“客户收费与代缴本金”“报价与授权记录”下`details > summary` | 两版独立批准/授权，代缴收付、need_documents补件逐项外部结果/履约；金额受同轮财务后继影响时读当前原件 |
| M14 客户其它收入 | SF父；`customer_other_case_id` | finance或原service/sales，1店；`#service-orders/{id}`，GET `/api/service-orders/{id}` | SF.read_as；同原收费面板和原quote历史展开 | 客户8元履约及实际到账，不拿厂家款替代 |
| M15 厂家其它收入 | SF父；`manufacturer_income_case_id` | finance，1店；`#vehicle-income/{id}`，GET `/api/vehicle-income/{id}` | SF.read_as(domain=income)；SYS/`#main .panel`及原单按钮 | 原到账100/独立改应收70/原账户实退30，不解释成客户退款 |
| M16 助手原会话恢复 | `dependent-plan-followup-controls/observations.json`；followup_database.plan_id/cards[].session_id；原pending card id、case_id另取dependent_pending_card_identity | 原admin，1店；`#business-assistant`；GET workspace/sessions及`/sessions/{session_id}` | `Evidence.ready`；`[data-ba-action="history"]`→`[data-ba-action="session"][data-id="{session_id}"]`→`[data-ba-action="refresh"]`；`[data-ba-action="queue-filter"][data-filter="pending"]`；`[data-proposal="{id}"]` | 原succeeded与pending卡分别显示、真实原单链接；原grant已revoked不复活、不确认待办、不发送新模型请求 |
| M17 系统非空审计三宽度 | `system-followon-hk192-193`；`supplier_id/source_audit_ids` | admin，1店，读本原supplier日志；`#audit`，GET `/api/audit?entity_type=typed_master&entity_id={supplier_id}&page=…` | AUD；`#audit-filters [name="entity_type"]/[name="entity_id"]/button[type=submit]`；`[data-act="auditdetail"][data-id="{audit_id}"]`；`#modal-title`“操作详情”，close按钮 | exact原日志与before/after；390/768/1440七字段记录可见、详情/分页可点，日期API UTC→UI本地 |
| M18 当前卡/会期 | `member-points-tier-hk121-122-188-120-119-131`及`membership-hk117-128-118-089-094`；`customer_id/active_period_id/period_void_id`、卡父active_card_id | finance，1店；`#membership/{customer_id}`，GET `/api/membership/members?customer_id=…` | MEM.ready_member；h1“会员卡与续会”，原`.panel`“等级与有效期间”“消费积分”；`[data-act="open"][data-route^="membership-order/"]` | 当前A/B会期与未来续会已退/PeriodVoid、卡历史和实费分开；不重办续会/换卡 |
| M19 积分/券独立批次 | PTS父；`customer_id/member_id/earned_points_wallet_id/independent_points_wallet_id/exchanged_coupon_wallet_id/direct_coupon_wallet_id` | finance，1店；`#benefits/{customer_id}`，GET `/api/group/benefits/members?customer_id=…` | PTS.wallet_view；panel“会员现有权益”“本店待核销”“原款退款”，按真实rule名称/余额定位行 | 实际消费积分与手工赠分，兑换2券/直接赠1不同batch；当前可用/占额按原账读取，现金不拼余额 |
| M20 精品实际零售/安装 | `boutique-purchase-retail-hk074-052-058-062-064-082`；`retail_case_id/installation_event_id/accept_event_id/work_item_id/retail_cash_ids/retail_group_plan_id` | finance或原service，1店；`#retail/{id}`，GET `/api/retail/orders/{id}` | BT.retail_read；原`.panel`与`details > summary`；当前原商品行/出库批次 | 双商品只安装收费那一行，唯一真实技师install/客户accept；券+本金+两笔Cash来源各自核 |
| M21 原保养替换提醒 | `customer-reminders-hk105-106-112`；`maintenance_case_id/delivery_correction_case_id/customer_vehicle_id` | 现任务本人service，1店；`#customer-service/{maintenance_case_id}`，GET `/api/customer-service/cases/{id}` | REM.care_read；原`.pagehead`与办理记录；不点`[data-act="care-action"]`写按钮 | 有效纠正/旧提醒失效/Replacement及新原basis，不把生成当外联或真实保养 |
| M22 客户车辆有效来源 | 同REM父；`customer_vehicle_id/customer_id/source_delivery_observation_id/first_service_observation_id` | 原service，1店；`#customer-vehicles/{id}`，GET `/api/customer-service/vehicles/{id}`及`/{id}/history` | REM.read_page参照当前车辆页面；`#main h1/.pagehead`，有效观察/服务历史原panel | 真实VIN关系与观察来源；跨店授权到期等HK099未观察条件仍partial，不因此新增完整HK099成绩 |

M01–M03应按对应check的实际 declaration解析，不从当前金额反推BANK/ENTRY。M05–M06/SRC helper原role假定finance且需can_money；权限恢复后root应使用合法admin阅读真实第三店并复核API范围，不能原样借已撤销第三店权限的finance/helper。

M07表控件以 `report_business.panel/verify_table/export_csv` 的当前原DOM为准：全表不固定前序少数行，实际下载会合法新增一条本人本店export审计，所有旧审计和其他业务仍保护。M16从历史选择会话仅恢复展示；原prepare/confirm/enable/resume/revoke整场函数不可当只读helper。M17不在这里再次改角色/密码/头像。

## 其余站点合并索引

范围是唯一的“主审阅归属”，允许在同一次实页访问上核多个明确原 check；每项仍单独评分。P1–P5 是下表相关站点的优先子站点，不另外累加需求数。

| 站点 | 主归属原需求 | 原 UI 页面族与当前岗位 | 人工输入到可见结果及来源重点 |
| --- | --- | --- | --- |
| S01 财务 | HK075–097（23项） | 上述更正；`business-finance`/`business-finance-order/{id}`、`reconciliation/{id}`、`invoices`，各收款原领域页；财务/独立主管/审计，1店及调拨双方原店 | 三类更正、预收/抵用/退款、原收款、开票/月结。Cash与会员/内部结算/发票/封存分开；明细与冻结定义逐项。正写过程没人工操作则 simplicity/recovery仍pending |
| S02 当前库存 | HK029、070、071（3项） | `legacy/vehicles`（原 GET `/api/records/vehicles?q=VIN`）、`vehicle-catalog`、`warehouse-item/{id}`；实际授权店manager/inventory/finance/auditor | 同轮真实VIN代次/位置/可用/占用，物资账面/可用/预占/在途；P2的权限恢复及当前0在途区别 |
| S03 第三店报表 | HK152、153（2项） | `warehouse-period`、`procurement-cohort`，P3 | 同一原期间、全店范围、非空图/表/CSV/原单，未知期初保持；日期历史窗口不补判 |
| S04 正欠额 | HK157–159（3项） | `analytics/finance`→`table/receivables`→四原领域；财务/审计/主管，P4 | 每种正差额独立；整表KPI/CSV，同账户实际Cash与非现金承担独立，无额外应收图 |
| S05 销售/附属服务 | HK008–017、022、037、065（13项） | `sales-quotes/{id}`、`aftercare/{id}`、`addon-orders/{id}`、`insurance-orders/{id}`、`service-orders/{id}`、`vehicle-income/{id}`；销售本人/原岗位 | 报价/VIN/生成合同原字节/签回/实款/PDI/实发/交付；P5加装与双收入源；退订和保险另原单，不以一次交付包办全部 |
| S06 售前 | HK001–007、103（8项） | `cases/lead`→`case/{lead_id}`、“我的工作”；销售本人/独立主管 | 创建、分派、意向、两次不同跟进、原到期任务实际打开；展开历史，必填员工候选必须选择。来源首七各稳定check，不用一个派单结果覆盖七项 |
| S07 整车供应/执行 | HK018–021、023–028、030（11项） | `vehicle-catalog`、`vehicle-procurement/{id}`、`vehicle-imports/{id}`、`vehicle-operation/{id}`、`vehicle-transfers/{id}`；库管/独立主管/财务、跨店双方本人 | 多车型颜色/VIN计划；CSV上传/预检/trial/review/confirm分别；实发/到货/其他出退/新代次/移库、原供应款退回。trial记录不叫实际执行 |
| S08 维修 | HK031–036、038–044（13项） | `service-intake/appointments`/`reworks`、`repair-orders/{id}`、`claims/{id}`、`repair-packages`；service/technician/独立主管/财务 | 预约到店/资源/接车/报价授权/施工质检/多方核赔/返修/交车真实来源。维修领退料与内部承担仍沿原字段；HK043设置借S12同页但独立check |
| S09 物资/仓储 | HK045–061、069、072、073（20项） | `procurement/{id}`、`warehouse/{id}`/`warehouse-item/{id}`、`transfers/{id}`、维修领退料原页；库管/主管/财务，原双方店 | 分批采购/部分原退/请款实付实退、耗材/礼品/其他入出及对应原返、盘盈亏/移库。明示数量milli/成本/位置/原来源；查询和配置不是物理收发 |
| S10 精品 | HK062–064、066–068、074（7项） | `retail/{id}`、`retail-bundles`、`procurement/{id}`；service/inventory/technician/finance/独立主管 | 同轮 boutique+retail_remaining完整父：双商品且仅收费安装那行有安装；关联维修独立Retail，实际部分可售退货与原款退10，Bundle套数/CPS分摊及实际履约 |
| S11 客户/提醒 | HK098–102、104–116（18项，含099 partial） | `master/customers`、`customer-vehicles/{id}`、`customer-service/{id}`、`customer-questionnaires`、`customer-reminders`、其它收入原服务页；service/customer_service/主管及本人销售 | 新改客户/同号明确另建/联系撤回权限；咨询、投诉、救援各原单；问卷版本/答案、回访源、真实提醒基准及纠正失效/Replacement。HK099历史到期日期条件单列 |
| S12 会员/权益 | HK117–133、188（18项） | `membership/{customer_id}`/`membership-order/{id}`、`group/{customer_id}`、`benefits/{customer_id}`、`recharge-bundles/{customer_id}`、`repair-packages`、`member-pricing`；front/finance/独立主管、规则发布仅原允许岗位 | 卡代次、当前/未来会期、独立调级/续费及原未来会费实退，实际本金/bonus/points/coupon/Package各单位账，真实消费积分与手工赠分区分、每批可用/占额及退款回收，不合并不同钱包/现金 |
| S13 统计 | HK134–151、154–156、160–169（31项） | 统计目录→原 `table/*`/`analytics/*`、`vehicle-period`、`visit-activity`、`repair-materials`、`material-value`、`reconciliation`；同店finance/manager/auditor | 以下报表键清单逐项操作非空来源、原范围表/图/CSV/钻取；共享表不同业务各选真实行，缺源问题保留。HK136事件时间与166到店批次不混为未来计划 |
| S14 基础资料 | HK170–187（18项） | `dictionaries`及7原group、`masters/{kind}`、`vehicle-catalog`、`master/items`；原管理/库管/服务及只读岗位 | 同轮真实已新建/编辑的各子类分别查，不用一个字典页覆盖七项；brand/category真实页是 `masters/material_brands`/`masters/material_categories`，help的newItem不是主档验收；仓类型和本店真实FK独立 |
| S15 系统/授权 | HK189–193（5项） | `stores`、`users`、`parameters`、`audit`、`dossier-grants/{sent,review,received}`；admin管理、独立复核及指定接收本人 | 原新增第三店和两个合成员工、默认sales/空勾店、本人首次改密/重置/会话失效、实际原文件授权/岗位变化/撤销/真实短期限、非空audit筛选/详情/三宽度。终态授权已失效不能伪复活；不碰已有真实账号 |

统计站点 S13 的确切原表/入口索引：134/135 `table/leads`；136/166 `visit-activity`；137 `table/orders`；138/142 `table/deliveries`；139 `table/addon_actual_facts`；140 `table/service_fee_facts`；141 `analytics/sales` 的保单/佣金/现金三独立原图表；143–145 `vehicle-period`；146 `table/service_appointments`；147 `table/repairs`；148 `table/repair_projects`；149 `repair-materials`；150/151 `table/movements`；154 `table/retail_settlements`；155 `table/warehouse_local_moves`；156 `table/retail_installation`；160 `table/cash`；161 `material-value`；162 `table/finance_advances`；163 `reconciliation`；164 `table/customer_vehicle_stats`；165 `table/callbacks`；167 `table/customer_value`；168 `analytics/members`；169 `table/benefit_coupon`。每项按相应 checkpoint 的原期间和当前完整范围，不制造集团本金报表键或空图通过。

## 未判定条件和停止边界

- 15个站点索引的主归属覆盖193行且无重复；这只说明组织完整。所有人工评分当前 pending，HK099仍partial；不是“18页/15站点等于193项人工验收”。
- 自动 PNG 看图可以确认当时可见状态，但不能证明本人实际点击建单、候选选择、交接、审批、银行确认或实物接收。若只审最终只读页，应在写需求的对应人工字段明确记录未观察的前序。新Chrome点击只记实际路径，不重标历史IAB。
- HK071当前非零在途已结束、二店临时授权已撤；HK152未知期初与更早历史窗口、HK099授权真实日期到期、未遇到的拒绝/冲突/同名/暂停等条件继续not_tested。不得为人工演示改权限、改时钟、复活旧grant或重提交旧单。
- 每次导出只允许真实一次download及一条本人本店原export审计；截图、分页、查看与GET不应写业务。提交结果不明或真正5xx立即留证停止当前项，由root收尾实例后决定修复，不盲重试。
- 三宽度必须在相应实际页面上保留；只验证一个审计手机页不覆盖所有表单/金额/库存/会员页面。岗位已恢复后仍按当前权限重新读，不用管理员替员工补动作。
- PostgreSQL/current migrations、Windows/Linux、真实模型101/283及其live门槛、真实员工效率和输入法、ClamAV与私有文件、真实银行/保险/税务/签字/实物、HTTPS安全Cookie/Host、生产门槛仍独立未判定。四新生产功能开关保持默认关闭。

**静态核对**：只读核了原193表、catalog六条件与rubric六评分、注册候选上述源键/原路由/当前岗位；人工站点集合193/193、重复0。本文尚无实际人工浏览器结果，未更新里程碑或自动报告。
