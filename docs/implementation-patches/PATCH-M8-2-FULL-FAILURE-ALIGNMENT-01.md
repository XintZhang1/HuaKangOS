# PATCH-M8-2-FULL-FAILURE-ALIGNMENT-01

2026-10-04。当前唯一实施项仍为 M8.2。Linux v21 CI 37188128764 / HEAD c269f5e962657d468747c932ab4331d1164da203 已自然终局 failure，101/101 命令、4151 passed / 87 failed / 10 原平台不适用；完整清单及输入一致，无超时或进程残留。Windows 同一轮仍在自然运行，其结果不由 Linux 推定。

本文件先在全新的仓库外候选目录登记。没有本地 run_validation.py 验证进程；仍在运行的 GitHub job 使用它自己已下载且冻结的源码及 source-only asset 609410676。当前 Git 工作树、V 注册测试/执行器/manifest 和该 asset 均保持原字节。只在本候选独立 before/candidate 副本实现并静审，不导入 app、不运行测试、不合入当前输入，不取消或改变 Windows job。Windows 自然终局且原件独审后，才核对差异、合入候选、登记新来源并启动全新隔离复验。这些候选从未被本轮 CI 读取，不把两轮证据混合。

## 实际失败与精确修订范围

- domain：Linux runtime-domain-01..08 的 50 个原 call failure，对应逐项诊断 bb7fbab9f9f42bd26d8638d0bbc31a1a74acbc381579903363385eb46ddbae00 中 test_source_provenance 列出的 31 个原 overlay Python 文件。仅修改这些原失败函数及其必要本文件夹具。13 个 UI 源码结构/语义断言沿当前已授权界面与显式 feature/版本/迟到保护；21 个 registry 断言核对精确类型 fallback、原 kind/version 与唯一 operation/fact owner；16 个事实/旧未接入夹具按已存在原 GET 完整结构修正。保留全部原节点、正负例目的、原单/权限/实际流水/完整性/未知三值守卫。不得以空 tuple 恢复重复 owner，不得用审批、时间或模型文字代替业务事实。
- node：诊断 c70c7cd8729c2ce8d3363b152d6ae9b9e6be51d034549d191a9a9ff7411c4fe0 的 18 原失败和 baseline 内 store_switch 一项。范围仅 overlay/scripts/check_workspaces.cjs、overlay/tests/frontend/test_m6_1.cjs、test_m6_3.cjs、test_m6_4.cjs、test_m6_6.cjs、test_m6_7.cjs、test_m6_8.cjs、overlay/tests/js/store_switch.test.cjs。补当前真实接口所需 VM global / Reader.releaseLock / boolean 成功返回 / 真实异步 loader与刷新等待；更新已批准文案、样式和功能开关断言。保真权限矩阵、源码函数边界、错误不是空结果、no retry/no followup、切店完整重读和不泄露授权等原语义。尽量保原 test 声明行和名称；如确需变动必须报告并按真实新收集登记，不能伪造旧行号结果。
- identity：仅 V/harness/fixture_profiles.py 及原 test_m02_fixture_profiles_contract.py。Linux CI 的实际已绑定物理解释器为 .venv/bin/python3.11，原 helper 硬编码 bin/python 导致五个业务子进程在 app 执行前拒绝。按当前 run 的真实 python_runtime 绑定绝对 executable、venv 和必要 SHA，保非链接、orig_argv、精确 tail、cwd及 Windows redirector 的现有证明；不增加宽泛解释器名称白名单、不改 CI Python 版本、不放宽任意子进程。夹具同步显式合成身份，正反例仍调用真实守卫。
- baseline 并发：仅 overlay/tests/test_dossier_grant_security.py、test_user_access.py 四个原失败函数及必要本文件调度辅助。同步点改在两个独立连接首次 BEGIN IMMEDIATE 之前；不在已持 writer 锁后等待另一 writer。普通账号竞争仍 200/409；互停管理员按首笔真实提交后会话已撤销的当前原权限合同为 200/401，核对唯一活跃管理员、赢家调用者/输家目标、版本与唯一回执。档案撤销用真实先提交撤销再让读取取得锁的序列，核对 403、无字节、无新增 DossierAccess，保后续拒绝；不倒置原事务合法次序。监听器及请求正常排空。
- baseline 存储：仅 overlay/tests/test_test_storage_isolation.py 原 subprocess 节点。由 reporter 的 active_node 精确核对当前参数节点后提供原 request.node.nodeid，不绕过 DB marker/当前源。parent 确认同一已标记合成库且零借出连接后 dispose 闲置池，使 child 可独立接管文件；不是强制关闭使用中连接。保 sentinel 全字节、真实原上传/下载及 blob 断言。Windows 文件池风险为静态生命周期判断，不冒称已有动态错误。
- baseline feedback：仅 overlay/tests/test_multistore.py 的原 removed-feedback 节点、test_workflow.py 的原权限节点。已获业主授权的独立 ops feedback 入口保留。显式无 OPS_STATE_DB 时具体店 GET/合法 POST 503、缺 body 422；获授权集团汇总 GET/POST 409，普通未获汇总岗位 403；旧 maintenance 404 与原业务权限断言保留。不初始化运维库、不调用模型/外部邮件。
- original unittest：仅 V/tests/m82-closeout/original-unittest/tests/test_runtime_integration.py 的五个原失败及本文件必要夹具。按已登记 PATCH-M8-1-LOGIN-TRANSACTION-01 核单次认证：父独立 writer 先 flush，原 HTTP 登录尝试 BEGIN IMMEDIATE，父 commit 后核成功/错密/停用三例的一次密码验证、会话/audit/attempt/Cookie。原 bounded 节点持真实 writer，仅该 login 夹具连接 busy_timeout=0，核真实 SQLITE_BUSY、一次 reservation/零密码验证、503、无新 session/audit/cookie；清理后 dispose，生产 timeout不改、不称未知提交测试。registry 核目前54个已实现身份及唯一映射，包括四补齐领域及 rework_derivative_results，不能仅为数字求绿恢复重复owner。
- 进度输出：仅 V/run_validation.py 的 run_commands 在原执行前后向 stderr flush 输出安全 command_id、序号、结果和耗时。stdout 最终 JSON、原 argv/env、timeout、selection、清单、终局和来源守卫保持；不打印凭据、配置或原业务数据。

## 合入与验证

本候选不修改生产 Python/JS、架构业务规则、total_plan、功能开关、依赖、原 API 或任何真实数据。root 管主文档、六个 baseline/original 文件与来源合入；day 管31个 Python domain/UI；reg 管8个 Node；mobile 优先监测并独审 Windows 原件，在监测间隔中可只改独占的 identity/进度候选副本。每组保 before/candidate/diff、节点变化说明与静态审阅，交叉核对后才能更新当前输入。

合入时只更新实际变化的 restoration/adaptations/overlay/supplemental SHA，以及必要真实收集的精确数组和胶囊清单；其余源输入逐项保持，失败证据不改。先同新指纹 M0.1 strict，按原 M0.2.B diagnostic 与已登记 M6/M7 入口做受影响检查；这些结果不提升其它里程碑状态、不替代全量，不新造 M8.2 诊断执行器。最后新 main 同候选 Windows/Linux M8.2 全101命令。新增或后置断言实际失败继续按原合同修复，不删节点/放宽语义/继承历史成绩。员工试用之外的后续全部技术门槛仍待顺序完成。

后续实施记录：Windows已自然终局并完成独审；上述候选与WINDOWS-FIXTURE-LIFETIME范围交叉审阅后合入。2026-10-04 v22候选已实际合入外部注册来源：129个已交叉静审的测试/夹具/执行器源文件，加两份来源登记，共131输入变化、670/801保持原字节；原319归档、全部命令/节点清单保留，9条Linux preview不适用规则仅重绑overlay SHA。合入前实际检查无本地验证进程，v21两平台已自然终局。新draft SHA `8be5fe1a17554916fa34d62c5ae4ff48209ad12b86fd280914d17b65b6b61f23`；下一步统一strict和原定向入口，尚未执行新候选动态检查，不记通过。

定向复验补修：M6.8真实run `20261004T120953Z-12bffdc9cc` 的原 `test_switches_are_read_only_from_the_server` 在re.compile阶段失败，新增regex漏转义闭括号，尚未到业务断言。仅在同文件40行补一个反斜杠；6个原节点和其余整文件字节/AST逆向一致，原GET、禁止POST/run/followup及开关守卫不变。静态扫描本轮31候选共52个regex字面量（6个新增/修改），只有此一语法错误；原失败、1字符diff和双审均外置保存。待全部同期验证自然结束后已核无进程再合入，新strict与M6.8实际复验，不重复无关M7或M02并冒称同一次全量。

本地定向终局：M02原657+27节点全通过；25个原M7入口202节点全通过；正则补修后新strict18、M6.8完整149 Node/61 Python及原syntax/生成物均通过。各自明确run与五指纹独立保存，不混成同一次全量；原unittest登录5修订仍按原M82完整入口验收。新source-only asset609828442/SHA129115b39864e387a02b3158151b0fb7f82d38cdff7c3141c681a7076c75c382已冻结，双平台完整结果待实际终局。
