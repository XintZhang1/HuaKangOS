# PATCH-M8-4-PACKAGE-CHOICE-VALUE-01

2026-10-01，M8.1。全部关联验证进程已收尾。精确仅 tests/browser_click/repair_packages_business.py 的 apply原单选择。

packages-claims02 的套餐在真实选择原修单后断言label等于原生value失败；原 web/repairpackages.js packageChoose option.value为本次候选数组索引，label是单号与标题，实测value=0。按唯一准确原单label找到唯一option，读取该option当前value再选label并核value及选中label；不能硬编码0、默认第一项或放宽目标Case/当前版本/会员/Lot守卫。其他共享helper/生产不改，旧失败保留，再以新实例执行原套餐整链。
