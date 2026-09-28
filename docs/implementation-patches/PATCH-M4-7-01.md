# PATCH-M4-7-01：事务分发与授权读取的必要接线

日期：2026-09-28。计划R4-20260928 / M4.7。依据用户持续授权登记，不另询问；本项尚在实施，不表示验收通过。

M4.7原允许outbox dispatcher及源事务信号hooks。源码核对发现原queue入队自行commit，不能与WakeEvent分发状态原子保存；现principal只有登录或已领取Run，不能为分发前查询伪造登录或先建模型Run；权限全局事务也不能假改write_store来写各店信号。最小补充如下。

- `app/assistant_runtime_queue.py`：固定signal批量resolve/persist/final-validate拆分，同Session/Engine短期一次性凭据，持久部分只flush不commit；按所有Session→所有Plan→Grant/Run固定顺序锁。保留旧单signal入口为兼容包装，原manual/user/领取/预算/重试不改。
- `app/assistant_runtime_principal.py`：新增仅服务器调用的有效Grant查询身份，无Run、lease、fence或登录凭据。原本人/门店/岗位/access_version、原会话、当前Plan/goal与Grant版本均从数据库核实，每次固定原GET前后复验；不能用于任何Run写入、模型循环、计划保存、确认或伪造登录。用于先读事实再决定入队，后台实际执行仍须原claim租约。
- 新增 `app/assistant_runtime_access_signals.py`：只接受同事务真实UserAccessReceipt或指定AuditLog新实体，核对来源、目标与实际修改；自行推导有关门店。仅以固定Core语句写WakeEvent，不接任意table/SQL/store列表，不修改db.info或原业务权限。原user_access_service/main只插入同事务hook，仍由原owner提交。

这些只读探测不代表条件满足。信号只指向真实原对象；M4.8继续负责条件指纹、无变化零模型与到期调度。M4.7不得在业务事务里发GET/模型、创建默认Grant或提前启用worker。

异常：来源不一致或过期凭据拒绝；跨店信号不能读取别的私人计划；任一入队失败回滚该事件的全部入队及dispatched，事件单独留pending并退避。权限变化使旧身份失效，不能借新探测身份更新旧会话权限快照。所有静态核对、源码审阅和最终指纹随本项记录；运行测试仍后移，原验收不降标准。
