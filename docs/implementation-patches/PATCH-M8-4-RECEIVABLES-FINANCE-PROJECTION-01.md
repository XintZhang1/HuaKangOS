# PATCH-M8-4-RECEIVABLES-FINANCE-PROJECTION-01

2026-10-01，当前连续点击交付内先登记，finance04 关联CLI未退出，生产/registered/runner仍冻结。receivables03 的补材料采购118独立批准、实际预付1000分与原收货1000数量/1000价值均成立，原Case已completed/v10、Task均done、原支付/现金/收货/库存来源一致；候选317却从本人库管的原订单GET读取 totals。该岗位原 procurement_service 明确省略财务金额，KeyError不是业务付款或到货失败。

所有关联CLI收尾后只修改 receivables_business.py 的 material_precondition 收货后的核对：保留本人库管的原 inline_receive、批次/库存/完整回执与旧行守卫，并明确核该投影不含 totals；随后复用原 MAT.detail，以有本店财务权限的本人登录原相同采购118页，原GET200/当前店/Cookie/可见状态和全业务零写入核对，再从其 totals 严格核 payable_cents=0、paid_net_cents=1000、completed及当前数据库一致。保存该独立财务读取证据，不把它改称库管响应、不给库管新增金额、不直接正向HTTP/SQL写、不借管理员或重放已成功付款/收货。

原全表/全旧行保护、金额精度、原单身份与三个应收全店oracle不降低。新fresh同轮闭包重新办理，旧失败/源码/实例原件保留；AST/独立增量审查后复验应收，随后当前指纹全注册联合。四生产开关与193人工、真实时间/环境/模型/员工/生产条件不变。
