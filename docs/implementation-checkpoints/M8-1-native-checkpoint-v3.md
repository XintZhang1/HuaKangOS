# M8.1 原生浏览器与 Git 交付检查点 v3

2026-09-29。本记录追加 v1/v2 的实际验证证据，不覆盖历史失败，也不改写实施计划中的 `M8.1 in_progress`。业务助手尚未完成全业务族验收；不部署、不默认开启四个新功能开关，真实模型调用为 0。

## 1. 已交付的精确版本

已通过现有授权将 `feature/assistant-agent-runtime` 非强制快进至：

- `6003569551d8ac01ceb3f43fbdd12df4c17267d6`：在真实上游祖先上恢复上轮 Runtime、确认、页面和并发登录修复。
- `213e28beea31627783cfb4cd793d6e05258a8441`：补齐显式跟进调度、两步依赖、通知、原接待事实、批量失败即停和页面竞态；将隔离测试源码随 Git 版本化。
- `1c4531f43712f43e690e8fbabb47a73e9f977cd0`：原生浏览器测试改用 CSP 兼容的等待方式；不改生产代码或浏览器安全策略。

被测树 `33bc276a28c055d52ca19797b41ac2008f71c01e`，祖先为原 feature `a293a92ae76073a97dc75511d48683be9c0fe34d`。没有 force push、重置远端或合并 main。本检查点本身只增加文档，不改变被测生产或测试文件。

## 2. 原生浏览器完整实测

Actions run `36501807123`、job `109194140065` 导入并校验上述精确 Git 树后，在独立 Ubuntu / Python 3.13 / Node.js 22 / Playwright 1.57.0 / Chromium 环境执行：

```bash
python tests/assistant_offline/run_isolated.py \
  --source "$GITHUB_WORKSPACE" \
  --output "$RUNNER_TEMP/assistant-validation" \
  --browser-mode native
```

验证步骤退出码 **0**。`run-summary.json`：`complete=true`、`browser_transport=native`、`real_model_calls=0`、`release_accepted=false`。

| 层次 | 数量 | 结果 |
|---|---:|---|
| 后端集成与编排 | 67 | 全部通过；其中 53 项为真实应用/API/数据库集成，14 项为 worker 编排隔离用例 |
| 完整前端模块行为 | 42 | 全部通过 |
| 原生 Chromium 页面操作 | 12 | 全部通过 |
| 合计 | 121 | 不与本地桥接复跑累加为不同用例 |

迁移、新库合成初始化、Python / JavaScript 语法检查也全部退出 0。没有继承旧归档的测试成绩。

本次浏览器没有替换原生 fetch、Cookie 或 SSE，没有桥接页面传输，没有设置 bypass_csp，也没有加入 unsafe-eval。登录、发送、确认、通知、刷新、离页返回、切店、取消和移动端操作均在完整原页面执行；其中两步计划实际完成了“开启跟进 → 准备第一张卡 → 人工确认 → 准备第二张卡 → 通知查看 → 人工确认”，未发草稿保留。模型供应商响应仍为受控合成内容；这不是 DeepSeek 能力测试，也不代表生产 HTTPS、代理和所有浏览器的验收。

### 原始证据

- artifact `assistant-native-evidence-1c4531f`，ID `11005138230`，SHA-256 `d87a24b666780b03840284c29ca0cca1af440f2df173349b229c29af2ffc1284`。
- 生产源指纹 `b05424bd1668f2531be01fb5931c7bd1784bd3a3f0e6fd1492821fb306fe011c`。
- 测试指纹 `bc26acd6fb650a5486b43956f491c8d505b5073f0c81cef9f329a9dc145bd8dd`。
- artifact 中含 `source-and-suite.json`、`run-summary.json`、逐项日志和合成截图；无运行数据库、凭据或客户资料。Actions 保留 7 天；本地副本在 `/mnt/data/HuaKangOS-native-evidence-v3`，不能依赖临时目录永久存在，测试源码已在 Git。

### 流水线结果与 Git 推进分别记录

该 run 的**测试步骤成功**，但其最后自动 push 步骤失败，因此整个导入 workflow 结论仍是 failure。具体原因为内置 GITHUB_TOKEN 没有修改 workflow 文件的权限；没有扩展权限、读取额外密钥或重复盲推。

随后通过已授权 GitHub 连接器验证远端精确 commit/tree 和 feature 原 HEAD，再以 `force=false` 将 feature 推进至 `1c4531f`，并读回 ref 确认成功。故“测试通过”“自动 push 失败”“授权连接器最终交付成功”是三个独立事实，不能合并成旧导入 run 全绿。临时 `checkpoint/assistant-followup-213e28b` 是导入和故障证据分支，不是应切换使用的业务分支。

### 保留的前序失败

- `36500955850`：67 后端与 42 前端通过；原生页面测试被测试侧 `wait_for_function` 字符串求值触发 CSP 拒绝，未交付。改为 Python 侧限时轮询只读 DevTools 表达式，并显式检查原 CSP 与 native fetch；不改原应用安全策略。
- `36501692310`：增量 Git bundle 的 ref 为 HEAD，导入脚本错误请求分支 ref；导入阶段拒绝，未运行业务测试。修复导入器后才有本次完整验证。

## 3. 本轮实际证明的业务边界

后台事件分发和到期计划检查已真实接入 worker；有到期工作时连续处理、每轮让出，空闲或异常才退避。显式授权可在退出后继续准备，但不能自动确认业务。暂停、撤销、账号或门店停用、租约失效和重复唤醒都有指定场景证据，不据此推广为全部故障组合已验收。

准备卡片前后原业务写入为零，确认才执行原业务接口。批量每项独立事务；第二项失败或提交后响应丢失时停止后续项，已成功的第一项不回滚，未知的第二项不换 request_id 盲重放。发件箱在通知插入后、事件完成提交前注入失败，回滚后重投只有一条通知。

前端补齐 PlanView、跟进按钮、通知读取和同会话刷新。异步请求按用户/门店/会话/最新选择保护，不覆盖未发草稿、已填答案或确认后的新事实。生产默认开关仍关闭，旧人工模块保留。

## 4. 已复现、尚未修复的下一阻断：销售事实与原 v4 流程不一致

这不是 121 项中的通过用例。额外诊断使用真实登录和同一类仓库外合成库：

1. 原 `POST /api/vehicle-catalog/entry` 创建合成品牌、车系、车型，取得实际 model_id / version。
2. 原 `POST /api/sales-quotes/orders` 传真实合成 customer_id、车型版本、整数分金额、未来有效日期和报价条款。
3. 原接口返回 201、`kind=order`、`flow_version=4`。
4. 当前 `domain_registry().supports_fact(key, 'case', kind='order', flow_version=4)` 对 `sales.active_quote_approved`、`sales.active_quote_consented`、`sales.delivery_recorded` 均返回 false。

源码核对：`sales_quote_service.CURRENT_ORDER_VERSION=4`，原 `is_quoted` 支持 3/4；`assistant_runtime_domains/sales_order.py` 与注册声明却只登记 3。故新报价订单不能被上述计划条件正确识别。

不能只扩大版本声明：还存在待验证的证据投影差异。原 `flow_engine` 的 deliver 写 `handover_file`；当前销售适配器检查 `delivered_at` / `delivery_recorded_at` / `delivery_receipt_id`。这部分目前是静态差异，尚无完整原生交付闭环证据，不登记为已修复。客户同意还须核对实际报价、配车、SalesQuoteConsent 及签回文件关系；岗位脱敏不能解释成事实为假。

诊断脚本 `/mnt/data/HuaKangOS-validation-v2/diagnose_sales_version.py`，最终日志 `evidence/sales-version-diagnostic-v2.log`；首次因合成种子没有车型导致的夹具失败单独保留，未计入产品缺陷或通过数。下一次应在已有隔离入口中新建正式销售族用例，不照搬临时环境为正式验收。

## 5. 下一执行点与未完成范围

先在实施计划中登记精确销售事实补丁范围，建立原生报价批准、客户签回、换报价/换车和交付的正反例，再修复上述适用性和证据投影。优先读取 `assistant_runtime_domains/sales_order.py`、`assistant_runtime_domains/__init__.py`、`sales_quote_service.py`、`sales_quote_models.py`、`flow_engine.py`、`flow_documents.py` 与原权限/附件合同。不改原销售规则，不以 task done、出库、结清、状态文字或模型回复冒充实际交付。

然后继续原 M8.1/M8.2 的跨业务族故障与回归矩阵。原 101/283 模型场景、全部 193 项业务需求、PostgreSQL、Windows、指定 MCP 客户端、生产部署配置和真实员工试用仍分别待验。本次保留 `M8.1 in_progress`，不将接口或注册数量等同功能完成。
