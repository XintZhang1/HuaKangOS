# PATCH-M8-4-BUSINESS-193-12：洗车、快捷维修及客户直接报销

2026-10-01，业主全部193项实际点击持续授权，按已冻结`docs/architect/tasks/repair-followon-scope.md`（SHA256 `e3f3f2dc3d3c2092b05e324781dff83080d163c5cb49f2b891f6369c6c97c985`）实施四项候选HK032/080/033/042。

作者只新增`tests/browser_click/repair_followon_business.py`并维护`docs/architect/tasks/repair-followon-click.md`。生产、fixture、注册、共享脚本及计划只读；不导入app、启动实例。沿同次已通过首维修有限report_sources及原主档/物资来源，通过原UI实际新建洗车和快捷工位、真实QuickPreset、预约/现场到店/转换、授权施工/质检/承担/到账/接车；当前车辆、工位、库存及原版本均重新读取，不能使用旧终点行相等约束或制造Arrival/GateVisit。

HK042以首维修当前真实客户承担、原到账及完整未被更正/报销占用额度为来源，customer_direct原评核、外部结果、另一主管批准及实际客户支付分别留事实，客户直接收款不得生成门店Cash。HK081当前首单无误记事实，不能冲正正确款求覆盖，留待真实明确合成误记前置。所有合成外部/实物/银行凭据分开上传，保持structure-only与人工条件边界。每步明确岗位、CAS、幂等、原API守卫，原Task转交只走主管原UI；保护旧业务、现金、库存、审计和证据。

冻结源码/指纹、原合同审查后根再镜像注册并联合实际运行。实际阻断或生产缺口另报根精确补丁，不隐藏失败、放宽类别/金额/状态或通过API创造正业务；候选与单纯导航不计193完整验收。

根登记：独立原合同短审及根有限前序核对后，脚本冻结 `0bfa02d61b3e38499a5b9c95f9ede320d23d859991cd6105a0e8c983b27ded00`，根将本文件加入 `run.py` 脚本镜像白名单与 `scenarios.py` 场景拼接。两个场景位于首维修、物资及主档之后，报销位于本轮洗车/快捷真实接车之后；未修改fixture，注册时仍无本候选业务通过成绩。
