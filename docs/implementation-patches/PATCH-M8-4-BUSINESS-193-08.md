# PATCH-M8-4-BUSINESS-193-08：原维修首链及真实物料前置

日期：2026-10-01。按193项实际点击目标及已审阅维修来源，继续完成HK031/034/044/049/053/079六项首链；其余洗车、快捷、索赔、返修及现金更正独立保留待测。

候选作者精确范围仅新增`tests/browser_click/repair_business.py`、维护`docs/architect/tasks/repair-business-click.md`。原UI工位、客户车辆预约/改约、现场到店、转维修、报价、独立主管核价、显式客户授权、技师开工、真实库管领1250/退250/再领250千分量、施工/质检、承担、实际财务收款、客户接车逐原来源核对。只读取同次已通过客服HK099本店子来源、主档HK175及物资首链checkpoint有限明确ID；不得使用历史fresh、demo余额、SQL/API创造业务结果。到店负责原进厂区间，不造重复GateVisit。

根后续接线范围仅`tests/browser_click/run.py`、`fixture_server.py`新增外置随机technician登录及store1 UserStore、显式repair角色合同；不预置工位/预约/维修/授权/材料/现金。密码继续全角色脱敏。冻结审阅后才接原镜像白名单、注册/汇总、README和任务索引；作者在根已冻结报表验证期间只改本人两文件。

严格沿原Cookie/CSRF/version/request_id和岗位任务守卫。任务分给demo员工时，只允许主管原“岗位交接”选择真实同岗员工并携带原任务版本，不能借admin或数据库改责任人。金额整数分、数量整数千分之一，真实领料价值和明确合成人工事实分别核对，不用售价猜成本。原签署、现场及银行凭据均合成、structure-only，不冒充ClamAV或真实员工/实物/到账验收。

人工体验与文案保持human_pending，六项自动完成不等于完整193验收。失败保存原件并停止，发现生产缺陷另精确补丁，不改守卫求绿。
