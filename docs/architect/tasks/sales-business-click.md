# 售前七项真实业务点击

- 任务：HK-001 至 HK-007 原接待、分派、意向、沟通和到期提醒。
- 负责人：click_scenarios。
- 当前状态：Fresh07同次七项原UI/API/DB通过；三宽度全新分派表单鼠标未选拒绝通过。当前IAB复核中，人工体验/完整193业务不记通过。前轮失败保留。
- 代码范围：`tests/browser_click/sales_business.py` 与本页。生产、夹具、入口和总计划由根代理及对应负责人维护。

## 架构与原合同

依据 `docs/workflow-source/business.json` 的 `wf-reception`、`wf-intent-followup`、原 `app/flow_specs.py`、`app/flow_engine.py`、`app/flow_api.py` 以及 `web/app.js` / `web/customerchoice.js` / `web/livechoices.js`。原表 HK-001…007 分别为展厅接待、展厅接待分派、意向客户管理、意向单分派、意向单跟进记录、展厅接待提醒、意向客户提醒；七项分别验收，不能共用一条派单事实冒充全部。

原提醒合同是当前负责员工“我的工作”中的原 `contact` / `follow` 到期任务。本轮实际选择“计划今天”，核对同原单号、标题、负责人和期限，再点击原办理入口。不宣称外部通知、真实客户沟通、后台时钟触发或员工效率。

## 夹具与入口

最小前置只有本店启用账号 reception、manager、原 sales 和 sales_peer（实际岗位 sales），账号密码仅外部随机凭据文件。`business_fixtures.presales` 提供 `store_id/reception_key/manager_key/sales_key/sales_peer_key`；不预置本轮客户、接待、任务、沟通、提醒或转交结果。原 assign 任务按接待负载分配，未篡改夹具的真实任务负责人；由原主管权限实际分派给所选销售。

新增模块复用 `scenarios.Evidence` 的原生点击、填表、登录、截图、网络和 SELECT-only 数据库接口，不顶层导入 `scenarios`。导出 `BUSINESS_SCENARIOS=(("sales-presales-hk001-007", sales_presales, 240),)`，函数签名为 `async (e, context, credentials)`；由根代理接线并定向联合执行。旧九组及需求四组全部保留。

## 场景和事实

1. 接待真实新建无电话客户：一张 `lead`、一个 Customer、原 assign 任务和 create 事件，门店/身份/来源准确。
2. 主管从原表单分派：assign 结束，contact 交给明确销售，Case/Customer 所有人及原事件正确。
3. 销售安排接待回访：缺电话时原浏览器必填阻止提交且业务摘要不变；员工明确补电话、沟通结果和今日日期，原 contact 待办实际显示并点击可用。
4. 销售将同原单转意向：need/期限/state/follow 原事实一致，接待历史保留，未另建客户。
5. 主管转交原 follow：同 Task、Case、Customer 一致改负责人，原转交历史保留；旧销售原列表和“我的工作”不再含该单。
6. 新销售提交两次不同 follow：追加两个原 FlowEvent，各日期和结果准确，第一次记录保留，同一任务版本/期限更新，原 UI 实际展开留痕。
7. 今日意向提醒实际显示并点击回原单，销售乙在原表单提交第三次跟进，追加提醒办理沟通并安排明日期限；原刷新仍只有一个 open follow，读取/刷新零原业务写入。

## 证据和验收边界

每项外部 `business-checkpoint.json` 含 HK 编号、稳定 `check_id`、具体 `acceptance_checks`、逐项状态、原 UI 动作、实际 Cookie/CSRF POST 及原渲染 GET 元数据、只读原 Case/Customer/Task/Event 事实。首次失败留 failed，后续未执行项留 not_tested；空场景、缺前置或异常退出不会标通过。截图、动作、网络和报告由原 Evidence 保存在仓库外。

本页登记的是七项本店主路径与上述边界，不继承原 13 组或映射报告成绩，不代表原 193 项全部验收、真实模型、生产支付/库存、跨店、员工试用或部署通过。本轮用户请求扩大业务验收，根代理维护总目录和正式实施计划。

## 当前进度与下一步

源码合同与夹具接口已对齐，场景已落盘。AST 解析通过，定向差异空白检查通过；代码人工审阅核对了原员工选择项的精确姓名边界、实际原单/任务版本、同源 Cookie/CSRF、原渲染异步响应、七项独立判据及原 Task/Case/Customer/FlowEvent 关系。仅静态检查，不等于七项通过。

本次 `sales_business.py` SHA-256 为 `42ed5b2a606fdf017f4cc3223999ebb85b9fa87a3e9e85f0bd09626ce5a5137b`。下一步由根代理接已稳定的夹具和入口，在全新外部隔离目录定向运行 `sales-presales-hk001-007`。本代理不启动应用、不直接提交业务 API、不修改原数据或回填结果。具体失败与通过保留在本轮实际报告，未执行项不补成通过。

## 第二轮实测失败与修正

已只读核对外部 `business-presales-20261001-02/evidence/sales-presales-hk001-007/business-checkpoint.json`：HK-001 的原 UI/API/数据库检查 passed，HK-002 failed，其余五项 not_tested；整场 `complete=false/passed=false`。原失败报告、截图和日志保留，没有将第一项成绩拼成七项验收。

HK-002 填写员工搜索后，脚本从旧完整候选冻结了 `#field-assignee_id-options-4`；原搜索防抖返回会重建列表，该员工的新候选变为索引 0，旧节点隐藏或分离，导致原生点击超时。原失败画面仍显示合成销售与合成销售乙，属于测试同步问题，未据此修改产品或降低原分派判据。

仅修正 `employee_choice`：保留精确姓名边界的动态 Locator，等待唯一且可见后记录真实点击动作并调用原生 `Locator.click()`，让点击解析当前候选；不读取或冻结旧 DOM 编号，不设置隐藏值，不 force、不添加重试或固定等待。点击后仍严格核对原隐藏 select 的员工 ID 等于真实目标。修正后仅 AST 与定向差异检查，未启动新实例；第三轮由根代理统一复验。

本次修正脚本 SHA-256：`0ebe17201511043edc0367a3b73e68214a6e81943726fdd84e2911d2be4434f9`；AST 和定向差异空白检查通过，等待实际联合验证。

## 第三轮实测失败与修正

已只读核对外部 `business-presales-20261001-03/evidence/sales-presales-hk001-007/business-checkpoint.json`：HK-001/002/003/004/006 passed，HK-005 failed，HK-007 not_tested。HK-005 的两次原 follow 提交和原数据库历史核对已发生，但查看留痕时失败，因此仍不能记该项 passed，不能拼接历史轮次补齐七项。

原 `web/businessux.js` 将整个 `[data-panel-role="history"]` 放进默认折叠的 `details.ux-history`，失败画面底部“操作留痕”仍折叠。脚本直接点击内部“查看记录”，该节点处于隐藏祖先之下，属于测试 UI 操作遗漏。原截图、failed 报告和原数据证据保留，未修改生产或历史核对判据。

仅补原生展开流程：先实际点击外层 `details.ux-history` 的直系“操作留痕” summary 并确认 open，再按两次不同沟通结果精确定位各原 follow timeline item 的动态 summary，等待唯一/可见后原生点击。不冻结 `nth-child` 或事件 DOM 编号，不 force、不重试、不固定等待。原两次事件追加、内容、日期、身份、版本、唯一任务及不新增客户/接待断言保持严格。未启动新实例，由根代理第四轮统一复验。

本次修正脚本 SHA-256：`106fcd5c1aa27b96a09bc356b12d70f5b8a955b38d415508137bffdee7bb439a`；AST 与定向差异空白检查通过。七项尚未完整通过，等待第四轮实际结果。

## 根代理第04—07轮接续

第04轮售前7/7通过。manual01暴露未选查找进度缺陷；第05轮换角色登录503，整轮失败。对应生产补丁与原生负向先登记再实施。第06轮7/7、automatic-business01全14/14同次通过，但manual02仍暴露768px按钮在鼠标释放前移位；人工失败未覆盖。LOOKUP-POINTER修复后第07轮在390/768/1440px每次新开原表单，以实际鼠标触发未选拒绝，无POST且完整业务摘要不变；取消明确放弃，然后正确选择员工继续，七项同次passed/退出0。新目录外部为 `browser-click/business-presales-20261001-07`，不拼接其他轮次。原表业务与真实员工/生产环境验收仍不同。
