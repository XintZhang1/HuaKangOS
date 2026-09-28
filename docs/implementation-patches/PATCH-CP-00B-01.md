# PATCH-CP-00B-01：完整基线发现的依赖、展示合同和生成物修正

计划：R3-20260927；归属：M0.2.B；当前状态：独立审阅通过，进入限定修正与复验，尚未验收。用户已授权 Codex 按全计划直接实施；本补丁只修复基线恢复遗漏、与当前已提交 UI 冲突的测试合同及既有生成物，不改变业务规则或 Runtime 架构，不放行 CP-00B。独立审阅为 `V/review/CP-00B/patch-01-independent-review.json`；P1/P2/P3 均未发现阻塞范围问题。

## 原始证据与停止点

- strict：`20260927T121534Z-9465484290`，18/18 通过。
- B：`20260927T121610Z-e5de8ccf21`；collect 2440 唯一节点；20 个命令已完成，真实执行节点 866 passed / 5 failed / 1 error。
- 发现必需的两个旧启动脚本未恢复后，终止本批进程树；首个业务 pytest 组只有部分事件，后续组未执行，均不能计完整通过。
- 终止前原始 `run.json` 字节另存 `run.before-operator-interruption.json`；`run.json` 仅补记 status=interrupted 和中止元数据，命令结果不改。实际终止说明为 `reports/operator-interruption.json`。运行进程已收尾，无本批残留。
- V=`E:/HuaKangOS-agent-validation/runtime-v1`；外部审阅见 `V/review/CP-00B/{node-failures-review,workflow-failure-review,r4-evaluation-failure-review,source-boundary-review}.json`。保留原断言、原件、diff 与旧失败，不覆盖为成功。

## P1：恢复两个只读历史测试依赖

目标：原 R4 评测继续检查启动参数及无外部查看器，不再因缺文件退出。

允许：从固定清理归档 `E:/HuaKangOS-cleanup-20260927-082922/removed` 原字节恢复 `测试业务工具层.cmd`、`仅测R4新工具.cmd` 到 V 的原件/overlay；登记来源、SHA256。仅在 `V/harness/baseline.py::_safe_relative` 增加这两个精确根文件例外；更新外部 provenance/manifest 和定向合同。

禁止：向仓库恢复这两个启动器；运行任何 CMD；开放任意根文件、任意 `.cmd` 或路径穿越；改 R4 原测试断言；恢复废止维护功能、模型联网或凭据读取。

异常路径：归档缺失或原字节/来源不可核对时停止此修正；不造替代脚本。其他根文件仍拒绝。

验收：两文件与归档 SHA256 一致；严格路径反例仍拒绝；原 10 项 R4 评测完整执行且通过；真实模型调用为 0。

## P2：迁移四处过时展示断言，保留业务语义

允许修改仅为三个外部 overlay 测试文件：

1. `scripts/check_ux.cjs`：`no open tasks never implies complete business, cash, or physical handover`。不再要求已移除的固定长免责声明；检查“暂无待办”不会把原业务状态改成完成、不会推断款项/实物/外部手续完成，保留原状态展示与无任务分支覆盖。
2. `scripts/check_workspaces.cjs`：合并入口用例以当前“查看接待”及稳定目的地识别，并验证同目的地只出现一张卡、三条工作流引用与原需求保留。转义用例覆盖当前实际展示的标题、按钮、需求及工作流标题；不要求不再展示的摘要必须出现，仍必须拒绝原始可执行标记。
3. `scripts/check_assistant_workboard.cjs`：补填入口以当前“补充信息”和稳定 `data-baw-card` 识别；验证点击只选择原卡，不发起确认/业务提交，依赖等待项不会凭空变成可确认卡。

禁止：修改生产 JS、Node adapter 或业务确认流程；删整项测试、skip/xfail、只移除失败断言求绿；回退已提交的简洁界面。

状态：旧失败保留 → 明确合同迁移 → 新指纹执行原完整 Node 四套回归。任一业务语义不成立则保留失败，不能归为文案差异。

验收：四套原 Node 节点完整，新增语义测试如有须登记实际数量；0 failed/error/skipped/xfail/xpass；原件哈希不变、每个适配 diff 和理由可追溯。

## P3：同步便携工作流手册

允许的唯一生产文件：`docs/全量工作流手册.html`。使用原 `scripts/build_workflow_guides.py`（不带 `--draft`）生成候选，先比较再写回。已定位六处为嵌入 `web/workflowactions.js` 的旧按钮文案，对应原脚本第 12、14、27、30、31、33 行。

禁止：改 builder、workflow 源、业务 JS、权限或状态机；手工改生成物内容绕过生成；放宽 `--check`；回写另外三份产物的未解释变化。

异常路径：其他产物有差异或超出六处文案时，保留候选并先定位/补充审阅，不直接覆盖。原数据、70 张嵌入图片、CSS、其他 JS 必须保持一致。

Windows 编码处理：原 builder 默认写入平台换行。保留原始候选及 SHA256 后，只允许把候选 CRLF 机械规范化回原文件的 LF；记录转换前后哈希，不改变其他字节。三份非目标产物规范化后必须与旧文件字节一致，仍不回写；目标产物规范化后的差异仍须仅为六处文案。

验收：候选由原 builder 生成；实际生产 diff 限六处文案；原 `--check` 在新安全镜像通过；其余三份生成物字节不变。

## 重新验证与结束条件

- 只有终止旧验证进程后才允许修改受检输入。当前 M0.2 仍为 in_progress，CP-00B 为 changes_requested；后续 milestone 不启动。
- 更新来源、适配 diff、准确节点清单和外部哈希；重新跑 strict M0.1，再跑完整 M0.2 phase B，五类指纹一致。
- 本次不将旧 run 的局部通过拼接为完整基线；所有 41 个登记命令在新 run 重新执行。新出现的失败继续分类处理。
- 成功标准仍为全部适用清单完成、全部必须条件通过及输入/依赖不漂移；不降低原门槛，不把本补丁完成当作 M0.2 或 CP-00B 完成。
