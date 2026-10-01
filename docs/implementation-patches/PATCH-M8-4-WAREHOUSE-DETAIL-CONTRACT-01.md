# PATCH-M8-4-WAREHOUSE-DETAIL-CONTRACT-01：原仓储详情的实际字段合同

2026-10-01，仅tests/browser_click/warehouse_operations_business.py的detail读后对照。其他关联实例仍活跃，注册文件暂不编辑，全部关联进程退出后实施。

business-warehouse-operations-20261001-01完整所选4为3passed/1failed、退出1；新增耗材原主档、零库位启用创建已经实际发生，原manager登录后读取详情时HK046在KeyError title失败，后七项未启动。原Warehouse.describe明确仅返回Case的id/number/state/version/store_id/business_date/due_date，另含operation/item_name及文档原事实，没有title；FlowCase原记录和通用详情确有title。候选误将两个不同详情合同混用，属于执行观察错误，不是原UI缺业务标题。原失败完整保留，不能记新八项通过。

最小修正保留仓储原返回的七Case字段逐项DB对照、operation_label与本批固定原作业/物资对应、页面h1及原单号可见；仓储API不要求不存在的title。财务嵌套case和通用Case转交待办仍严格核真实title。全部原文档字段、金额权限、数量/成本、Task及接手、有限Guard/旧行/其他店、整数和原UI提交不变，不放宽权限或补造字段。AST/根及独立短审后全新采购/主档/物资/仓储八项原UI复验，不改生产或helper，不继承旧成绩。
