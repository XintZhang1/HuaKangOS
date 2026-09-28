# CP-00A-v2 审阅与 Codex 接手记录

日期：2026-09-27。结论：v2 不通过；由 Codex 在 M0.2.A 内继续修补，满足检查后进入 B。用户已改为直接连续实施，执行协议见实施计划 R3。

v2 的 18 / 36 / 39 / 17 个执行成功结果真实存在，保留原报告和 run；它们不能证明执行器的失败判定与输入绑定已完整满足 PATCH-CP-00A-01。

| 问题 | 证据与实际影响 | 本次处理范围 |
|---|---|---|
| 报告字段缺失仍通过 | verdict 对缺 command_id/run_id/source/exit 的报告放行；脚本 nodes 可缺失或含失败；collect 未落实独立报告和下限 | 外部 verdict、reporters、自检和回归；逐节点结果与汇总交叉验证 |
| XPASS 可通过 | pytest reporter 已记录 wasxfail 信息，但判定只看 passed outcome | 明确拒绝 skip/xfail/xpass，不改原业务断言 |
| 配置入口与冻结合同未闭合 | validate_environment 无条件拒绝 ALLOW=true/无配置；env 合同可脱离 run 冻结记录，node context 未绑定当前 run | 仅外部 isolation 与注册协议；精确活跃节点三态，固定路径/hash/身份 |
| 文案同类回归 | “确认卡已生成，请核对是否正确。”及“已准备好1张确认卡，请核对是否正确。”在旧 HEAD 为真，v2 为假；ASCII 成对引号查找起点错误 | 仅 claimed_actions 纯文本 helper，不改提示词、SSE、对话提交或权限 |
| 严格引用与输入漂移 | manifest 写入 strict run_id 后被刻意排除绑定；applicability、恢复清单和依赖声明没有完整前后指纹 | 静态 manifest，runner 自动查最近成功同仓库 strict；引用只写当前 run；补齐所有声明输入 |

产品配置三态不需新增生产改动：test 环境无显式配置、synthetic=false 均被产品拒绝；synthetic=true 加固定假 key 可就绪；空 key 为 enabled=true、ready=false。不得为适应执行器去放宽产品配置。

关于编码：当前 ASCII 转义句式表无 U+FFFD，且已逐字核对。审阅在同一 E 盘目录用显式 UTF-8 写入/读回中文成功，字节一致；不能认定 exFAT 自动替换非 ASCII 字符。此前损坏的具体写入链路根因未定位，保留 ASCII 转义与解码校验即可，不迁移磁盘或重建环境。

外部审阅证据目录：`E:/HuaKangOS-agent-validation/runtime-v1/review/CP-00A-v2/`，含 verdict/config/claim 纯函数探针及 UTF-8 回读结果。它们是定位证据，正式验收仍须使用修补后冻结输入依次运行 M0.1 strict 和 M0.2 phase A。真实模型调用未用于本基线。

R3 接手：已获全计划连续实施及本地 DeepSeek 调用授权；后者只在指定 live gate 用全新合成数据执行。此文不含凭据，也不授权生产部署。v3 的实际运行、指纹、进程和验收结果另行追加，未执行的检查不预写成功。
