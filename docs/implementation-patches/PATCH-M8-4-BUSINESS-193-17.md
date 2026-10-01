# PATCH-M8-4-BUSINESS-193-17：维修物资报表八项候选

2026-10-01，当前M8.1，冻结范围 `docs/architect/tasks/report-followon-scope.md` SHA256 `11d8af2e07c43e5fc073333f99365d0998fb92d2d52ed894d7dc1742439b692a`。作者仅新增 `tests/browser_click/report_followon_business.py`、`docs/architect/tasks/report-followon-click.md`，生产/原目录/fixture/runner/注册/计划只读，不导入app或启动应用/浏览器。

精确8完整候选HK146/147/148/149/150/151/153/155，真实同轮五前序采购→主档→客服→物资→首维修有限来源。原日期口径、维修授权报价/领退料、采购原收退、移库库位/在途配对、全范围图/明细/分页/CSV及原单钻取逐一核对；不同实际日期不借来源重写。所有读取/下载本人员原UI，DB SELECT-only；按原export独立精确适配，不让旧report helper将专用149/153路径误判为visit。原唯一导出审计照核，同型SQLite静态风险若实际发生保留错误，由根另登记修复，不改后端/降断言求绿。

HK152没有今日启用前真实期初，保持明确partial，不改时钟/库或改其他原单来造历史，不计第九项。HK155配对明细真实非空而图净额0按原提示核，不能造非零。库存/库位当前数量版本现场重读，旧收退/成本/来源逐行保护，金额分/数量千分之一及原单位保持，模型/工单缺依据明确缺失，不猜填现车型。six criteria人工体验仍pending，193全量/外部/生产不由此替代。作者冻结及根独立短审后才注册新镜像实测，无预写成绩。

703行脚本冻结SHA256 `b1c9a226e5f7abe9c44dc839f826021a52e53877bda02eb0827b0121be886385`，作者AST/SELECT-only与独立代理只读短审通过。原八项合同、专用三类CSV实际path/query/唯一审计、动态表与日期金额数量守恒、五同轮父来源及152partial均核对，无确定静态误配。finance-followon03退出后根将本文件与系统两项添加原白名单/单导入拼接，当前32注册；实际点击待新镜像，不提前记通过。
