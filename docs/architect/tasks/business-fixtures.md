# 任务：实际业务点击的最小前置夹具

**任务 id 与负责人**：business-fixtures；test_inventory，向 browser-click 负责人报告。

**目标与范围**：依据 PATCH-M8-4-BUSINESS-193-01，首批只为 HK-001 至 HK-007 原售前接待、分派、跟进和提醒提供可登录身份；2026-10-01 依据 PATCH-M8-4-BUSINESS-193-02，为紧邻整车采购链追加财务和库管身份，再按 PATCH-M8-4-BUSINESS-193-04 为紧邻销售交付链追加服务顾问身份。只维护 `tests/browser_click/fixture_server.py` 与本记录。随机登录名/密码由负责人维护的 run.py 生成，密码只在新外部 runtime 凭据文件；本批不创建新的客户、接待单、意向单、任务、事件或提醒结果。

**原合同只读核对**：当前 HEAD `5069b2bcc9f580ebb9d70780769049a14a6de946`。已读 fixture、flow_specs、flow_engine、flow_api、flow_seed、customer_choice 与原需求映射。lead 新建允许 reception/sales/manager/admin，初始待分派；分派接待允许 reception/manager，目标本店启用 sales/reception。管理员沿原显式通用授权。转意向和接待回访须当前 contact 任务负责人，意向跟进须当前 follow 任务销售。HK-004 意向单分派使用原任务转交接口，仅 manager/admin，核对任务版本/本店/目标岗位，同事务更新任务接手人、原单负责人及仍属于原负责人的客户责任。HK-005 是意向跟进记录，不与分派混算。提醒依赖实际联系电话、联系意愿、下次处理日期和原 open 任务；原未来日期、停止联系与重复/冲突守卫保留。

**已有演示前置与边界**：原 demo 建两店和8种岗位员工，各店成员真实存在，但 demo 密码随机不可登录且 must_change_password=true；原新入口另有可登录 admin/sales，销售原双店成员保持。既有07外部合成库只读观察为两店各9成员、23条背景 lead（含上轮测试及读取样例），这些旧记录不计本次 HK-001 至 HK-007 业务结果。原 demo 已有供应商/车型/物资等背景，本批售前接口无需新增此类主档、车辆或订单。

**最小补丁实现与当前位置**：与 browser-scenarios 任务定稿并落盘：新增凭据 key reception、manager、sales_peer（实际 sales），仅创建本店1 User/UserStore，显示名分别为合成接待、合成主管、合成销售乙；原 sales 保留。manifest users 记录实际 id/display_name/role；`business_fixtures.presales` 只提供 store_id、reception_key、manager_key、sales_key、sales_peer_key。真实本批客户、原单、任务、历史和提醒由同事的实际 UI 新增/分派/跟进产生。原 initial_tasks 仍按本店接待任务负载挑选接手人，不强制选创建人；已提示场景核对真实分派人，必要转交也须原主管 UI 办理。夹具要求 runner 先提供三项外部随机凭据，缺失直接报错，不复用 demo 密码或提升原员工权限。

**首批历史静态核对**：仅有24行角色/manifest增量，Python 3.11 AST 和 whitespace 检查通过，人工核对新增3员工只授权本店1、原 sales 双店保持、未新增业务结果。该时 fixture SHA256 `25c3e304c7b7cca15a6ffd2659b970dd23d34aeb98f617a464f92eb506053df1`。此记录仅描述当时静态核对，不代替负责人后续实际点击证据。

**2026-10-01 整车采购身份增量**：负责人确认当前实例已停止后开放明确写入窗口。本次只增加 key inventory/finance，对应本店1启用 User/UserStore、实际 role inventory/finance、显示名合成库管/合成财务、must_change_password=false；密码从 runner 新外部凭据读取，缺项直接失败。复用已有 manager，原 sales 双店保持，demo 员工和不可登录随机初始凭据不改。`business_fixtures.vehicle_purchase` 精确为 `{store_id: 1, manager_key: "manager", inventory_key: "inventory", finance_key: "finance"}`；users 保存真实 id/display_name/role，不在此入口预置本轮业务结果 ID。

**原业务前置与验收边界**：HK-171 新供应商、HK-177 品牌/车系/车型、HK-178 整车仓库/库位均须界面新增；库管原采购计划、主管独立核价及请款、财务原付款、库管逐 VIN 发运/接收再形成 HK-018/HK-029 非空库存。价格、文件、付款、Shipment、Receipt、Vehicle、Custody 和 Position 不由本次夹具制造。此前空表单和读取样例保留背景身份，不计本轮主档或库存结果。原待办负载可能分给 demo 员工，先核对真实接手人，必要时主管用原任务转交 UI 办理；当前 AssignInput 只有 version、assignee_id、reason，无 request_id 或 expected_assignee_id。结构扫描只记本地 structure_only，不当 ClamAV 通过；合成资金和实物登记不声称真实银行或公司实物发生。

**只读账户与主体前置核对**：仅按已停止外部 `business-presales-20261001-04/manifest.json` 的标记合成 database_path，用 SQLite mode=ro/query_only 读取：本店1已有 active bank Account 1“门店结算账户（演示）”；EntityPolicy、StoreEntityBinding、AccountEntityBinding 各0。原 APP_ENV=test 且无主体策略时 operating_party=null、freeze_case_entity/require_account_entity 合法返回无主体上下文，不以此绕过生产策略；场景在原非只读抬头输入填明确合成采购公司，若后续运行有真实 operating_party 则遵从原只读抬头。新场景仍从真实 UI 选账户，不固定旧运行 ID；此读取不计付款或生产账户归属验收。

**采购身份增量历史静态核对**：AST 解析、两个新增岗位及四键 manifest 声明核对、限定文件 whitespace 检查通过。人工审阅确认只补两个本店身份和入口，未新增主档、订单、付款或车辆。该时 fixture SHA256 `217656c26a86d0d021327af67e3e77258c078bc4773976f3bb25aa890d11ee62`，当时未导入 app、初始化实例、启动镜像或联合测试，等待负责人接线后的实际点击。后续只读 `business-vehicle-purchase-20261001-03/evidence/run-summary.json` 确认为本次 selected 采购场景 complete=true、passed=true、exit0，7项自动检查通过，人工验收仍 pending、193完整业务验收仍 false；不是未测销售链的成绩。

**2026-10-01 销售交付身份增量**：负责人确认采购03退出、无当前应用或验证进程并登记 PATCH-M8-4-BUSINESS-193-04 后开放写入窗口。本次只增加 key service，实际本店1 User/UserStore(role=service)、显示名合成服务顾问、active=true、must_change_password=false；密码仅从 runner 本次外部随机凭据读取，缺少 key 直接失败。原 demo 员工不登录、不重置，原各岗位和 sales 双店关系保持；不新增技师或其他本链非必要身份。

**销售链入口与前序**：`business_fixtures.sales_order` 精确为 `{store_id: 1, sales_key: "sales_peer", manager_key: "manager", inventory_key: "inventory", finance_key: "finance", service_key: "service"}`，只指向上述实际员工。客户/意向和车辆必须来自同次浏览器售前、采购前场景；报价、独立批准、合同生成字节/本版签回、实收/退款、PDI、出库、交付及其任务/事件均须由原 UI 本人操作产生，不在夹具预置验收结果。原 v2 order 检查/整改/复检允许 service 本人原任务办理，无需增加 technician。只读已停止采购01标记合成库，store1 contract/handover 原模板 id1/id2、v2、approved=1、reviewed_by=1，首句均“本模板仅供虚构数据试用，不能用于实际签约。”，来源是原 flow_seed demo 初始化；本轮未制造新模板批准，不能当正式公司合同验收。

**销售身份静态核对与冻结**：AST、单项 service 元组及 sales_order 六键精确声明核对、限定两文件 whitespace 检查通过；人工审阅确认只增一个本店角色和入口，不预造业务事实。fixture SHA256 `614766ded87d36f8257acd573bc0470a09eeb66f4b1c1136c2adf55c42d3352f`。未导入 app、初始化实例或启动服务；此时销售候选尚未注册，等待负责人随机凭据接线并先进行已注册15场景完整复验。夹具完成后冻结，下一批仍按实际依赖增量补前置；生产疑点只交负责人处理。
