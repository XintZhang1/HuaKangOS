# PATCH-M8-1-FOLLOWUP-SOURCE-DRAIN-01

2026-10-03，M8.1 原生验证器修复。正式完整 80 场中 dependent-plan-followup-controls 的原一次员工重核后第二次 POST 仍 409。原日志显示终态 Run 的关联 Wake 在重核和第二次提交之间派发；原报告未保存第二次详细响应，不将该推断写成已证实的第二次拒绝原因。原版本守卫和解除二次确认是正确保护。

允许修改仅 `tests/browser_click/scenarios.py::Evidence.followup_click`。只在原 active Plan 的唯一 active Grant 的 revoke 首次真实 409 后，读取同事项相关的实际 Run、已到期 Wake、未来预约、完整授权、当前岗位/门店和同 owned worker 的推进证据，限时等待来源收尾，再保留原一次员工重核与原一次 POST；任一新失败或当前 Grant 已失败直接拒绝。暂停、恢复、开启及 paused Grant 的 revoke 保留原 NULL 调度合同。不停止 worker、不写业务、不调时钟、不放宽 CAS、不追加自动重试。

队列接管后绑定当前唯一已就绪的 idle worker、owner/spec/descriptor/ready 及真实心跳；没有队列时读取受已有 mutex 保护的 base state。拒绝旧 worker 快照回退。实际 GET/POST 的整数 expected_version 和第二次拒绝 detail 留在外部脱敏证据。

候选先在外部登记、保留逐次原件和差异，审阅后按原 old-lease→dependent 路径验证真实交接，并复验原 source 回滚和 goal 场景。未执行的结果不预写通过；整项仍 M8.1 in_progress。

首次组合 `fd4-20261003T110248Z-3e8f0c4e` 四场执行完整、2通过/2失败，CLI1/service0/forced=false，原件保留。old-lease 与 source 回滚通过；goal/dependent 在首次 revoke POST 前被新增验证器身份条件误拒绝。实际本人 owner1/admin、启用门店1，原 `tenancy.role_for_store` 对真实管理员不要求 UserStore，INNER JOIN 错误丢弃该合法身份。允许同函数内仅改为固定当前 Store 的 LEFT JOIN，记录实际 membership_user_id，严格接受原真实 admin 或原普通员工的本人门店关联；完整身份、岗位、门店及关联整行每次仍须不变。不新增关联、不借管理员身份、不改产品权限。候选保留逐版原件，独立审阅后在全新实例复验原四场。

第二轮原四场4/4、CLI0/service0/forced=false，精确scenarios50111baf已合入，生产bbe95959/脚本0c343d58稳定。原revoke首次200，所有protected_conflicts=[]，新增409后drain未动态触发，不能记该分支通过；原静态审阅和正常交接/控制实际结果分别记录。正式完整原合同及独立故障重复尚待终局。
