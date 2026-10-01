# PATCH-M8-1-RECONCILIATION-COPY-01：核账首屏与实际来源文案

2026-10-01，当前M8.1；只允许web/reconciliation.js展示文案、已观察来源与枚举中文映射、原生details的说明折叠。登记时生产及注册源仍冻结于automatic-business11/手动复核实例，本补丁尚未实施；必须关联进程全部退出后才改源码。

实际证据为V/browser-click/manual-finance-system-20261001-01/evidence/iab-reconciliation-{1440,768,390}-before.png，同源0ce46e44/脚本63e28f37。原UI建立并独立封存三版后，IAB本人原菜单进入版本3，真实打开/取消复开表单并钻回原凭据/待办。五段历史版本介绍常显，核对要点的实际DOM top为689.36/805.33/1035.21px，手机首屏看不到核对金额；明细实际显示business_finance_advance_entries、sales_quotes、vehicle_positions等内部表名以及receive/correction/applied/stored等原枚举。三个宽度均无页面横向溢出，但文案简洁性低于3分，不能记人工通过。

最小修正：当前真实期间金额、未收款、差异、原单和可用操作先显示；详细历史版本/现金统计口径收进可展开说明，保留全部原区分及本版本排除明细。原source_changed真实警示和历史需重算范围提示仍常显；不改后台22/7定义、金额、来源、CSV、冻结版本、状态机、权限、确认/任务/CAS或事务。

有限中文来源只补本次可见的预收流水/原账户、抵用退款申请、客户收退批次/分配、原账务更正、维修套餐购买事件、报价/知情/复核、代办原单/项目/报价/价格复核/授权/履约/分配以及整车库位/流水。枚举按真实来源区分：预收receive为实际到账、correction为账务更正、apply为抵用、refund为退款；applied仅表示该原申请已办理，不冒充到账；旧会员topup为充值、原库存purchase/issue为采购入库/出库、车辆stored/exited为在库/已出库。不全局翻译未核来源或变更原服务判断，未知原值不猜状态。

联合11的冻结来源实际亦包含addon_dispatches/inspections/installations/lines/orders/payments/quotes/rectifications/reservations/targets十类加装原事实；本次同层有限标签分别补实际出库、验收、实际施工、项目、原单、收退款关联、报价、整改、库存占量和原款目标。原引用/凭据号码优先原样展示，不能把恰为refund等号码误译成状态。关联实例全部退出后才实施此有限展示补丁。

独立短审发现service_orders原subtype同时含agency与other_income；上述七类service来源统一使用中性“客户服务原单/项目/报价/价格复核/授权/履约/收款分配”，避免将其他收入原事实误标代办，不改来源键或金额。其余三展示/观察补丁Node、AST、差异及独立短审通过，真实新镜像待做。

实施后Node语法与独立只读短审，再新鲜外部原生三宽度实际展开/收起、原凭据钻取、原表单取消及后台全行摘要核对。没有真实修后证据前不补分；本定向复核不替代193全部业务人工接受、原外部环境/员工/模型及生产门槛。
