# PATCH-M8-4-BUSINESS-193-07：本店物资采购、原预付及库存实际办理

日期：2026-10-01。继续193原业务点击目标，沿同一次原主档及供应商来源，先完成一条本店材料输入到库存结果路径，作为维修领料真实前置。

精确范围：新增`tests/browser_click/material_business.py`并维护`docs/architect/tasks/material-business-click.md`。本批九项自动check仅HK-069/045/054/083/070/072/073/051/061：原采购预付申请、另一主管批准与财务实际原付款；两行材料采购/独立批准/分批到货及按批次抵用和尾款；非空补货/材料库存/原仓库查询；按明确原到货行退一份，释放预付抵用后从原prepay Payment同账户实退；有据正负及零盘差、捕捉后库存变化原桥接；同店原移库分批出入及位置账守恒。

前置必须是本轮已passed runner及固定master HK183 Item/Profile、HK184真实材料仓/位与purchase HK171 Supplier checkpoint，指纹/有限原ID再次只读核对。第二材料、第二库位、实际activate、采购款项、到货/盘点/移库原凭据和库存余额全部走原UI。fixture不增加任何业务成果或身份；已有inventory/manager/finance本人即可。不从demo/旧run/最新余额猜选来源，不直接SQL或业务API制造结果。

金额整数分、数量整数千分位。原采购/Prepay/Payment/Receive/Return/StockMove/仓位流水/事件/任务及版本分别核对，旧流水/原款不可覆盖；按真实释放来源选择original_id，已抵用预付不当作可自由退款现金。正向办理需原同源Cookie/CSRF/CAS/request_id及独立批准，失败或未知结果停止而非重放。后继维修仅取本场景同轮明确原物资/库位/启用/到货ID。

本候选未注册可与根已冻结验证并行写本人两文件；根短审冻结后仅接run.py白名单、scenarios.py原注册/汇总、README和任务索引并全新镜像执行。发现产品缺陷另精确生产补丁。HK055/047/071跨店调拨，精品/耗材/礼品/维修/加装及其他材料分支另实际源，不冒本批通过；人工与193完整业务、真实模型/PG/Linux/员工/实物/银行及发布条件保留。
