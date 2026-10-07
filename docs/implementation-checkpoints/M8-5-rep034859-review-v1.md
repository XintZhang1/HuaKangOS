# M8.5 九例真实模型复验审阅 v1

2026-10-07。M8.5 `in_progress`，M8.6 `todo`，CP-37 `not_ready`。本报告记录九个原代表的本轮结果，不替代完整 283 或同批重叠 101，也不继承上一轮裁定。

## 冻结与实际运行

基线源码 `0c856655350d8aa69fe08329712cdc4df811c269`，当时干净工作树；源码指纹 `7047703634fbd596410a298cb679242fcc2a1f29d1d7347e03edef1711a85fec`。本轮继续原九例 S03、V03、V05、V08、M03、M04、F05、F08、Y07 的 `--representative --thinking` 登记，原 283/101 定义、适配器、评分及业务确认合同保持。

受审源码门禁重绑与单独费用 ACK 后，以 post-strict `20261007T034422Z-dfb5364251` 为同五输入权威来源：实际 18 passed/18 collected/18 tests_run、零 skipped、零模型调用，八项标记及 commands_ok 全 true；run SHA `cc2ccc022120a8e635c9139a72bb6c70fffa60f341b60d754a0de4ba017b2a57`。依赖锁与 installed 保持，harness `83b2f1806c9dafb3f8ceead7264c63a16eeaf88390f1bf57c1773203dedfdc14`，外部输入 `f864cf2aeb1b550b6a179f0463e0d8378079b5796a10b03498149bfb3cf0f9f4`。

真实 `deepseek-flash` 运行 `20261007T034859Z-39fe694f84` 通过 V/run_validation.py 的 M8.5 representative 实际执行，自然 CLI0、299.797 秒、未超时、进程已排空。原/R4 结构 9/9；源码、镜像、overlay、依赖、harness、外部输入、manifest 快照、全部输入八项不变性均 true，commands_ok true。strict_reference 权威五指纹一致、drift 为空；run.json SHA `e7eccf947542d38c68d93f8063e06e13c155fa00215485188acc5a99318f316f`。runner 的 `milestone_complete=false`，结构结果不代表业务语义或 M8.5 完成。

## 独立逐例语义

| 案例 | 裁定 | 本轮实际结果或问题 |
|---|---|---|
| S03 | 可接受 | 原意向客户尚未确认下周来店；准确准备一张 follow pending 卡，保留员工本次沟通结果及 2026-10-08 下次联系日期，须本人点击后才记录。 |
| V03 | 普通失败 | 未确认实车到店时正确不备验收卡。但“没有原采购单则建计划”分支漏原必填 contracting_party；本轮 catalog.operating_party=null，不能自动带出。回答仍承诺所列资料足以准备，失败限于无原单建计划分支。 |
| V05 | 可接受 | 本次授权返回候选实际 12 台、均未定位，三个真实 sales-blocked VIN 后缀 001—003；不把候选当当前库存、不虚构 0013。未选车、无目的库位时等待，无额外主档卡。 |
| V08 | 普通失败 | “业务助手→资料整理”预览及“导出此表”入口真实存在，CSV 导出保留原表 columns/values，没有厂家表映射至整车导入固定列能力。实际发布指引 business.json 的 wf-vehicle-batch-import.exceptions[1] 误写“导出固定列”，回答沿用为“导出成固定列”；原导入严格按 kind 固定表头，原表导出不等于自动生成 manifest/ship/receive CSV。岗位、分批、试执行回滚与本人正式确认边界正确。 |
| M03 | 可接受 | 四张原领料 34/31/29/26 的真实单号、状态及 34 原 issue/reject 动作、本人库管待办准确。客户读取真实403；只读父33/30返回404，回答限定“如33、30”，客户关联未知，不默认选34。 |
| M04 | 可接受 | 来源未选，父单本轮未读取、版本与动作未知；准确区分历史v1/v2技师/服务顾问申请、库管原退料子单入库和v3/v4库管原维修明细退回。明确父单不可读或版本未核不准备；末句“能办的步骤”结合前文按本人授权查询后条件判断，不是给单号即获权。本轮没有已知被拒父单查询；root完整回答终审同意，不继承旧轮失败。 |
| F05 | 普通失败 | 原12个来源为10正额/2零额、计划办理日期及无卡边界正确。但列表没有 issuer 字段，仅未选定 source35 被探查且 issuer:null，其它11个来源未读；回答却泛化为待选来源无冻结经营主体并无条件补问销售方，须先选来源再读其快照。 |
| F08 | 可接受 | 原客户2/车辆订单5总额15880000分、实收3000000分、来源余款12880000分准确。报表GET真实业务规则403，回答以授权来源解释余款而不假称报表已读；财务原待办、凭据及零写入边界正确，不套维修月结/内部承担分支。 |
| Y07 | 可接受 | 全账号与全类别审计组合仅全局admin；实际 NativeReadRolePrecheckDenied 在原传输前发生，明确没有原GET或原可评审拒绝。非admin日志范围、maintenance=系统维护、账号级管理员升级路径正确，无StoreRole或助手升级卡。 |

A/B/C 各审 3 例且分别为 2 可接受/1 普通/0 关键，最终合计 **6 可接受 / 3 普通失败 / 0 关键失败**。九例各 467 张业务表指纹前后等值；仅 S03 一张卡且为 pending，零业务确认/执行请求。无本轮新增资金或库存事实。查询中的原403/404/422及输入修正保留，不能称所有工具调用无错误。

外部独审原件在 V/closeout-20261007：

- A `rep034859-semantic-A/review.json` SHA `432513d1ae38782ec61a26c2def22b13c11c21d9b79c8373f948fd1e0ac2426a`。
- B `rep034859-semantic-B/review.json` SHA `0127291d2f50a3c622e57e4cd9ae41794b7a9b92ca10f551c911f8cf348d809a`；M04 root 完整上下文确认另存 `adjudication-M04-root-confirmation.json`，SHA `c20184ae744bdd311b4faa810859b9184039e892a801cfde885a7c609a192704`。
- C `rep034859-semantic-C/review.json` SHA `a55c34fe1b96d2aada3b876600173dcb4d2f366e9b60afed321913286bb638de`。
- root 最终终态审计 SHA `81f384ada9dabcf1861e81072ce5edbc6c57306a78450e82229e7a10af593053`，已填实际 6/3/0；原件和 trace 不覆盖。

## 费用、有限候选与待复验

51 次新请求全结算 0.563868 元；累计 9646 次（9639 已结、七旧未知、零预留），已结算 229.858549 元，七旧未知 66.322432 元，保守占用 296.180981 元。预算 400 元/12000 次、单次 reserve 5.242880 元保持。自然排空后 root 只设 halted/halt_reason 暂停，账本 SHA `eda3f3e404258c53306d4ee7c6c43773b648be0a0706df3483d05c6833488c0f`；旧 attempt 内容、费用和未知占用不变。费用与停机数取 root 排空后审计，本次文档登记不读取共享可变账本。

按 [PATCH-M8-5-GUIDE-SOURCE-CHOICE-10](../implementation-patches/PATCH-M8-5-GUIDE-SOURCE-CHOICE-10.md)，生产有限修复仅由 root 在两个文件及三生成物实施：`docs/workflow-source/business.json` 补原采购建单真实经营主体、纠正资料整理只导出原表列；`app/business_assistant_prompt.py` 将销售方补问限定为选定来源本人已读且无冻结快照，并区分未读、列表省略、已读空值；通过原构建脚本同步三份发布生成物。不新增转换器、默认主体、自动导入，不改变原单位、API、岗位、版本守卫或确认合同。

PATCH10 已完成 C 独立有限静审，无静态阻塞；外部 `patch10-static-review-C/review.json` SHA `dac8d983fe6bdf5d8ccbbe960f26980d0d8b020f661f6bf36fd70d61477dbaf4`。prompt AST 回填原常量后全等；workflow 源与发布 JSON 仅上述两个 action 字段改变，三生成物反向还原全等，193 映射、111 个 ID、岗位和入口保持。root 原生成器check193/111、AST1/1及diff检查通过。指南 source SHA 保持原构建算法结果，其算法不计本次说明文案，不能据此宣称文案未改。候选尚待冻结、新同输入 strict、仅来源与 gate 注册重绑、post-strict、单独费用 ACK 及原九例真实复验。实际普通问题消失后才从零执行完整 283、逐例审阅并单列同批重叠 101；旧代表、旧完整批次和中断前缀不拼接。当前候选尚未执行新 strict/live；total_plan.md 未改。M8.5 仍 `in_progress`、CP-37 `not_ready`、M8.6 `todo`。
