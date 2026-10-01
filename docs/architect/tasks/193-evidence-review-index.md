# 193 项证据与体验审阅索引设计

2026-10-01，M8.1 同一项；只新增本设计页。未导入 app、未运行应用/测试/浏览器、未读数据库或凭据，未生成执行结果索引。以下针对 **未来同一次完整全 53 成功执行** 的证据整理，不表示该执行已发生或 193 项已验收。

## 输入与门槛

静态只解析当前源码：注册为 53 个唯一三元场景（9 基础、4 帮助/页面/表单、40 原业务），镜像白名单 45 文件；catalog 为十模块、193 项，每项一个唯一 acceptance check。family 数或场景数不能代替逐项体验。

索引输入只接收一个仓库外 run 根，读取该根 `scripts/` 的 catalog/rubric/注册源码与 `evidence/`；不拿后来修改的工作树覆盖该轮合同，也不搜索多个 run 找更绿结果。建议只输出外部 `evidence/manual-review/193-review-index-v1.json`，不改原报告、checkpoint、actions、network、observations 或 catalog。

**预览阶段**：同实例 `--review-after-tests` 已由场景进程退出 0 后进入等待，browser-click-report complete/passed、full_registered_suite_complete 均 true；53 个 expected/actual/all_registered 精确集合相同、无重复/skip，每场 passed 且非空动作。原 193/111/70/9 UI 覆盖计数正确。此时 run-summary/provider 仍可能未终局，只能 index.phase=preview/complete=false，不能写最终通过。用于在 HTTP 仍存活时开展独立 Chrome 审阅。

**最终阶段**：原 stop-requested 正常收尾、CLI exit 0；run-summary complete/passed/full_registered_suite_complete=true/scope=full_registered，scenario_exit_code=0；provider 最终存在、real_model_calls=0、blocked_external_attempts=0；与原自动报告和预览指纹一致。provenance.snapshot_stable=true、changed_paths 空、source_before/source/source_after 与 script_before/script/script_after 相等，script_files 中每份镜像和数据合同 SHA 均匹配。相同 HEAD 不能替代此门槛。若任何条件缺失或 selected/不完整，拒绝 final 索引或标 pending，不拼历史；仍可以保留失败诊断。

逐业务场景 checkpoint 必须 scenario 对应、complete/passed=true，且同轮父依赖完整；source_contract_sha256 对应该轮 catalog，候选哈希（有此字段时）匹配该轮 scripts/provenance.script_files。早期少数 checkpoint 没有 candidate_sha256 时，必须用实际注册函数→镜像文件→provenance.script_files 绑定，标明该字段缺失，不能虚造。检查点里的 origin/source_root/evidence_root/mirror 如存在必须归本轮，不允许有限 ID 指向另一轮。

## 最小 JSON（结构示意，不是结果）

下面只示范一个原条目的字段，实际必须枚举全部 193。null、空数组和 pending 故意保留；不能把示例当真实自动、人工或日期成绩。

```json
{
  "schema": 1,
  "phase": "preview",
  "run": {
    "id": null,
    "root": null,
    "source_sha256": null,
    "script_sha256": null,
    "catalog_sha256": null,
    "rubric_sha256": null,
    "registered_expected": 53,
    "same_run_only": true,
    "automatic_final_gate": "pending",
    "provider_final_gate": "pending"
  },
  "artifacts": {},
  "requirements": [
    {
      "id": "HK-001",
      "module": "整车销售模块",
      "title": "展厅接待",
      "check_id": "HK-001-create",
      "automatic": {
        "status": "pending",
        "scenario": null,
        "checkpoint_ref": null,
        "source_file": null,
        "candidate_sha256": null
      },
      "native_action_spans": [],
      "png_refs": [],
      "assertion_refs": [],
      "partial_observation_refs": [],
      "conditions": [],
      "screenshot_review": {
        "status": "pending",
        "reviewer": null,
        "criteria": {},
        "notes": null
      },
      "chrome_review_click": {
        "status": "pending",
        "same_instance": null,
        "actor_store": null,
        "actions_ref": null,
        "png_refs": []
      },
      "supplements": [],
      "business_accepted": false
    }
  ],
  "counts": {
    "catalog_items": 193,
    "indexed_items": 0,
    "automatic_passed": 0,
    "screenshot_reviewed": 0,
    "native_review_clicked": 0,
    "accepted": 0
  },
  "complete": false,
  "full193_business_acceptance": false
}
```

`artifacts` 以安全相对路径为键，保存文件 SHA256、bytes/type；字段 `*_ref` 只放 `{file, json_pointer}` 或 `{file, sha256}`，PNG 放逐件 `{file, sha256, label, association}`。根路径只记录本轮外部路径。多条动作段使用 `{file, first_index, last_index, basis, shared_setup, review_status}`，真实 action.index 为 1 起；未知边界为 null，不截出虚假的独占动作数。大 DB facts/CSV/附件元数据不复制进索引，使用有限 JSON pointer；metadata 本来不完整必须标 missing，不能另读库补结果。

## 按当前真实形状建索引

1. **从合同建 193 行**：catalog.requirements 按原顺序取 id/module/group/title/check_id、ui_action、db_facts、roles、negative_or_edge_checks、suggested_followup_checks、unverified_conditions。HK001–007 原 check 后缀为 create/assign/intent/reassign/history/reminder，不能统一猜 `-business`。标题和 ID 逐字核对 requirements_manifest 的来源映射；目录静态 not_tested 不改。
2. **从唯一当前结果匹配**：以 browser report 中本轮 40 个注册 business 场景的 requirements[].acceptance_checks[].check_id 建一对一映射，未知/串项/重复检查立即阻断。不把 partial_requirements、导航 checkpoint.items 或 observation.label 当 acceptance check。对照 business-acceptance-report.requirements[].automatic_status/checks；自动 passed 必须场景 passed 且目录必需 check 全 passed，不用 diagnostic_checks_passed 替代。所有项仍先 business_accepted=false。
3. **动作范围**：普通 checkpoint 的 evidence_action_start 保存动作数 S，evidence_action_end 保存 E，转换成 actions.index 的闭区间 `[S+1,E]`，确认 index 连续、0≤S≤E≤len(actions)。requirements_click 的 first_action/last_action 已是 1 起闭区间，且属于只读层。售前 sales_business 只存 end；reports-complete-source start/passed 没有逐项 start/end，不允许按合同数组顺序或 PNG 数字推断开始。保留 end/whole-scenario 引用，range_review_status=pending，再由镜像源码实际 cp.start/输入/原 submit 与 checkpoint facts 建立人工确认的有限动作段。master/material 等 deferred 条目可能有 setdefault 起点和重叠范围；必须标 shared_setup/overlap，不能把整段点击数当该项员工操作次数。
4. **每件截图精确关联**：读取 observations.json 的 `{label,value}`，只收 value.screenshot 且文件实际存在、PNG header 可读、SHA匹配的图片。`Evidence.snapshot` 的文件前缀是 len(observations)，**不是动作编号或时间**；用明确 HK label（`hk-001-business`、`hk-134-report`、`hk-152-functional-source`、`hk190-business` 等）与对应 check/源码 snapshot 调用关联，边界匹配防止 HK001/HK010串项。其它图按实际对象/阶段 JSON pointer 校核，不能“场景目录下所有 PNG 都支持每个需求”。主页面/最终事实、关键输入或拒绝图分别留标签；某项无图/只显示别项时标 missing/needs_review。
5. **事实与实际断言**：check.evidence、steps、checkpoint.report_sources/material_sources/warehouse_sources 等保留原 JSON pointer，核原门店/员工/原单/版本/金额分/数量milli/积分整数/任务/独立复核/事件/流水/原件长度+SHA。将 checkpoint.criteria 文本声明与执行结果分开：字符串列表不是六类 criteria 分项 passed，也不证明所有 source 中 require 分支都运行。assertion_refs 只引用有实际 facts/native metadata 的已执行子动作，另给同 SHA 源码文件/函数/行作为断言解释；没有独立证据的条件保留 not_tested。
6. **网络是佐证**：通用 network.json 只存 request/response 的 path/method/status、Cookie/CSRF存在、店/CSP等，不存 request_id、动作序号或时间。不能仅同路径有一个200便与每项点击连接。原请求唯一性、动态 action、原 ID/version/request digest、values、现金/原数据不变，应引用该项 evidence/steps 中 native metadata 与源合同的实际响应事实，再把全场 network 作背景链接。允许的403/409/422应与原拒绝/无业务变更对应；5xx/page_errors/external_attempts 非预期则不能 final通过。
7. **文件/CSV/图表**：报表逐项绑定真实范围/filter/source IDs/oracle/图表/CSV行数与字节/hash及唯一新增导出审计，不能用其它 dataset 的非空列表。库存/资金/权益/返还/保留成本要区分。文件仅存元数据+SHA/size与授权范围/原下载事实，不装入BLOB、base64或正文；下载/导出引用不能自动算员工办理外部手续。
8. **条件单独汇总**：收 catalog 的必需/条件/suggested，checkpoint 的 conditional_checks、conditional_not_tested、conditions、unexecuted_scope、planned_pending、partial_requirements 等。保存原值/来源 pointer 后逐条件分类 passed/failed/not_tested/not_applicable/unknown；not_applicable须本轮条件不成立的事实，不能由 false flag或缺字段自动推出。建议未测仍明确保留；真实银行/员工/PG/Linux/ClamAV/OS输入法/live model/生产等边界另列，自动点击不替代。

## 人工截图审阅与 Chrome 点击分别留证

**PNG 人工/模型审阅**：逐项读取属于该项的真实截图与动作/facts，记录 reviewer、实际看过的每件 SHA、notes/问题，rubric 的 visual/simplicity/conciseness/fact_clarity/recovery/accessibility 六项 1–5 分；每项至少3分且有依据才该项 screenshot_review=reviewed。模型评图标 reviewer_kind=model，不冒充员工反馈。visible_text 由当前 scrub 截为最多2000字，不能据此断言整页没有多余文案。各业务通常1440×1000 context；full-page PNG高度不是 viewport高度，基础三宽测试不能继承为每项移动端验证，未看手机/焦点就保留条件。

**原生 Chrome review_click**：沿同一次 fresh 实例、真实当前岗位/门店，打开本项原入口/原单/结果/报表筛选、展开必要原控件、核显示与应有权限，保留本次真实 navigate/click/key、URL/原单/店和独立PNG。默认审已有结果，不重复办理已完成原交易；需要新的业务操作仅在根登记范围内留新的独立事实。人工日志写 `manual-review/`，不覆写自动53的动作/DB摘要/截图。截图审阅不能填成 Chrome 已点击，Chrome 可打开也不代表该193项都点击。当前 IAB不可用明确 not_available；未实际Chrome操控、真实员工试用或输入法候选窗口只记 pending/not_executed，不降级桥接/fetch伪称点击。

本项 accepted 只能在目录相应必需/适用条件和六类标准（front_end_expected/simple_flow/concise_copy/backend_matches/hard_bug/source_integrity）都有本轮原证据、逐项人工审阅完毕后，由根明确登记。rubric 六分项与这六类业务标准有关但不一一等价，缺一类不能只由总平均分补齐。15 family 的代表页审阅可以形成共用体验发现，不能批量给没有实际阅图/操作/断言的条目勾通过。统计始终以193行 count，分别统计 auto、PNG、Chrome、accepted与条件缺口，不把它们相加。

## HK099 真实日期追加与最终冻结

保留原 customer_service/customer_followon/customer_reminders 对 HK099 的 partial/local_scope observation 及 acceptance_check_submitted=false，不改原 business-checkpoint/status/count。从同轮有限 source CV、双方集团身份与真实员工，依 `docs/architect/tasks/hk099-date-followup.md` 单独新建 **今天截止** 的原 HistoryGrant，记录原UI/本次新 request/前后数据保护；有效最后一天 Date D 原读仍有效，真实业务时区 D+1（严格大于截止日）再原生读不再展示共享历史，DB原授权不被改成终态。HK190的两分钟 expires_at不是Date失效证明，不改时钟/夹具造expired。

结果只 append requirements[HK099].supplements（独立文件/SHA、同run同镜像、Grant/CV有限键、Date/时区/原请求事实/截图与只读字段、旧行保护），不得把旧partial改为自动完整或覆盖失败。仍须逐条核车辆新建/编辑/Observation、history明确集团关系/撤销和逐原单/逐文件子合同是否有本轮支持；跨引用 HK190 只补具体事实，不把相邻需求passed复制成HK099通过。尚未跨日或实例已结束不能补真日期成绩，标 planned_pending。即使 full53与其它192检查完毕，HK099缺必要Date条件仍保留未完整。

停止实例后，复核 preview所引用自动文件SHA未变、原53/provider/run-summary全部终局通过，冻结 final索引SHA；新增人工/Date证据与原自动源独立分别哈希。HK099后续日期附录版本追加，不回写旧full53成绩。full193_business_acceptance在全部193逐合同及人工条件满足前始终false；合成业务体验审阅不授权生产上线。

## 本设计读取的当前合同指纹

这些是设计参考的当前工作树字节；生成实际索引时必须换为该run镜像的相同文件哈希，不把此列表当未来已运行候选。

- `tests/browser_click/business_acceptance_catalog.json`：`eeea5ea2088ac932fe9f725ef1d4bd68073507bd23f695df360ef0036ba8a3ff`。
- `tests/browser_click/rubric.json`：`5b5768cb49b027091e127362e6022cdc5843a0acda254dc6b8f549f570927ff1`。
- `tests/browser_click/requirements_manifest.json`：`19840f4fc5fd816d94ea35a4602a31bde4674105e44621eeb4cfe42bdad27a1f`。
- `tests/browser_click/scenarios.py`：`d582050454c57af8a687105b154e8785b279481a7f9a4dd525a8d55bf54e28bd`。
- `tests/browser_click/run.py`：`8f40932b9a3bbfbc3122a0ee20a92883684e0fd99413f11bf2a549d0fcfd5cad`。

后续若需实现外部只读索引工具，须由根明确登记入口/文件范围；本页没有新增工具、运行或自动评分。

## 最小只读 preview 核对（文件结构诊断）

不新增 framework/runner。根可以用一段标准库 JSON/Path 文件读取做下列检查，输出 diagnostics 到外部；不 import app/scenarios、不跑测试、不访问 SQLite 或 private credential 指针。

1. 根限定唯一当前 run，并显式区分 `diagnostic_selected` 与 full53 preview。从该轮 browser-click-report+business-acceptance-report 检查原题/check关联；实际 business scenario 由 acceptance-report.checks[].scenario 取得，再与该轮镜像静态 BUSINESS_SCENARIOS 的40集合比较。只有报告内已执行且 passed 的 business 场景进入结构通过清单；失败场景也保留状态，不将“目录存在”当场景通过。final仍需前文完整53门槛。
2. 每个 passed 场景读取固定 `evidence/<scenario>/business-checkpoint.json`，require scenario同名、complete/passed真；逐row精确 id/title/check_id 对catalog，check.status=passed且evidence为非空dict/list，检查未知/重复/串项；0/false为合法事实，不能用`any(evidence.values())`判断“没有证据”。全部引用原JSON pointer，不读SQL来补洞。
3. actions.index必须精确1..N。按已记录的start count/end换为闭区间，保留缺边界与deferred重叠。observations中value.screenshot按明确HK三位编号/同原scenario定位，要求resolve留在本run/evidence、实际PNG文件/签名/尺寸/SHA；这只证明文件可定位，不证明可见内容正确或人工已阅图。统一network path200不能归为独立check的实际提交证明。
4. partial_requirements单列，不能进入check唯一map；条件和计划pending原样保留。source_contract/candidate/mirror字段有则核真实本轮；缺字段须从本轮镜像provenance和注册函数绑定，明确fallback，不能制造字段。steps/evidence可能是多动作或字典，不做所有family一刀切字段推断。

已只读核 `business-reports-complete-source-20261001-06`：selected，6/6终局、5pass/1fail、snapshot_stable=true，source `a2cd8704e5e02aa0c24a72bec269497e62554adc8284300098ae4191e8e6a9f7` / scripts `02c316bac9eb1903554159c9bfab92620610ff7613ae0fd7d059a1da8fcd5307`。5父checkpoint complete/passed，合计40精确check，每项evidence非空、原标题/check匹配且原HK截图可定位并具PNG签名；actions序号连续。该run不是最终193索引输入，不拼其它run成绩，未实际阅图评分。

| 本轮已通过父结构 | 项数 | 本次确认的特殊字段 |
|---|---:|---|
| presales | 7 | 没有candidate/source_contract/mirror；只记录action end且实际执行顺序HK006在HK003前，不能按catalog次序猜区间。 |
| vehicle purchase | 7 | 有source_contract，没有candidate/mirror；有start/end，HK178为deferred末尾图，范围可重叠。 |
| master data | 15 | 有source_contract，没有candidate/mirror；181/182/184等deferred图在末尾，catalog次序与执行图次序不同。 |
| material | 9 | candidate/source_contract/mirror均存在，有material_sources；部分同次流水/库存表项evidence只一个顶层事实字段仍是真非空，不用key数量评分。 |
| system management | 2 | 有source_contract，没有candidate/mirror；partial HK192/HK193隔离。本次不打开synthetic_system_private_credentials observation指向的私有文件。 |

失败reports-complete-source checkpoint本次complete/passed=false，HK152 not_tested、HK153 failed；即使有candidate/source_contract/mirror也不汇入通过。只读取其状态，本文不解释退款失败或削弱原守卫。

再次核清单/C评审scope：127原reviewed business包括业务主档/字典的真实管理岗位动作，**不含** main的`add_user/add_users_batch/edit_user/reset_password/add_store/edit_store`这六个管理/凭据闭面writer，它们当前仍Depends(get_db)。原auth/password已有独立显式writer依赖属于先前修复，本次helper不改变认证算法。note_refusal另开Session不继承此request bind；其它导入/扫描/配置闭面原scope明确不自动纳入。SYS场景passed是本次实际输入结果，不是这些闭面并发writer已被127补丁修复的声明。C组“无阻断”仅第29–41 API的机械delta与db helper，不宣称全应用busy/517已解。
