# PATCH-M8-4-BUSINESS-193-13：客户预收、更正、应收与分笔月结

2026-10-01，业主193项实际点击持续授权，依据冻结`docs/architect/tasks/finance-next-scope.md`（SHA256 `f7c9c637595f0af8fa79310b07d603b1f0c8945190eb013f9f5a9e08c4610ffc`）。只新增`tests/browser_click/finance_business.py`及维护`docs/architect/tasks/finance-business-click.md`，原生产/fixture/注册/共享脚本和计划只读，不导入app或启动实例。

五完整候选check HK087/090/091/093/096；同次销售customer_id、采购HK021 account_id及原service/manager/finance身份，原UI创建一收费项目和两张other_income各6000分。客户预收明确合成误录10000分、真实核对正确9000分，独立更正批准/执行必须保留原冲正和正确重记，不拿退款替更正。抵用A4000只调整Advance与原应收不二记Cash；A2000+B6000实际冻结8000分月结，分笔3000及5000逐原分配；原预收余5000经独立批准退同原有效账户。最终两单应收及Advance为0，真实净Cash12000分，会员本金/权益保持全行不变。

必须保留每步实际原收款本人任务、原业务/Member/Case/Statement版本、CSRF、幂等、金额整数分、原账户、原款未退/占额/可用量及同事务回执/审计。正业务只原UI；来源缺失或错误停止留证，不用API/SQL造事实、不换请求号重放。原文件类别和字节分别核验，仅metadata/大小SHA进入报告；全部旧原单/现金/库存/会员/附件保持，有限原新ID更新列与追加记录单独核准。

HK090本批advance来源，更正group本金及已退/套餐组合支路按冻结原目录conditional另列，不能声称全部异常已执行。HK017/088共享客户服务仅partial，厂家原源未走不提交其完整check；不创造与193合同无关的任意资本、借款、资产处置现金。候选完成静态/独立审阅后根才统一接线；原PG/Linux/live/员工/生产门槛和人工体验保持pending。

根注册记录：冻结脚本 `71152135cc82695572f57cd098096dfd4dd03cdae8212567b528c7a98c006763`，独立原合同短审未发现确定装置误配，根核有限来源/终局后，精确把该文件加入 `run.py` 镜像白名单及 `scenarios.py` 拼接。新增FINANCE_SCENARIOS位于已声明同轮前序之后，未修改fixture，注册时五项均未实际运行，不计通过。
