# PATCH-CP-00B-02：补齐非 Python 依赖与嵌套 Node 隔离

归属 M0.2.B / R3-20260927。只使用本项已有外部测试恢复和执行器修正范围，无新增生产文件、业务规则或架构改动。不能据此跳过 CP-00B 或将环境不满足的测试标为通过。

## 证据

第二轮 strict `20260927T124451Z-e96aba73fb` 通过；B `20260927T124521Z-dd25b2e338` 收集 2460 个唯一节点，合同测试期间只读依赖审查确认仍有缺失后主动中止。仅 collect 命令完成，151 个节点有通过事件但无整组最终报告，不能计为正式通过。原快照和 operator 中止记录保留，无本批进程残留。

有限审查覆盖 199 份代码和明确常量/固定列表依赖；外部报告为 `review/CP-00B/limited-static-dependency-review.json`、`nonpython-test-dependency-review.json`。不把动态临时文件或可选配置当作缺依赖。

## 精确恢复清单

从固定本地 Git `1f884fb0a6225679dcec652fa81fcccc63cadfc8` 取原字节，仅恢复到 V 的 original/overlay 并登记来源、git blob、SHA256 和消费者：

- `tests/fixtures/questionnaire_o57b_synthetic.json`
- `tests/js/dossier_grants.test.cjs`
- `tests/js/store_switch.test.cjs`
- `tests/js/master_completion.test.cjs`
- `tests/js/questionnaire_exports.test.cjs`
- `tests/js/time_display.test.cjs`
- `docs/试用脚本/总表.md`
- `docs/试用操作手册-XC.html`
- `docs/试用脚本/R01-系统管理.md`

禁止恢复其他无适用入口的 CJS、草稿 SQL、旧 app、真实配置或业务数据；不修改原断言，不执行历史启动器。恢复后原件总数为 319；原 310 份记录与适配元数据保留。实际恢复证据为 `review/CP-00B/dependency-restoration-20260927T125542Z-94eaa7/`。

## Node 子进程守卫

原 pytest 会启动这五份 CJS；时区用例还会启动三个本地 Node 子进程。不能因它们不是顶层四套 Node 脚本而漏掉离线保护。

允许修改外部 `harness/isolation.py`、`runtime_guard.py`、`node_offline_guard.cjs`、`run_validation.py`、既有 Node/隔离合同测试及 manifest：

1. 生成隔离环境时设置唯一精确的本地 guard `NODE_OPTIONS`，不继承外部 loader、NODE_PATH 或其他 Node 预载配置。
2. Python 审计遇到 Node 启动时，要求精确环境预载，或已有独立适配器的显式 `--require <同一 guard>`；丢守卫或改为其他 loader 必须拒绝。
3. 只有包含 `tests/test_time_display.py` 的登记命令允许 `node_execfile_scripts=['tests/js/time_display.test.cjs']`；合同须冻结并由 guard 核对 run、路径、哈希、当前 command 和精确 pytest 节点。
4. 仅该实际脚本 worker 可用固定 Node 可执行文件执行其 `-e` 时区片段，环境除三个固定 TZ 值外不得改变，guard 必须继承。其他可执行文件、shell、其他 child API/Worker 仍拒绝；孙进程不能继续派生。
5. 原测试、原业务 JS 和已有顶层适配器的明确守卫保持不变。新增纯合成合同必须实际证明预载、网络阻断、时区继承及异常路径，而不是只检查字符串。

验收：原件哈希/固定来源完整；全部原适用 pytest/Node 用例经过统一 runner；正常受限时区子进程通过，缺失或篡改守卫、错误身份及外部请求拒绝；不降低完整清单、失败、跳过或输入指纹门槛。

## NTFS 环境决策（已获批准，按 03 迁移）

只读检查确认固定验证根所在 E: 为 exFAT。除符号链接/junction 两节点外，原 `app/private_files.py::publish` 的真实原子发布也依赖硬链接；不能通过改产品逻辑、mock 掉存储或排除原安全断言规避。

用户已明确批准把后续隔离验证根迁到仓库外 C: NTFS，E: 原证据及归档保留。该批准对应整根迁移，替代此前仅针对两项链接测试的窄范围提议。具体路径、复制核验和新一轮验证要求见 PATCH-CP-00B-03。C: 硬链接和目录联接已实测成功，符号链接仍报 WinError 1314；不能因 NTFS 路径获准就声称全部系统条件满足，也不自动修改 Windows 权限或开发者模式。
