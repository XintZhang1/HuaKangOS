# PATCH-M8-4-BUSINESS-193-25

2026-10-01，M8.1 当前浏览器点击交付补丁；延续业主逐需求表验证授权，不新增里程碑，不改 total_plan、原验收或生产开关。

允许新增 tests/browser_click/repair_packages_business.py 与 docs/architect/tasks/repair-packages-click.md；其余源码、fixture、helper、目录、runner、计划只读，候选先不注册、不启动。根审阅后在全部关联进程收尾的窗口另登记注册。范围依据 packages-remaining-scope.md（SHA256 59fbc5bf650a9c09e7e087a2429a8bca9b6c1cfffd16b020e111e0ca1aced4c4）。

目标 HK043/HK133/HK126/HK127 原完整 business check：新混合 PackageRule 作业与配件独立批准、本店真实映射；同会员同客户新维修宿主申请购买、客户本版授权、财务实际收款2400分发行；各1000milli实际施工/领料/质检/分摊及原组件核销，C/P/S=1500/1200/1200；原UI分别办理作业800分、配件400分未用区间退款，独立批准及实际原账户退款；停止新购买不改已售合同、报价、Lot与旧现金。不得以旧次数权益、夹具 package1、规则提案或导航覆盖替代。

固定同轮前序为 membership/material/master/repair 的真实 passed 报告及有限来源，必要上游沿既有真实依赖。原已交车修单只提供客户车辆/工位事实，另从原预约/到店/转换生成新未终态工单，不复用其作为购买宿主。当前库存、门店岗位、任务、Case/源版本和真实凭据即时核对；数据库只 SELECT，正向业务仅原页面点击。

原UI单组件退款意味着两次真实申请，不伪造数组请求；PackageRefundClaim 与旧 RefundHold 分开，GroupReceipt 与 repair_v3_quote FlowReceipt 按真实执行器断言。原权益、钱包、已售快照、原现金及全部旧行按动作收窄保护，金额整数分/数量整数milli。若同轮有效积分来源已 passed，则按冻结原规则保护并核对正常赠分，不为测试禁用；否则不继承静态会员候选为真实来源。

异常仅取本路径的实际守卫与真实拒绝，403 rule/refusal 精确追加，422/409 与UI零提交分开。已耗材料售后实退、停工、过期、跨店、全部异常、真实银行/病毒扫描/PostgreSQL/员工验收均待测。无运行结果前只记候选与静态审阅，不登记四项通过。

作者核源码发现原repair前序CV属于customer-service新客户，会员来自sale客户，两者不同；原“同会员沿repair客户车辆”来源建议无效，不能跨客户套用或改旧关系。允许仍只在本owned候选由原客户车辆UI为有限membership客户新建明确合成CV（新VIN、真实关系资料/GroupIdentity），再原walk_in/arrive/convert建立本客户v4新宿主。repair父只复用真实工位及守卫合同，不复用其旧CV/客户/终态工单作为购买事实。原会员、原客户/车辆、旧repair及各已授权报价保持，全库Guard仅精确新CV/关系与本次原事件追加。无fixture、生产或额外作者文件范围变更；先登记该实际必要前置再实施。
