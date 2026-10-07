# M8.5 rep084731 实际审阅 v1

2026-10-07。M8.5 `in_progress`、M8.6 `todo`、CP-37 `not_ready`、M8.10 `done`。

## 本轮实际结果

冻结 HEAD `1d65082bbbec6f44d99256492933702b7b1c06ef`，source `bd2894384abca464e68e1628b065cfd6c7bdc82819f3a4151b293123d62cded5`。受审来源重绑和单独 ACK 后，同五输入 post-strict `20261007T084358Z-4c384cd52a` 实际 18/18、零模型调用。真实 Flash 四原例 `20261007T084731Z-90cf76704e` 自然 CLI0，131.718 秒，进程已排空；结构 4/4，独立语义 3 可接受、1 普通失败、0 关键失败、0 技术失败。原执行器 `passed` 仅说明结构阶段完成，`milestone_complete=false`，不能代替语义验收。

| 原例 | 终审 | 实际依据 | case SHA256 |
| --- | --- | --- | --- |
| S06 | acceptable | 正确解释原订单 5、客户 2、版本和实际收款／子单／逾期待办；未把查询当实际交接。 | `9a06352a2c4bee3f469fcd9406716ede1d930ac8702975b640a4156388fa6f69` |
| M06 | ordinary | 已读物资 2 库位账未启用，却承诺仅补库位、原因和日期即可准备库位盘点卡，漏原启用守卫。 | `29cdece14715d4273d01d44d75afae7e3d1b927ce437d5368eba78f23384a528` |
| F05 | acceptable | 未选来源先消歧，再查选定来源冻结主体；未保证买方必能自动带出。本页 12 来源、10 正额、2 零额正确。 | `4650fcbf6a67b7495500329c3a76f1c028bc786072ba01601b29bf1733e4360f` |
| C07 | acceptable | 续保提取、分派和回访分阶段说明；未把内部任务或人工联系当成实际续保完成。 | `b52b96b2a1b3734291bcf74361da6d9dccbe9007fc8f721dc57fcd4528af197e` |

四例均零卡片、零确认，每例 467 张业务表前后等值。源码、镜像、overlay、依赖、harness、外部输入、manifest 快照、inputs 八项不变性和 `commands_ok` 均 true。零写入不抵消 M06 的具体条件错误；本轮不启动完整 283。

14 次新增 POST 全结算 0.183081 元。累计 10999 次（10991 已结、原 8 未知、0 预留），已结 245.634062 元加保守未知占用 71.565312 元，共 317.199374 元；旧记录和费用保留。排空后 ROOT 仅将账本 `halted=true`、`halt_reason=representative_semantic_review_failed`，halt 后 SHA256 `1244980370ef7e352c5232ce86700e948053e6312c2312fbf95a7242ec737b43`。预算 400 元／12000 次及单次 reserve 5.242880 元保持。

## 定点修复与待验范围

[PATCH-M8-5-COUNT-ENROLLMENT-15](../implementation-patches/PATCH-M8-5-COUNT-ENROLLMENT-15.md) 已事前登记并由 ROOT 实施：只补 `wf-material-stock-count.prerequisites` 的原库位账启用前置及全店实盘路径区别，三原生成物同步；原生成器 build/check、193/111 和 `git diff --check` 已通过。A 独立有限静审无静态阻塞，新候选冻结、新 strict、同四例真实复验和从零完整 283／同批重叠 101 尚待执行。runner、gateway、prompt、原服务守卫及四例注册输入不因本补丁改变。

## 外部证据

外部根：`C:/Users/tiefu/.codex/HuaKangOS-agent-validation/runtime-v1/closeout-20261007/`。

- 本轮 `run.json`：SHA256 `20933598326aa549db999b8ce92ab0520e7bb201397309f1ccb86f51a1cefe6b`。
- post-strict `run.json`：SHA256 `3a10d97ae2927c7a762563e2e78b806e9026a8afe39372ad52d30cd5588c08ff`。
- `rep084731-terminal/audit.json`：SHA256 `5d471663aecaa64132b2947d06a7b02523d7ed239b5eb6490e7b176805ced075`，记录排空时核账；其中 halt 状态为随后安全 halt 之前的快照。
- `rep084731-terminal/semantic-aggregate.json`：SHA256 `2c22faa6c29f9d672565bb0e0f8901f5541a85d97956628c17c46b73a71d9826`。
- A `rep084731-semantic-A/review.json`：SHA256 `9759f9f848f60f7fc34d09c80214ee0dc38132c1184bd680b49dc5b0d044ee79`；C `rep084731-semantic-C/review.json`：SHA256 `e431d1ea5e8dd4b380a1afe6a3f356e15eca9788ad0db159eadd0c3222019c68`。

同五指纹中的 harness 为 `c1593983be5399179dd464bb2e08244cfd82696e3e6ad437c4eba07dd00cf36e`，external 为 `360b65d4866a5526852abc3828662102c96f0493fcf5c1e33e90fdb590c7ba65`；lock 与 installed 依赖保持原值。来源与本轮成绩不继承为 PATCH15 新候选结果，旧完整批次及中断原件继续保留。
