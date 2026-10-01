# PATCH-M8-4-BUSINESS-193-14：保险资金及原周期续保候选

2026-10-01，按业主193项实际点击持续授权及冻结 `docs/architect/tasks/insurance-next-scope.md`（SHA256 `8bdbd821e758d5062df3d918e03e22e3512d485992a776095e9ffffc72ca797c`）新增七项候选HK013/014/077/113/114/115/116。

作者只新增 `tests/browser_click/insurance_business.py` 并维护 `docs/architect/tasks/insurance-business-click.md`。生产、fixture、共享runner/注册及计划只读，不启动业务实例。用同次已通过本店主档Insurer与客服本地CustomerVehicle有限来源，核真实同客户/VIN；不把HK099 partial提升为通过。两版保险分别核价/客户授权、三次外部提交/结果、保费代收/原款代缴及独立佣金实际到账，再沿真实保期边界提取/去重、分派/本人回访、建立真正新保单与renewed守卫，最后原撤保失效与代缴追回/客户退款/佣金原款返还分别核事实。只输入声明的合成短期险和合成外部凭据。

各资金、原件、Task/员工、CAS及原幂等合同保留；全部旧业务行、另一店、来源与原字节受保护。正业务只由原UI提交，不直接API/SQL设置结果；结果不明停止，不改时钟/DB保期求边界，不自动重放。脚本冻结、独立审阅后由根精确扩镜像白名单与注册，首次真实运行前无成绩。原保险file_category静态缺口由根另登记生产窄补丁，作者不能放宽原后端文件校验。未覆盖销售退车、采购退回、真实保险/银行/签字/ClamAV/PG/Linux/员工和生产条件。

根接线：保险最终源码SHA256 `ab7e7e472b17f36be774fb8936a269b018c82bfb3474282b7e470715a052cd05`、文档 `dcb0f85ecc03841508b2ae7674ffff7ad4c4e1b5aa4800114bbd1c2bd36a713f`，独立短审及最终增量复核完成；原SQLite布尔证据按实际0核对，API布尔仍严格False。完整28实例结束后根扩 `run.py` 单文件白名单、`scenarios.py` 单场景导入/拼接，当前注册29场景；生产字段窄修独立登记INSURANCE-PROOF-FIELD-01。首次实际保险结果尚待执行，不预写通过。

首次实际 `business-insurance-20261001-01` 同轮selected4/4、退出0，33完整自动check，其中保险七项首次完整通过，保险实际120.05秒；其他26是本次采购/主档/客服真实来源，不与完整28的84拼成联合结果。源 `978552f07fe422a93a8dea5b715765166ffce7cfda46f4a6f6f30d8ef7e499cf`、脚本 `a4e18d82a6863662950d3d775019d8433666dda83be43f94ff701ec0178eb308`、镜像稳定，0合成/0真实模型。人工体验和193全量仍pending/false，保险原件类别修复按实际原UI七项复验；证据全外置，实例已结束。
