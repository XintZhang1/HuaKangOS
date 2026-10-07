# PATCH-M8-5-ANSWER-COMPLETENESS-14

2026-10-07；仅属 M8.5 的既定真实模型回归定点修复。M8.5 `in_progress`、M8.6 `todo`、CP-37 `not_ready`、M8.10 `done`，本补丁不放行验收。

## 已有证据与问题

冻结 HEAD `662b085`、source `897bf4b9` 的 37 个原失败代表 `20261007T074423Z-b32a03ad7d` 从零运行，结构及独立语义均 37/37；已登记的新增 gateway 原 API 节点 `20261007T073312Z` 为 1/1，post-rebind 同输入 strict `20261007T073232Z-611683be12` 为 18/18、零模型调用。代表结果不能替代原 283 或同批重叠 101。

随后同冻结候选从零全量 `20261007T080101Z-7eb0d1f095` 因 C07 的 `provider_call_failed` 自然 CLI1 退出，仅 47 例落盘，其中此前 46 例结构通过，C07 为执行器终态失败，余 236 例未运行。A/B/C三份终稿逐例审阅共43可接受／3普通／0关键，C07另记1技术失败；同批原101只有47例覆盖、54未运行。不能先写全量语义通过。A 的 F05 在来源尚未选定且只读了来源列表时承诺销售方抬头和税号有经营主体快照、员工无需补录；原来源详情 `issuer` 可为空。C 的普通问题涉及盘点申请与实盘阶段、以及纠正卡片说明丢掉员工原问题的完整答复。具体原话、case SHA 与分片修正以 [本轮审阅](../implementation-checkpoints/M8-5-full080101-review-v1.md) 和仓库外原件为准。

本次已完整返回的 46 例各自 467 张业务表前后等值、无人工确认；C07 技术失败原件单列，不把它计入结构通过。原终态预算审计保留原7笔未知和C07一笔 `reserved`；独立审阅后已在锁内仅把第10985次尝试的预留转为 `uncertain_occupied`，仍保持halt，安装回执为`full080101-terminal/ledger-conversion-installed.json` SHA `4be8b5ca47f8164b8e2fa1250105ded5bd015ddc7bc8bedcfd184ee1aa94f8a2`，新账本SHA `441b611af06905804504ac68e6b927a9a7289db0de6cbca3284b198aa5c3f3e6`。当前10985次尝试为10977已结、8未知、0预留；已结 `245.450981` 元，加原七未知 `66.322432` 元及该笔保守占额 `5.242880` 元，合计保守占 `317.016293` 元。400 元／12000 次与固定预留额不重置。新付费前须按原门禁、冻结、strict、来源重绑和独立账本 ACK 核实，不能拼接本次 47 例与后批。

## 精确允许范围

- `app/assistant_runtime_runner.py`：仅在已有纠正卡片数量／结果的再答复指令内要求重新完整回答员工原问题，保留本轮已核事实、本人下一步与需同事办理或等待的依赖。此前答复没有交付员工，不得让模型只说卡片数已纠正、其余照旧。实际卡片数量和结果仍取服务器记录；不新增卡、不扩文本正则或权限。
- `app/business_assistant_gateway.py`：仅对成功原 `GET /api/invoices/sources` 的既有 `invoice_source_counts.notice` 增加来源范围说明：列表不含销售方 `issuer`；选定来源后必须读取该来源详情，`issuer` 可能为空，确实为空时补问真实销售方全称与税号；不得在未选定来源时保证免补录。原 `data`、`route`、计数、原发票 API、权限和业务守卫保持。
- `docs/workflow-source/business.json`：仅改 `wf-material-stock-count.prerequisites`，把当前总括的“盘点时点、实盘依据和现场数量”按原 `manual` 拆成申请所需物资／实际库位／盘点安排与批准后现场观察、实盘、复核所需事实。创建申请不能统一前置现场实盘事实；真正库存调整仍依据实盘与原复核。`manual` 原动作、按物资全店盘点与按库位盘点两条原单族、数量整数千分之一及员工点击原确认的边界不改。
- 用 `scripts/build_workflow_guides.py` 同步原三生成物 `web/workflow-guides.json`、`web/workflow-handbook.html`、`docs/全量工作流手册.html`，不手修生成内容、不改 193/111 映射。
- 仅同步本补丁、`docs/implementation-checkpoints/M8-5-full080101-review-v1.md`、`implementation_plan.md` 的当前 M8.5 与 CP-37、`docs/architect/progress.md`、`docs/architect/tasks/m85-live-closeout.md`。旧审阅、旧总计划、其它源码与已登记外部输入不覆写。

## 异常路径与复验

纠正轮如前答不完整，仍须向员工独立交付可读的完整结果，已成功卡不重备、拒绝与未知结果不改成成功。发票来源详情拒绝、缺失或 `issuer=null` 时停在待核，不猜本店法定主体或税号；列表来源不能代表详情。盘点申请可先收集对象、范围等当阶段事实，未现场实盘不能说库存已调整；实盘、批准及复核不得互相替代。仓储通用提示和其它指引不叠加重复改写。

必要静态检查及独立有限审阅已完成，未发现静态阻塞；后续须冻结源码与输入，同输入隔离 strict、注册后的定向无网诊断和受影响原例真实模型复验，最后从零完成原 283／同批重叠 101 并逐例审阅。`provider_call_failed` 独立归类执行中断，不以局部通过掩盖；员工试用、人工验收和 M8.6 不提前签收。
