# CP-00B-v1：首轮完整基线中止，需修补

日期：2026-09-27；计划 R3-20260927；M0.2=in_progress；gate=changes_requested。此报告不是完整基线通过或后续里程碑放行。

## 实际执行

- 严格自检 `20260927T121534Z-9465484290`：18/18 passed。
- B run `20260927T121610Z-e5de8ccf21`：41 命令登记；完整收集 2440 个唯一 pytest 节点（2124 原节点 + 316 新增合同），0 收集错误/重复；169 模块无遗漏。严格自检与 B 五类指纹一致，独立审阅通过。
- 20 个命令完成：316 项新增合同、193 项目录检索、1 项生成检查、76 项 Node、286 项 Python 脚本，合计 866 passed / 5 failed / 1 error。收集不算执行通过。
- 首个业务 pytest 组已开始但未完成，只有 10 个 setup、9 个 call、9 个 teardown 的通过事件，不能计作该组通过；其余 20 个业务组未执行。
- 确认缺少必需测试依赖后主动终止本批进程树，统一入口实际退出码 1。PID 32496/41604/48512/22404 已结束，无本批残留进程。
- 原终止前快照按字节保存在 `run.before-operator-interruption.json`；`run.json` 只补记 operator 中止元数据和 status=interrupted，不改已完成命令结果。实际中止事实另见 `reports/operator-interruption.json`。

## 失败分类

| 失败 | 实际结果 | 分类与处理 |
|---|---|---|
| workflow `--check` | 1 failed | 便携手册嵌入的 6 处按钮文案过期；原 builder 生成后核对差异 |
| Node UX | 29 passed / 1 failed | 旧固定长免责声明断言，迁移为当前展示及真实状态语义 |
| Node workspaces | 21 passed / 2 failed | 旧按钮文案、要求已移除摘要出现；保持合并引用及实际展示字段转义验收 |
| Node workboard | 13 passed / 1 failed | 补填按钮改名；保持选择原卡及零业务提交验收 |
| R4 evaluation | 9 passed / 1 error | 恢复清单遗漏两个根 CMD，只恢复外部只读测试依赖，不改原断言 |

四处 Node 断言与原 HEAD `f735de2` 的简化 UI 变更可对应；不是靠删断言通过。具体范围及验收见 `docs/implementation-patches/PATCH-CP-00B-01.md`。

## 来源与安全边界

原 5 个废止维护功能排除项未扩大。308 个归档原件、11 个新增 overlay、Node 版本及可执行文件哈希均已登记；此轮漏掉的两个 CMD 明确记为恢复缺陷，不能声称依赖闭包完整。

557 个 app/web/migrations 文件在当前工作区、strict 镜像和 B 镜像逐字节一致。相对原 HEAD，生产变化只有已审阅 claim 判断块，块外字节一致。B 本轮尚未改生产文件。模型调用 0，未接入公司或用户预览数据。

外部证据根：`E:/HuaKangOS-agent-validation/runtime-v1`。实际 run 的 `run.json` 保存全部五类指纹、完整命令和逐节点报告；`review/CP-00B/` 保存登记、源码边界和失败分类的独立审阅。完整日志与 diff 不复制进仓库。

## 下一步

先独立审阅 PATCH-CP-00B-01，按有限范围修正、登记来源和新指纹，然后重新执行 strict 与完整 B。当前没有复用局部结果完成基线，没有将后续 milestone 置为 in_progress，没有发布或部署。

## 修补实施回填（尚未正式验收）

PATCH-CP-00B-01 已独立审阅通过并实施。P1 恢复两份原字节 CMD 至外部目录，合同模块保留原 59 项并追加 20 项，开发检查 79/79；P2 仅迁移三个 overlay 文件中的四处展示断言，Node 76 个原节点无删减，增加状态/引用/转义/零提交语义检查；P3 由原 builder 生成，唯一生产差异为便携手册 6 处文案，另外三份产物未改。

外部证据：`review/CP-00B/P1-validation.json`、`P2/adaptation-manifest.json`、`P3-candidate-20260927T123658Z-73917b/writeback-result.json`。新的完整 pytest 预期 2460 节点；来源、适配和哈希已重新登记。开发诊断不代替正式 strict+B，CP-00B 仍 changes_requested，最终实际结果另行追加。
