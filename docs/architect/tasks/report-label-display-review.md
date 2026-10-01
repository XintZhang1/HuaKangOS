# 任务：报表轴标签与理赔现金说明独立静态复审

**任务 id 与负责人**：`report-label-display-review`；`audited_reads`。2026-10-02，根登记 `PATCH-M8-1-REPORT-LABEL-DISPLAY-01` 后分派独立只读审阅；只写本任务页，不编辑生产或测试。

**目标与交付结果**：核对已观察 HK160 现金图标签重叠及理赔现金说明含内部模型名的有限显示修复。结论：两文件实际差异精确限于轴标签挑选与一条中文 caption；统计定义、查询、金额与系列、原单明细/CSV没有变更。这个结论只完成静态范围复审，不表示新页面已视觉通过。

**架构依据与决定**：沿原统计/图/表/CSV同范围合同及 `docs/文案标准.md`，保留未知/来源不足与不重复确认收入、现金的限制。HK160 标签问题由根/C的本轮实际 PNG 审阅报告提供，本子任务没有把未亲自看过的该图写成自己的实图观察。仅修显示，不修改历史定义21、现金定义7；当前月结定义版本源码本来为22，也原样保留。

**代码快照与影响范围**：外部 before 根为 `C:/Users/tiefu/.codex/HuaKangOS-agent-validation/runtime-v1/browser-click/launches/report-label-before-20261002/`；登记文件 `.../launches/report-label-edit-20261002.json` SHA256 `73bc27fec5ae2c84ba3b26a3878cdc56679998b02caa3dbaa06f46616f99ccad`。登记恰2条且各 before/after 与实际原件、当前文件相同：

| 文件 | before SHA256 | 当前 SHA256 |
| --- | --- | --- |
| web/app.js | f06b590bbd23b4ab4e87798f8084738a729185610d8edc4970557ef7a630cdba | 0afce29bdd1833071a24617c19b75d1e503d19869cd32b00376ff01356ea0fb7 |
| app/claims_analytics.py | b3f81740244ab3fdaeedd4107ca8d7fc72a27ecfd1e309f17c14b0828d4a08ca | 4e26aecca03f8186c7d90bce7050101d78c74738137f3af29900b524678254ac |

**已完成与当前位置**：两文件均完成正向及反向完整字节核对，替换旧/新串各恰出现一次；把当前新串换回原串后，整个文件逐字节等于外部 before，包括所有其他函数、行尾、终末换行与中文。不是仅比较 hunk 或忽略空白的差异检查。

`web/app.js:331` 唯一替换原 tickCount/tickIndices 构造；`xLine` 原表达式仍完全相同。新规则从左到右按每个原标签的真实 x 位置挑选：bar 仍为 `left+(i+.5)*plotW/labels.length`，line 仍为 `xLine(i)`；只有距上一已显示 label 中心至少145的项才进入 Set。previousLabelX=-Infinity 使首项正常入选；不强行追加末项，避免尾部再次靠近。该条件直接保证已选中心距>=145，消除了原按数量/圆整索引忽略实际绘图区间距的机制。

145来自本次横排中文轴标签的保守显示估计：原 font-size=15，原显示最长9字符（超9则8字符+省略号），约135像素，加10像素间隔。它是显示估计，不是字体测量，也不宣称所有字体、缩放、边缘裁切或设备已通过。原单标签、所选标签完整 title、所有系列完整 values、bar/line/circle逐值循环与原几何/数值 title、颜色/图例/SVG标题全部原字节不变；未选项仅少一个横轴 text，其原数据仍在各 bar/circle完整 title及同范围明细/CSV中。未引入canvas、DOM测量、数据采样、系列删减、字体/尺寸缩放或新测试。

`app/claims_analytics.py:96` 唯一字符串改为：

> 来自已有现金流水及关联收付款记录，只作专项明细；第三方直接付客户不在此表，不能再次加入总现金或维修收入。

旧首句的 `CashEntry/PaymentLink` 换成员工可理解的业务来源，后续专项明细、外部直接付客户排除、不重复计现金/维修收入边界原样。其用途仅为 `chart(...caption)` 的参数，存入 chart payload 的 caption，再被原页面 `E(c.caption)` 与 SVG title 显示；不是查询参数、统计定义、去重键、金额计算或判断条件。Python原AST反向替换唯一新 caption 常量后与整个旧AST完全相等。

作为历史定义与查询未改的附加核对，当前 `app/flow_analytics.py`、`app/reconciliation_service.py`、`app/inventory_report_common.py`、`app/cash_basis.py` 全部与 full13 冻结源码逐字节相同。这是代码保持证据，不继承13的业务或视觉成绩：

- flow_analytics SHA `dde62d794a4ea194ea8dd93988362d2a5c1ef2d3df2962be78b52ac8527745bc`。
- reconciliation_service SHA `4be23e53df58dc656544ae514f6c4c930c549c055508aaf00b507a55e49b92f5`。
- inventory_report_common SHA `5eb10d5e698799fe88484a8750bd06636869c81648c9c983c0ba9e00ccf6ba65`。

**下一步**：等待根冻结并运行新的完整53 full14，再按分派读取该唯一新 evidence 根的 complete/passed父场景真实PNG，观察横排间距、说明可读性及完整原对象。原13部分审阅保留；不复制旧评分或 accepted，人工六rubric未实际观察项仍pending/null。

**验证与实际阻塞**：本任务只做文件原字节、登记指纹与Python AST读取；没有导入app、执行测试/浏览器/SQL、读取DB/密码或修改原证据。根报告 Node syntax check=0，本子任务未重复执行。无静态范围阻断；新页面视觉、三宽/手机、键盘与恢复、最终53/193原门槛仍待真实证据，全部不由本报告记passed。
