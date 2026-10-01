# PATCH-M8-4-PACKAGE-WORK-LINE-01

2026-10-01，M8.1。全部关联验证已收尾，精确仅 repair_packages_business.py Guard的当前work有限ID及混合原套餐报价调用。

packages-claims-rework03原报价已经生成两行，但Guard错误要求纯作业行item_id也等于材料ID。原RepairLine合同明确kind=work时item_id=None/work_item_id真实；part相反。仅repair_lines新增work行允许None且必须kind=work、work_item_id等于本次已核work参数；非空item仍只等本次材料ID，其他表的None不豁免。当前报价调用带入明确workID，后续两个Lot/Quote/Line/数量/金额快照关系校验保留。旧失败原件保留，守卫不能笼统允许所有空物资。
