# 当前店完整采购来源与仓库期间功能点击候选

2026-10-01，按 `PATCH-M8-4-BUSINESS-193-38` 实施。仅新增本人候选及本页，没有运行应用、浏览器或测试，没有修改生产、夹具、注册、runner、目录、计划或旧证据。本页描述候选覆盖；不登记两项已经通过。

入口为 `reports-complete-source-hk152-153`，导出 `REPORT_COMPLETE_SOURCE_SCENARIOS` 三元组，限时1500秒。两个独立检查为 `HK-152-business`（物资仓库入出存统计）及 `HK-153-business`（物资采购订货统计）。根接线、稳定镜像、独立短审与首次真实执行均待做；空执行、父未通过或任一断言失败不能记场景通过。

同轮依赖固定读取 `system-management-hk189-191`、原整车采购、原主档及原物资九项四份完整 passed 检查点和父 runner 状态；`fixed_dependency` 核对当前目录、完整check与目录指纹。候选额外核对稳定 provenance、本人及复用helper字节。只使用系统父 `HK-189` 的实际新店 actions／原新增门店 Audit ID；当前店必须 active、非初始两店且确实没有任何原 Case、Item 或 Cash。既有第三店没有旧业务不等于报表成绩，此候选仍须原UI新建非空来源。没有合格前序即失败，不扫描 latest／跨run取旧单，不删旧简表、不改时钟。

原三个不同员工来自 `business_fixtures.vehicle_purchase` 的 inventory／manager／finance。先以三个独立浏览器上下文真实登录形成原会话；管理员在原员工表单逐店保留原账号默认岗位、启用、汇总开关与全部门店岗位，仅追加新店对应角色。每人核原 access_version +1、原请求规范指纹、唯一 UserAccessReceipt／全局 Audit、精确派生 Wake 门店集合、所有旧Wake及其他员工／旧业务／旧会话保护，并从被撤销的旧页面真实读取401。业务员工本人随后原生登录、原切店控件取得当前新店岗位；管理员不代办采购、实物或资金。

原主管在新店原管理UI建立供应商、物资品牌／分类、materials 仓、两个原库位及独立 bank 账户；原库管建立零库存 Item 和真实归类。原 Item 的单位是原表单文本字段，显式输入“升”，不假造单位字典外键。零库存原库位启用申请明确一个真实位置数量0；上传外置合成依据后不同主管批准，唯一 Enrollment／原批准／consumed Allocation 及同位置零分配行、一个零 Balance 和原事件可核。零数量、零价值不生成 WarehouseEntry 或 StockMove，不能把启用当进货。

新店原采购一行2.000升，单价10.00元：原库管申请，不同主管批准；两次本人原收货各1.000升，分别通过原内联库位准备选择两个新位置，并消费本次 Allocation。原 finance 实付20.00元到本原账户；第一实际收货批次申请原退0.500升，主管独立批准，原库管准备第一原位置并确认实物发出，原 finance 引用同原付款／账户实收退款5.00元。附件由原UI实际选择上传；原存储字节仅保留哈希／长度元数据，结构检查不称 ClamAV。资金与库存分事实核对：最终两位置数量500／1000千分位，门店数量1500、价值1500分，原净付款1500分，应付／应退／预付均0。Case／本人Task／版本／规范RequestReceipt／事件、原验收与退货 StockMove、原账户付款与退款必须一致。只有同组合法本人的明确Task交接走原主管表单；不借admin、SQL或HTTP绕写。

每个正向原提交前建立独立当前店 Guard：动态全原业务表摘要比较，允许有限本次 append 表及当前明确 Case／Task／Item／Balance／Allocation／Return／Account ID 的原可变列，所有其他旧行、资金、库存、会员、其他门店和旧文件BLOB保持。新行核当前店／有限原单／物资关系；原上传复用首维修只读字节校验和外置元数据。每次本人登录后再建动作基线，不用四表计数代替旧行保护。

HK153先核整个第三店只有本次原采购、没有 legacy purchase；按不可变创建事件本地日查当日原批次，而不是按收货日查批次。独立读取整店 Line／Receipt／ReturnPosting／StockMove，核原订货2000＝累计到货2000＋其余0，实际退货500、净留存1500，七类整数数量／金额及原 KPI 全吻合。原三表完整DOM、非空“升”单位 SVG、三基础CSV与动态图原始行CSV全部同范围；从真实累计到退货行钻回同原单。完整来源必须 true、差异空，未知或旧简表不能被吞掉。

HK152分别查询整店和原可见物资／仓库候选筛选。独立从本次 Enrollment、唯一 warehouse_approve 时刻、已消费的零初始 Allocation／同位置零分配行、全部实际库位 Entry／StockMove 与两 Balance 重建整范围 oracle。原启用基准没有零 Entry；仍按原分配位置和批准时刻保留一条数量／价值0的报表 baseline 及原批准单钻取，真实收退流水独立进入明细。真实当日启用不能支持午夜期初，因此 API opening／in／out／revaluation 保持 null，period_complete=false，明确可见覆盖缺口提示；各期末数量／价值和 known_in／known_out／known_value_delta 与原不可变流水严格一致，closing_complete=true。原完整三表字段、基准不是进货、原数量／分换算、已知15.00元期末SVG、三CSV、启用原单钻取均验证。该项只记原功能分支完整检查，**真正 start 严格晚于真实启用日的完整历史窗口仍 not_tested**；不改日期、补零或把期末图称全期间图。

每次CSV只从实际浏览器下载文件读取字节，核原 headers／所有行／顺序及 formula safety；请求原 Cookie／本人当前店／原查询参数严格一致。导出仅追加一条本人本店、精确表／期间的 Audit，旧审计和全原业务不变。没有后台正向请求、响应替身、API业务重放、隐藏select注入或前端state写入；所有填选／提交／原单跳转由原DOM真实点击。

完成两检查后再次用三个独立真实本人新店会话核授权，再管理员原UI恢复三人原全部岗位；版本必须原值+2，第二回执／审计／Wake和被撤销会话再次核对。本人重新登录只见原授权店和岗位，第三店选项不存在，旧token不能复活。恢复失败仍令整场失败，不先把两局部检查当场景完成。未知业务结果停止，不自动重放业务提交；失败检查点和原证据保留。

成功才输出 `business-checkpoint.json` 的两个 passed check、有限 `report_sources` 与 `original_access_restored`。来源包含 store／supplier／account／item／warehouse／locations／enrollment／activation_case／purchase_case、原 receipts／payments／cash／stock_moves／entries及期间与已观察整数结果。状态始终保留 business_accepted=false／human pending／full193=false；不继承旧 partial／不同run成绩。人工六标准、真实日期到期、历史完整窗口、真实银行／模型／PG／Linux／员工／扫描和生产门槛独立待测。

静态核对：原 `inventory_reports_api.py`／`procurement_analytics.py`／`warehouse_period_analytics.py`、原 web/procurement／warehouse／inventoryreports、原授权服务和复用 helper 实参／返回结构已逐段对照。自审发现原十五主档helper不含suppliers，现仅在本人typed函数中为供应商保存加原UI专分支，核原 MasterReceipt 的 `master:suppliers`／id=None／version=None／原values指纹和唯一Audit；其他kind保留已验证helper，不扩大它的TABLES或调用硬编码第一店的旧材料Guard。

首次冻结静态检查：源码1081行，AST成功；复用 M／SYS／ACCESS 的必需实参核对无缺项；23处直接数据库调用均为SELECT-only；导出为外层tuple／一条三元组／1500秒，两原标题／check ID与现目录一致；UTF-8无替换字符或零宽字符，owned空白检查通过。历史源码 SHA256 `b64b5588e80c7adfd63b9caee506b0286421f78b5414582075ffa5535dae4efb`，历史文档 `9ceaeb6ea7e330a076790edb9a66636bc37a77861cc627ee358d95b77673ece1`。该版未注册、未执行；首次静态审查不足以证明其零流水断言正确。

独立审阅发现首次候选把真实零启用误要求为一条 WarehouseEntry；按 `PATCH-M8-4-REPORT-ZERO-ENROLLMENT-01`，关联52四个实例退出后，仅本候选／本页修正。原 `warehouse_service.py:262–268`／`warehouse_stock.py:96–98` 明确0／0只生成零余额、Enrollment、原批准并消费分配；原 `warehouse_period_analytics.py:59–62`／`135–138` 仍从分配位置输出零 baseline。候选收紧批准 Guard，禁止 WarehouseEntry 追加；两处改核0 Entry，保留唯一完整原分配、零行、批准、Enrollment与后续不变核对、原期初未知／真实期末、三CSV／图／钻取。没有后端修改、零流水补造或业务成绩新增。旧源码和文档逐字保存在仓库外 `C:/Users/tiefu/.codex/HuaKangOS-agent-validation/runtime-v1/browser-click/static-candidates/report-zero-enrollment-20261001/`，文件名由旧SHA加原文件名组成，可恢复原件。新冻结指纹与独立增量审阅交根；真实执行仍待调度，静态检查不等于实际业务通过。

零基准修后冻结：源码1111行，SHA256 `f13e7c75fe8f6abeeb187a9c0196e3b8dbcb96f0974dbb7db2179806ded59056`。AST／27处直接SELECT-only／tuple三元1500秒／无app导入／UTF-8与空白检查通过；新增有限原分配查询只读取本case/item及其唯一line，helper必需实参无新增缺项。该源仍未注册、未执行，不登记任一需求passed；独立增量审阅与同轮全新真实UI验证待根安排。
