# PATCH-CP-00B-08：R4 首个完整基线的失败归因（测试合同对齐 + 两处产品修复）

2026-09-28，集中测试阶段。合并 `origin/main`（0927_bugfix）后的第一次完整 M0.2.B 基线
（run `20260928T064850Z-ed840e406e`，41 条命令、44 项登记中 3 项为 phase A/其它批次的重复登记）
结果为 **2741 passed / 39 failed / 1 skipped**，7 条命令不完整。逐条归因后：
38 项属**过时测试合同或测试替身**（本补丁对齐），2 项属**产品缺陷**（本补丁修复）。
原始失败、日志与全量指纹全部保留在 V 的 run 目录中。

## 1. 产品修复

### P1 工具目录在缺少配置时不再崩溃（`app/assistant_runtime_registry.py`）

`registry_for_config(config)` 直接读 `config.tool_profile`；历史调用点（与两条回归用例）
传 `config=None` 时抛 `AttributeError`。M3.1 之前只有一个目录，缺省即旧目录：

```python
profile = getattr(config, 'tool_profile', 'legacy')
```

缺省永不等于 `business_v1`，因此不会误开业务工具面；崩溃路径被消除。

### P2 提交标识只由服务端生成一次（`app/business_assistant_service.py`）

`resolve_preparation` 原判断 `generate_request_id = 'request_id' in properties and 'request_id' not in body`，
即**模型自带 `request_id` 时服务端会照抄**。这违反 M2.1"请求号只生成一次"的合同，也让
`SubmissionSnapshot`（只接受 `POST|PUT /api/...` 且要求 body 的 request_id 与冻结值一致）
在确认时不成立。现改为只按 schema 判定：

```python
generate_request_id = isinstance(body, dict) and 'request_id' in properties
```

模型/员工自带的那个值在临时校验副本里被替换成零值探测键，落库前从 payload 丢弃，
准备落库时再由 `build_proposal` 生成真正的提交标识；确认阶段（纯校验）保持不换键。

## 2. 过时测试合同 / 测试替身（外部 V，原件与差异全部留档）

| 文件 | 现象 | 归属与对齐 |
|---|---|---|
| `tests/test_business_assistant_migration.py` | 其它用例调用共享 helper 时报 `'tuple' object has no attribute 'intersection'` | 本补丁自身引入的 helper 签名缺陷：`indexes(..., later=())` 未把默认 tuple 转 set |
| `tests/test_business_assistant.py` | 28 项确认类失败（409 提交标识/冻结内容不一致、uncertain） | 替身不完整：假网关 `inspect` 缺 `body_schema`（服务端据此判定生成提交标识）、`validate` 会覆盖已存在的提交标识、缺 `refusal_metadata`/`permission_hint`、操作号是 `create_record` 之类的别名（冻结合同只接受 `POST|PUT /api/...`）、`_inspect_question_card_schema` 未暴露 request_id |
| `tests/test_business_assistant_gateway.py` | `SimpleNamespace has no attribute 'scope'`；`request_id` 缺字段错误抢先；`model-chosen-key` 断言 | 假 request 补 `scope={}`；case/create 信封补服务端提交标识；把"校验层换键"改为断言 M2.1 分层（校验层保留、准备层丢弃） |
| `tests/test_business_assistant_scope.py` | 动作名用例 422 字段错；中间单据用例缺 request_id；403 提示为空 | 动作用例保留"拒绝原因只能是字段事实、不能是动作名"的断言；信封补 request_id；`permission_hint` 改为按 M2.2 用真实 `record_refusal` 记录断言，并断言无记录时无提示 |
| `tests/test_business_assistant_stream.py` | `last_request` 多一个键 | M5.1 起 `last_request` 含 `run_id`（Runtime 关闭时为 null） |
| `tests/test_business_assistant_case_navigation.py` | 403 的 `error_category` 不是 `permission` | M2.2：无真实拒绝记录时报 `refused`，且不得凭文案改称权限不足；同时断言无 `hint` |
| `scripts/check_assistant_r3.py` | 2 项错误（合成行缺提交标识）＋4 项 cards=0 | 冻结的 h51i/f24s 合成行按其自身列集合写；脚本化工具调用补 `type=function`（M3.1 起必须是真实 provider 形状） |
| `tests/test_member_fee_correction_reconciliation.py`、`test_partial_correction_reconciliation.py`、`test_repair_package_reconciliation.py` | 新批次 `definition_version==21` 断言失败 | 0927_bugfix 新增定义 22（`private_file_objects`），旧批次仍冻结在 18/19/20；新批次断言改用 `CURRENT_DEFINITION_VERSION` |
| `tests/test_business_assistant.py`（R3 同类） | `全部工具都要执行` 断言信息不足 | 断言消息附带服务端 issue 列表，便于定位（不改判定） |

每处改动都在 `archive/baseline-restoration.json` 的 `adaptations` 中登记
`original_sha256 / overlay_sha256 / diff / diff_sha256 / patch / reason`，
差异另存 `tests/baseline/<file>.cp00b08.diff`；原始文件保持不动。

## 3. 复验（同一源码指纹 `46c3960e85c2e98fc41cdb9c0366341c5b60987cb10d1f88cbc0d6589bea4ff6`）

| 命令 | 基线 | 复验 |
|---|---|---|
| `b05-business-02` | 143 passed / 18 failed | **161 passed / 0 failed**（`20260928T090316Z-f2eeac2f7b`） |
| `b05-business-03` | 98 / 16 | **114 / 0**（`20260928T083034Z-2b3ba7a4bc`） |
| `b04-check_assistant_r3` | 4 failed + 2 error | 见 §4 复验记录 |
| `b05-business-09/10/13` | 2/2/1 failed | 见 §4 复验记录 |
| `b05-business-11` | 1 skipped（符号链接环境） | 保留为环境缺口，不改为通过 |

## 4. 复验记录（诊断运行）

- `b05-business-02`：`20260928T090316Z-f2eeac2f7b` diagnostic_passed（161 项）。
- `b05-business-03`：`20260928T083034Z-2b3ba7a4bc` passed（114 项）。
- `b04-check_assistant_r3` 与 `b05-business-09/10/13`：见对应诊断运行输出，结论与失败项在
  集中测试报告中追加。

## 5. 边界

- 全程只读合成库；未访问公司库、原预览库、真实附件或凭据；未调用真实模型。
- 未放宽任何业务断言：所有改动都保留原判定意图，只是把替身/断言对齐到当前已评审合同。
- `tests/test_private_files.py::test_symlink_file_and_root_rejected` 仍因当前环境无法创建
  文件符号链接而 skip，属环境缺口，未改为通过。
