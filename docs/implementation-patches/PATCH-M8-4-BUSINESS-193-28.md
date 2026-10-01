# PATCH-M8-4-BUSINESS-193-28

2026-10-01，M8.1，延续原193需求表实际点击授权。全部关联 vehicle04/member-boutique03/customer02 已终局退出，允许根只维护 tests/browser_click/run.py 的SCRIPT_FILES、scenarios.py 两import与BUSINESS_SCENARIOS原顺序接线；不改fixture/catalog/helper/业务接口/原193门槛或total_plan。

登记已冻结和独立静态审阅的九项候选：repair_packages_business.py c75a016894f3c865a5aced106ec625422bdacb4a77dab847a0977eb3aff1b50b（PATCH25，HK043/133/126/127）；interstore_business.py b389cc6f1ca44588abb8cd7f5620d3e0955fe48b032862769816c633dab35632（PATCH26，HK020/024/047/055/084）。根审套餐当前源/API/web/models/helper和七SELECT、作者以外test_inventory审跨店双店/CAS/整数成本/三清算六Cash/原拒收返运和16SELECT，均无确定静态阻断；均未实际执行，人工仍pending。

在精品/积分/客户后放套餐，当前有效会期必需同轮积分完整passed并核真实12消费积分；最短独立套餐闭包可明确无有效会期，保留null claim且不借静态积分来源。跨店需原采购/主档/物资/车辆作业/退订及七前序真正同轮passed，车辆A只当前新代次、B只原退订已释放VIN，不能使用已退供应商车。两原1500秒三元入口保持，首次定向失败/超时/缺父均不得记通过。总运行1800秒及CI40分钟当前不改，真实运行预算不足另以实测登记。维修索赔五项仍owned未注册，不进入本次镜像。
