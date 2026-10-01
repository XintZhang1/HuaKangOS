# PATCH-M8-4-PACKAGE-ALLOCATION-DEFAULT-01

2026-10-01，M8.1，四关联运行已退出。套餐05 原allocate已200，实际接待/报价/原套餐占用/授权/施工/领料/质检已走至结算，回执digest比对缺原Allocation schema的payer_name空串默认。仅 tests/browser_click/repair_packages_business.py 的该动作receipt临时标准化副本加payer_name=""（显式原UI值仍覆盖），与已完整核赔场景同原schema；不修改原提交body、原记录、版本或金额。未知后继不报通过，返修因套餐未完成仍实际工位占用而未执行，保持原守卫，重验须先完成原套餐。
