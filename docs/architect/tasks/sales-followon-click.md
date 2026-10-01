# 交车后加装、代办及其它收入点击候选

2026-10-01，依据 PATCH-M8-4-BUSINESS-193-11 和已冻结范围页 `sales-followon-scope.md`（SHA256 `65f2f90ea82b92c746921eb24ce05ce5f1d16c17a483d530127bd3ad2312ac1c`）。仅新增 `tests/browser_click/sales_followon_business.py` 与本页。没有修改生产、fixture、共享 runner、注册、目录或计划，没有导入应用、启动服务或执行业务。当前是未注册候选，实际浏览器与人工评价仍待负责人集成后执行。

## 四个独立自动检查

入口 `sales-followon-hk012-015-016-017`，函数 `sales_followon_business(e, context, credentials)`，导出 `SALES_FOLLOWON_SCENARIOS`，候选超时上限600秒，未测实际耗时。

| check_id | 原业务范围 | 本批原输入到结果 |
| --- | --- | --- |
| HK-012-business | 精品加装单 | 本轮已交付原销售建立非阻断加装；一件明确原商品30元和安装5元，销售报价、另一主管批准、客户本版授权；库存本人准备明确库位、原VIN实际发料；技师安装，另一服务顾问实际不合格检查、技师整改及独立复检；客户接收与财务实际35元到账分别留原事实。 |
| HK-015-business | 代办服务单 | 原销售客户建立代办，服务费与10元代缴本金分开；财务实际35元到账，明确原本金向本次原代缴单位实际支付10元；两个原明细各自提交、外部批准并办结，其中服务费明细先要求补件再引用该原结果重新提交；不得用建单、资金或一个明细办结冒全部结束。 |
| HK-016-business | 代办核价单 | 实际资金和履约前，第一版服务费20元、本金10元独立批准和授权；第二版服务费25元、本金10元再次独立批准和本版授权；原行键、旧版本、摘要与原历史保留，原UI展开两个冻结版本；后续实际款与办理使用第二版。 |
| HK-017-business | 整车其它收入单 | 客户源A：本次明确其它服务项目8元，服务顾问建单/报价，另一主管批准、本版授权，实际履约与财务到账，禁止虚构外部代办。厂家源B：同轮原供应商及已交付原VIN、不可变配车事件，原结算目标100元、独立批准和实际到账；追加有据70元目标、独立批准，财务明确选择原VehicleIncomeCash.id及同原账户实际退30元；旧实际收款保留，最终目标与净收均70元。两方来源全完成才允许该自动check为passed。 |

## 原来源、身份及证据合同

只读取同一外部运行中已注册且实际passed、完整checkpoint的四个固定场景：销售 `sales-order-hk008-009-011-022`、采购 `vehicle-purchase-hk171-177-178-026-021-018-029`、主档15项、物资9项。比较相同catalog、provenance及当前白名单脚本指纹；不搜索旧运行或猜本地编号。最短前序为售前→采购→主档→销售及物资→本候选。已经注册的其它前序如何安排由负责人接线；本候选不继承其余需求通过数。

原商品取本轮物资secondary的item、实有库位、启用和采购验收来源。开始与报价、实际发料前均重新读取当前量及可用量；安装数量1000千分之一，原移动平均成本按原实际账核对。所选库位减数量，可能发生的其它同物资库位价值重估仅允许零数量average_revaluation；总数量和价值与原Item一致。库位prepare只新增准备，实际库存和流水不变，实际dispatch才新增StockMove与WarehouseEntry并consume该Allocation。

复用现有sales_peer、manager、service、inventory、finance、technician；没有新增账号、借用admin或后台代办。每一步真实登录完成后取基线，读取同原单当前GET和CAS；非本次本人原待办仅由主管在原UI明确转交有限原Task。厂家审核明确排除原创建人和本版提出人。换员工登录的合法原login审计发生在业务基线前，旧审计整行仍保护。

所有正向写入只点击可见原表单一次，经同源Cookie/CSRF和当前店提交原POST。每步核对当前version、唯一request_id原回执、同本人追加事件、关联原单及真实原事实。没有直接业务HTTP写、SQL写、App导入或结果不明自动重放。失败后停止，当前项failed、已有不完整前序partial、后继not_tested；已执行动作保留，不改请求号重放。

原Task交接独立沿AssignInput三字段version/assignee_id/reason，不带业务request_id。交叉短审发现首次候选统一读取request_id会在该合法交接成功后产生KeyError；当前精确适配仅`/api/flow/tasks/{id}/assign`单一调用，核对三字段与明确原因、Guard照常核对，证据request_id_sha256为null。其它非multipart业务封包仍必须有request_id。此项是执行装置静态错误，未发生对应实际重放或业务失败。

写守卫保留全库其它业务表哈希；允许表内保留所有旧行及原字节，只开放本次明确Case/Task/Item/Balance/Allocation/Account的有限ID与列、关联父销售源码明确的version/updated_at，以及本步关联原事实的新增行。其它店、其它原单、旧库存、原现金、签回、版本、附件和回执均不能覆盖删除。厂家派生不修改原销售；目标修订与批准不得自动生成或覆盖现金。

独立原件由当前员工在原上传UI选取仓库外合成文件；每次不同实际内容与SHA，按后端动作分别使用authorization/inspection/evidence/receipt。原件实际数据库BLOB只在内存核对类型、长度和SHA，checkpoint仅写文件metadata、长度和SHA，禁止default=str/base64化正文。沿原structure_only扫描与can_use，不冒ClamAV、真实签字、银行款、现场安装或外部机关结果。

## 静态审阅及未测边界

生产附件接线只读审阅：serviceorders现金和termination_apply为receipt，其它原非取消动作与方案为authorization；vehicleincome非现金evidence、现金receipt，与原服务逐action `_proof` 一致。后端原件安全、重复SHA、权限、状态和版本守卫没有由本候选放宽。

库位事务接线独立只读审阅：get_write_db在SQLite认证首次读取前通过同一缓存get_db Session开始BEGIN IMMEDIATE；get_audited_read_db保留同函数别名及三个原CSV依赖，普通GET、其他command与PG保持原合同。没有自动重试。writer等待仍受原30秒锁超时，本候选不宣称所有SQLite并发已解决，不把无请求path日志517绑定为原prepare的精确错误码。

静态核对：Python AST通过；26处e.db.rows均以SELECT开始，未发现直接HTTP mutation或应用导入；四个check_id与source_reviewed目录相符；无附件正文序列化捷径。脚本1073行，SHA256 `017c7610a71bca55c6cb8fa6ab17c3075f22d49320f190c83f1fddf95fed71f3`。click_scenarios对前候选完成独立短审，仅发现上述AssignInput适配错误，其余未见确定静态误配；该窄修已重新AST核对，单一request_id例外调用确认，最终增量交叉审阅待确认。任何静态结论都不代表实际通过。

零价赠送、拆回/取消/随车移交、原客户退款、代办第三方退回/终止保留费/客户退款、已履约行改价、多车厂家结算、门店开票及退回/撤回等分支逐项保留conditional/not_tested。HK013/014保险是独立后批，没有本批check。自动passed只能证明执行过的UI/API/DB断言，简单流程与简洁文案等人工criteria保持pending；business_accepted与full_193_business_acceptance始终false。真实模型、PG/Linux、ClamAV、真实外部手续、员工试用和生产发布门槛仍待各自证据。
