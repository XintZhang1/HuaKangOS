# PATCH-M8-4-BUSINESS-193-26

2026-10-01，M8.1 当前浏览器点击补丁，延续原193表授权。允许新增 tests/browser_click/interstore_business.py 与 docs/architect/tasks/interstore-business-click.md；其他生产、fixture、helpers、runner、scenarios、catalog、计划只读。未注册候选不进入正在运行的镜像。范围依据 interstore-remaining-scope.md，SHA256 79d5c985eae4c57d3f007685a79c6bec9ab773087a7502ccb084a34cec69bfea。

拟完整原HK020/024/047/055/084：一张整车调拨实际验收、一张物资1000milli调拨两次实收500/250及拒收250原返、第二可用VIN另单拒收退运原店新代次接收；原实际验收三条往来逐条付款店pay及收款店receive，双店现金与库存成本守恒。完整024含第三张原单拒收/return_ship/return_receive，不以两张主单覆盖替代。

固定同轮原采购/主档/物资/车辆操作/sales-cancellation完整passed报告与有限来源。第二车现场无hold/原单占额且明确可用，不借已交付或已退供应商车；原成本、身份、Custody与Position代次真实核对。新二店manager/inventory/finance仅由原admin新增明确UserStore后各本人首改随机密码；账号级sales与当前店岗位分开。新密码仅外置私密runtime并加入Evidence秘密脱敏，原UI创建二店账户、两种仓/位、同SKU/name/unit零Item与零activate，不修改旧员工/权限、fixture或SQL造前置。

所有业务提交原页面实际可见控件，旧行按动作有限守卫、双版本/任务/整数分与milli/正确回执家族/双方独立证据保持。附件不借admin读对店；任何普通下载若真实违反对店scope，保留失败另登记产品修复，不绕过或放宽。清算只对三条实际正验收产生的往来，不虚构拒收单现金。无未知结果盲重放、跨run最新行或整表豁免。

作者自审AST/当前API/schema/源指纹后冻结，根独立短审，待关联验证进程全退出再注册和新鲜执行。未执行不记五项通过；损坏/短缺/找回/赔付/撤销差异/所有异常、跨店文件指定授权、真实银行/PG/Linux/员工及生产均保留待测，不改total_plan、里程碑门禁或四开关默认关闭。
