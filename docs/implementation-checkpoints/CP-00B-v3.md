# CP-00B-v3：C: 完整基线终态与下一轮修补

结论：**changes_requested，M0.2 仍为 in_progress**。这次完整基线已跑完，不能放行 CP-00B。依用户 R3 连续实施授权，在当前项内修补、复验；不开始 M0.3 或 Runtime。

## 实际执行

- 验证根：`C:/Users/tiefu/.codex/HuaKangOS-agent-validation/runtime-v1`（下称 V）；E: 历史根和归档未改。
- HEAD：`f735de2d74f5eb37f13addc1353e6a8e435a01c4`；当前工作树作为候选，不以相同 HEAD 代替指纹。
- strict：`20260927T140154Z-bbad0660d9`，18/18，退出 0。
- 完整 B：`20260927T140257Z-053b24940f`，统一入口退出 **1**，已自然结束。原 exec session 38349 已返回终态，未留运行中的验证进程；没有中途修改冻结输入。
- 41 条登记命令全部产生可归属结果，34 条通过、7 条失败。完整 collect 为 2523 个唯一 pytest 节点＝原 2124＋新增 399，原节点集合完整保留。
- pytest：2486 passed / 36 failed / 1 skipped；其余目录、生成物、Node、脚本检查共 556 passed。合计 **3042 passed / 36 failed / 1 skipped**。
- inventory_complete 与 coverage_complete 均为 true；无 missing/extra/duplicate/not_run。successful、phase_complete、milestone_complete 均为 false。
- PATCH-04 的 19 个 reporter 合同、7 个原失败节点及原安全解析器节点，共 27 个目标已在本轮正式通过。此前 missing_report 问题已关闭，不能因这 27 项通过而忽略本轮其它失败。
- 真实模型调用 0，未接触生产/原预览数据库、附件或密钥。

## 输入与独立审阅

本轮前后 source/mirror/overlay/harness/external_inputs/manifest/dependencies 全部一致。strict 引用的五项指纹全部匹配，无 drift：

| 输入 | SHA-256 |
| --- | --- |
| source | `342929ffbdb521dde5e4514aea3e1de4420cc6285128a0de5c9f32ef1cb5e95e` |
| harness | `aa528e83b40ba867407dd5fa6bc5d0101d26318fb76950036d3e357fef6b7514` |
| external inputs | `1618f5a1d9c51edcf775487b25a4f7812926db89b459143c05d15101270f71cd` |
| dependency lock | `3910945cf6063ebe984b40cc22667657bd83476dcca1024ef4884b10f01dc930` |
| installed dependencies | `0c9c6fd3198a051b655f51ee26babe35e42d64dc77b3c0f48bac14ccc9c218a5` |

独立终态审阅逐项核对了 41 份报告的身份、退出码、合同哈希与实际节点，并复核当前 613 个源码/镜像、29 个 harness 输入、654 个外部输入、331 个 overlay/镜像、319 个原件、manifest、Node 和 Python 依赖。差异与审计问题均为空。

完整证据：`V/runs/20260927T140257Z-053b24940f/`；独立审阅：`V/review/CP-00B-05/full-run-terminal-review.json`，SHA-256 `c2c4930acf332c4879b3b7e5c5c11afadd50b2a69132fcd18c1b198c288c73b0`。原 v1/v2 和旧 run 保留。

## 失败分类及处置

| 数量 | 实际失败 | 处置边界 |
| --- | --- | --- |
| 4 | 流程帮助的管理员说明、无匹配提示、分类和字段投影旧断言 | 按当前发布目录/相关性/权限合同更新原四节点，保持显式字段边界 |
| 4 | 操作目录分页、岗位/人工评审提示、依赖链、前序事实旧断言 | 按当前 R4 实际合同更新原四节点，保留本人权限、真实 ID/版本和人工点击 |
| 1 | 原主体迁移回环的新库未登记 synthetic marker | 保留原 l248→k137→l248、16 表及外键断言，有限标记原子进程合成目标 |
| 2 | CLI 安全负例的新库和 local/production 环境未登记 | 必须执行到原产品拒绝且 DB 未创建；守卫错误不得算成功 |
| 3 | 本地预览 marker 的规范只读 SQLite URI 被当普通路径拒绝 | 在原合成库权限范围内校验真实 uri=True、mode=ro 和一次审计许可 |
| 2 | 中断预览 prepare 的旧库只读 URI/fresh 库标记未登记 | 保留旧目录原字节；产品创建 fresh 目录后才补 synthetic sidecar |
| 1 | 完整备份恢复读取主合成库的规范只读 URI 被拒绝 | 与上述 URI 共用边界，不新增业务路径名单或改产品备份规则 |
| 1 | browser 存储隔离辅助测试的新库在 run/tmp，且 conftest 重写 DB basename | 外部 bootstrap 只创建命令 fixtures 内的新库标记，保留 helper 返回目标及原零外部写入断言 |
| 18 | 车辆运输三组完整性用例的参数化 SQL 含加号/引号，被登记器字符白名单拦住 | 使用冻结命令及 reporter 活跃节点身份；完整参数只作为 JSON 数据，原损坏 SQL 和完整性断言不改 |

以上共 36 个失败：8 个旧合同、28 个隔离/执行适配问题。被守卫提前拦住的产品断言尚未执行，不能由此宣称相关产品行为已经通过；修补后若出现新错误，仍须重新分类。

另 1 个 skipped 为原 `test_symlink_file_and_root_rejected`。此前原生 Windows 探测报 WinError 1314，本轮该节点确实跳过了文件/目录符号链接拒绝检查。等待用户处理系统权限；不得改为 hardlink/junction、删除、降为可忽略或计作通过。

## 后续范围

具体修补见 `docs/implementation-patches/PATCH-CP-00B-05.md`。候选和原始差异先在 `V/review/CP-00B-05/` 独立审阅，按限定 hunk 合并，记录全部来源/输入指纹，再执行开发合同、新 strict、正式诊断和完整 B。诊断结果永远不能替代完整 B。

本报告只允许在当前里程碑内继续已授权修补。CP-00B 未放行，后续项未启动，生产发布未授权。

## PATCH-05 应用与登记（正式复验之前）

18 个外部候选已独立审阅并按最终合并指纹应用。唯一跨候选冲突是新 URI 纯测试缺 reporter 记录，已补齐独立合成身份，未回退注册守卫或删除原断言。最终 merge-manifest SHA 为 `abe78c0ac0ee18ab5916dc3cd1201b96ca34f7d3e99db2ee747ba998685e4e2f`；独立审阅 SHA 为 `a8755f78341a6c5eaed32f7dac9534f5042fad7b8125a0fff8aac45430d8094a`。

开发登记收集 `20260927T155226Z-60d062e9` 退出 0，五个新纯模块分别 46/41/124/9/24，共 244 节点。该步骤只有 collection，测试执行为 0，未导入 app、打开数据库、发起网络或子进程；输入未变。它只提供登记数量，不是验收通过。

登记器核对原 319 文件、历史 2124 原节点、原测试声明和 41 命令定义后，写入实际 manifest/provenance。b01 预期 643 节点，全量预期 2767 节点；正式 runner 仍须核对本轮完整原节点集合。新 manifest SHA `8523a8196091d51c0be1331a3ae058082dd25ceb4b2b8e2547b62da869cdc4fc`，provenance SHA `13c57ad2df2d8794a0b9f187a12a343d5be580f708f783f6dfe7695ccb9cf1ed`。

证据：`V/review/CP-00B-05/candidate-application.json`、`combined-independent-review.json`、`registration-verification.json` 与 `development-collection/20260927T155226Z-60d062e9/collection.json`。下一步新 strict 后，正式诊断覆盖 b01、完整运输组、其余原失败/跳过节点和 PATCH-04 相关回归；诊断永远不放行 B。原完整失败记录保留，CP-00B 状态仍为 changes_requested。

## PATCH-05 第一轮正式诊断（2026-09-28 收尾）

新 strict `20260927T155446Z-0be208b45d` 实际 18/18，通过且退出 0。诊断 `20260927T155523Z-0df4da21e5` 已真实结束、退出 1，未遗留验证进程；源码、镜像、harness、外部输入、manifest 与依赖前后均未变，strict 五项指纹一致。完整 collect 已收集 2767 节点，随后 b01 收集 643 节点。

b01 为 374 个完整 passed、1 个 teardown 错误、268 个级联 setup 错误，0 skipped。首个 fixture-registration 节点的 call 已通过，但 monkeypatch 恢复约 161 KB 的 HUAKANGOS_COMMAND_CONTRACT 时触发 Windows 32767 字符限制，后续环境身份未完整恢复。不能把级联错误归为 269 个独立产品缺陷。b01 原 continue_after_failure=false 生效，其余 7 个所选业务组均未执行，原 36 失败和符号链接节点仍未完成本补丁复验。

诊断保持 diagnostic_failed、phase_complete=false、milestone_complete=false，没有生成完整 baseline 或覆盖 latest-run。修复仍限 PATCH-05：精确清单保留在磁盘冻结合同，环境只携带数量/摘要及实际权限交集，并验证长度边界。修复后必须新 strict 和完整定向复验，随后再跑完整 B；本次失败证据不删除。

实际进程退出证据：`V/review/CP-00B-05/first-diagnostic-process-exit.json`。Windows 首次启动辅助脚本的 os.execv 提前返回，因此 root 另持有实际 runner PID 44500 的系统句柄至结束取得 exit=1；没有把启动脚本的 0 当作 runner 成功。后续辅助脚本改为同步等待原统一 runner。

## 环境长度修复应用（第二轮正式复验之前）

两文件候选 manifest `3e11a63c62b298c0ad4c771ee73a71283b677e0861f7e877949bbbe19b4cbe23` 已独立审阅并应用；审阅 SHA `0f340a08ae0fb6952475cde4c566e4615da6f960d4670b7273e3335c80e95218`。runner 的诊断权限合同改用清单数量与规范摘要，完整选择仍在原磁盘合同/command；fake-config/profile 仍取精确交集，full 原路径不变。实际序列化值达到 32767 UTF-16 单元时拒绝，禁止截断。

新增大清单/环境恢复和 ASCII/非 BMP 边界共 5 个回归。开发收集 `20260927T160811Z-f8674b63` 退出 0，五模块 46/41/129/9/24，共 249；未执行测试或产品/数据库/网络操作。登记仅把 b01 minimum 643→648，更新现有诊断 addition、历史差异和维护辅助程序对应数量；17 addition、13 新模块、41 命令其它字段均不变。

登记后 manifest SHA `c72e1a875d35b210bf8a02cf437930ea1110d7ef731e943c4f1afb3cdb44f4e6`，provenance SHA `86bdd64b3c69faeac6d86dd96de44e38949db9e95ef614479a646b017060ffcb`。应用、登记证据见 `V/review/CP-00B-05/contract-size-application.json` 与 `contract-size-registration-verification.json`。后续正式验证须使用这一组新输入，不继承旧诊断的 374 通过片段。
