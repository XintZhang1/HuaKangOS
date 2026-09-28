# PATCH-CP-00B-04：结果记录隔离及七个旧测试合同

归属 M0.2.B / R3-20260927。修复仅限外部验证器和外部测试，不修改生产 API、助手表单/提示词/排序规则或原文件解析安全测试。按用户连续实施授权，经独立审阅后执行；不等于 CP-00B 放行。

## 当前证据

新 C: strict `20260927T131721Z-08d5e63d84` 18/18 通过；完整 B `20260927T131802Z-08e49c6b4c` 已真实退出 1。22 个命令到达终态，前 21 个完整；累计 1089 passed。第二业务组共 161 节点：118 已触达但缺终态报告，记 incomplete；43 未执行，加后续 1810，共 1853 not_run。第二组事件含 110 个 call passed、7 个 call failed、另 1 个仅 setup，不将局部通过拼入完整成绩。前后源码、镜像、overlay、执行器、依赖、外部输入和 manifest 全部未变。

第二组原 `test_pure_parser_never_opens_paths_writes_files_calls_network_or_model` 临时将 `builtins.open` 和 `Path.open` 替换为拒绝函数，正确检查解析器无外部副作用。外部 `baseline_results.py` 在 pytest call 报告时也调用 `Path.open`，因此 INTERNALERROR；随后结果文件未能写出，runner 正确以 missing_report 停止。统一入口及本批子进程均已退出后才修补。

完整错误、分类和原件留在新 V：`runs/20260927T131802Z-08e49c6b4c/`、`review/CP-00B-04/`。PATCH-01 的 P1/P2/P3 六个正式命令 87/87 已通过，独立复核见 `review/CP-00B-03/patch-01-formal-review.json`，不据此宣称完整 B 通过。

## P1：只隔离执行器自己的证据 I/O

允许修改 `V/harness/baseline_results.py`，并新增 `V/tests/baseline/overlay/tests/test_m02_reporter_contract.py`；更新外部登记与 provenance。生产 `test_business_assistant_files.py` 原安全用例、解析器、`harness/isolation.py::dump` 及全局文件打开行为均禁止修改。

- 在插件导入时保存原始 `io.open`，仅用于该已验证 command 结果目录中的四个固定文件：`node-context.json`、`pytest-events.jsonl`、`pytest-collection.json`、`pytest-results.json`。首次绑定时要求 command_id 为单个合法名称，使用既有 `clean_path/inside` 拒绝重解析/越界，并核对结果目录恰为本次 `run/command-results/<command_id>`；现有环境验证不会代替这项核对。
- 不接受测试或产品传入的任意路径、文件名或模式；node-context 覆写、events 追加、终态报告禁止覆盖分别保持原语义。序列化结构、身份、节点生命周期、脱敏和逐事件及时写出不变。
- 不撤销或缩小原测试的 monkeypatch；产品的 `builtins.open`/`Path.open` 仍须实际拒绝。捕获的原始文件调用仍产生 Python open 审计事件，审计拒绝必须传播；四文件路径收口由插件自身验证负责，不宣称现有 runtime_guard 已提供通用 open 路径审计。原网络/数据库隔离不变。
- 纯合同实际执行四类证据写入，验证原打开函数被 patch 时证据仍完整、产品文件打开仍拒绝、重复终态报告不能覆盖，记录 I/O 失败必须抛出而不能伪造成功。新用例登记进入完整 B，原文件解析安全用例必须正式重跑。

## P2：三处文案断言迁移（两个角色节点）

仅改外部 `tests/test_business_assistant.py::test_prerequisite_facts_reach_both_the_model_and_the_card` 和 `tests/test_business_assistant_case_navigation.py::test_intent_get_case_shows_native_follow_and_related_phone_entry`，保留原函数名、角色参数、原件和 diff。

- 前序测试不再要求孤立词语“逐项”。当前 HEAD 所含的 `d694a82` 变更已明确核对真实原单、不重复询问已知事实、缺项放入卡片、依赖未产生时等待。对这些具体语义分别断言；保留真实 notes 精确相等，并核对工具返回 ID 对应的卡片与数据库持久化前序事实、pending 状态及零业务 invoke。
- 原单导航不再要求孤立词语“不能编造”。当前文案明确真实沟通事实、未来回访计划不等于已经联系、禁止生成假反馈；分别断言这些语义。空 proposals 独立断言，避免短路隐藏。保留全部原 actions、岗位和电话入口条件，并核对查询前后原单状态/版本/数据/客户和该原单事件数不变。
- 不回退正确生产文案，不仅删失败断言。此前因短路未执行的卡片/空 proposals 条件均需正式到达并通过。

## P3：三处补信息卡的合成网关合同

仅改外部 `tests/test_business_assistant.py` 的下列三个既有节点及其必要局部测试辅助；默认不改变其他测试共享 fake 行为：

1. `test_a_card_can_require_the_employee_to_fill_facts_before_it_can_be_confirmed`：让该用例的 fake `inspect_operation` 返回与当前真实网关一致的有限 body_schema，准确声明 name、values.note、values.extra 类型；保留原缺项 409、未提交、填写后唯一调用及实际字段落值断言。
2. `test_answers_only_use_the_keys_the_card_declared`：同样从 inspect 暴露真实形状 schema。未声明答案键必须 422，业务调用为 0、原卡未成功；随后只给合法键才成功并唯一调用，额外字段从未进入业务 body。不能恢复静默忽略注入字段的旧合同。
3. `test_answers_land_on_the_real_field_even_when_the_model_prefixes_the_key`：schema 放在 inspect 返回，而不是已经移除 body_schema 的 validate 返回。保留模型输入 `quote.name`，要求服务器返回 canonical key `name`，确认按卡片返回键提交，最终只进入原 API 的 body.name；不放宽生产未知键或缺项守卫。

`forms.body_schema`、`prepare_questions`、`apply_answers`、真实网关 inspect/validate 及 service 准备/确认函数均与固定 HEAD 一致，本补丁不修改它们。分类证据见 `triage-question-cards.json`。

## P4：95 张待确认卡夹具消除时钟偶然性

仅改外部 `test_business_assistant.py::test_every_pending_card_stays_visible_past_the_old_eighty_card_window` 的合成记录与断言，保留该原节点及 95 张数量，不改产品排序。

原夹具一次 flush 95 行，created_at 使用平台时钟默认值；当前产品在同时间戳时按 UUID 稳定排序，循环第 0 行不保证就是时间最早的唯一记录。纯时钟观测 95 次得到同一时间戳，证据见 `card-timestamp-observation.json`；此观测不是原业务验收。

显式给 95 行设置依序、互异的合成 created_at，保存各原 ID；要求返回 pending 恰为全部 95 个原 ID、无重复或遗漏、真正最早/最晚记录在正确位置，重复读取保持顺序。保留每张可操作卡真实 id/digest；不通过删最早卡断言或改生产排序求绿。

## 实施和复验

实施前保留修改文件原字节及 SHA；PATCH-04 独立审阅无阻塞后修改上述有限位置。新增原测试适配登记在 provenance，原件哈希不变；原 2124 节点完整保留。新增 reporter 合同数以实际收集为准，更新最低数及完整清单。

开发纯合同只用于发现实现错误；正式复验须新 strict 和完整 B，原失败/缺报告 run 不覆盖，不混合片段。此前迁移的硬链接/目录联接可用；符号链接权限仍未解决时不改原安全测试，仍不能宣称完整基线通过。

- [x] 独立审阅补丁及最终差异，没有生产范围扩张。
- [ ] reporter 纯合同与原文件解析安全用例实际通过；缺报告和 I/O 错误仍拒绝。
- [ ] 七个原失败节点保留并正式通过，等强业务含义到达断言。
- [ ] 新完整 inventory、执行结果、指纹及来源全量成立后再审 CP-00B。

实施记录：P1 的 19 项纯合同已全部通过；独立复核确认插件仍只写四类本轮证据，原解析器安全测试字节未改。P2/P3/P4 两文件共六个函数、七个原失败节点的修改已完成静态语义复核；共享夹具和原测试签名/角色参数保留，尚未作为业务通过成绩。

登记已保留 319 份原件，新增 reporter 模块后共 12 个新增文件、8 个合同测试模块、41 个 B 命令；预期 pytest 总数为 2523（原 2124 + 新 399）。登记首次因旧 adaptations 摘要不含四个 bootstrap 适配而停止，未改元数据；随后对 317 份本次未改 overlay 同时核对上一轮 C: 的记录哈希、外部输入哈希和保留镜像字节，全部一致。旧来源记录和差异保留，不把历史适配当本轮新修改。完整登记证据见 `review/CP-00B-04/registration-verification.json` 和 `historical-overlay-verification.json`。

上述为实施和开发检查记录；冻结后重新运行 strict 与完整 B。原解析器安全节点、七个失败节点及全部原基线未正式通过前，CP-00B 仍为 changes_requested。
