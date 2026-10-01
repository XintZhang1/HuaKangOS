# PATCH-M8-4-INVENTORY-ACTUAL-PURCHASE-01

2026-10-02，M8.1。automatic-business16 完整执行53项，52通过、HK071失败，整体failed/CLI3；UTC19:58:50原runner正常收尾，关联Python已退出，provider合成16/真实0/阻外0。原报告、失败、图像及权限清理事实保留，不继承至新轮。

原HK071 checkpoint确证：item9总量/可用2250 milli，源库位2余额250 milli/250分，目标库位3为2000 milli；retail/addon/holds/transit/approved_return/count均0。materials终局源位5250，维修100净-1250、会员组合零售135 -1000、会员价格零售164 -1000、保养包维修179 -1000、跨店材料185净-750，结果250。500移库保护正确拒绝；未创建移库，失败路径已原UI恢复员工19的仅店1manager/group=false权限。不是生产库存不足判断错误。

只允许 tests/browser_click/inventory_scope_business.py 与 receivables_business.py 的必要接线/准确单位文案。HK071从同轮原材料采购源取得当前item/supplier/warehouse/source location/bank account及真实inventory/manager/finance，核本店、启用、原仓位关系和有限原ID；无SQL/API造库存，复用既有material_precondition，经原UI另采1.000升、单价10.00元、独立请款批准、实际支付1000分和源位收货1000milli，完整保存原全行守卫、receipt/现金/库位事实及证据。始终明确执行该必要采购，不按不足时静默fallback，不改原移库500、源位2、成本、预占、围栏、权限/会话撤销和清理检查。先取得新实际库存，再进入原员工/门店查询及移库链路，旧期初/定义/盘点及此前消耗保持。

共享helper只将“精品一件”及点击标签改为以原item.unit表述实际1.000单位、10.00元，其签名/固定数量价格/请求/金额转换/业务守卫不变；避免将升材料误称件。不改生产、catalog、53注册、45白名单或runner/CI预算，未证明超时不改预算。独立源审与静态检查后，在全新外部镜像原入口重验；新指纹不得拼full16为全量，真实Date/原环境和193完整接受仍依原证据。
