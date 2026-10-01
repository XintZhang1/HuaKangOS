# 同轮 193 项证据索引外部草稿

2026-10-01；当前 M8.1 同一项，按根授权准备。只维护本页及仓库外 `V/browser-click/launches/193-review-index-draft.py`；生产源码、测试、runner、catalog、共享任务索引及原自动证据没有改动。未导入 app/场景模块、运行此草稿或任何测试/SQL/浏览器；未打开数据库、真实环境或任何私有密码文件。本页记录静态审阅，不是动态 passed、full53 或 193 项验收结果。

## 产物与入口

- 外部文件：`C:/Users/tiefu/.codex/HuaKangOS-agent-validation/runtime-v1/browser-click/launches/193-review-index-draft.py`。
- 当前字节：38,316 bytes，585 行；SHA256 `a6d521d86296e047d010174c854ba9bf1a4f1aa37e34c24ecda3d048672af4b6`。
- 标准库 AST 解析完成；只解析这份源码，没有执行其顶层、函数或 main。没有新增测试框架、app 导入、场景导入、数据库连接、HTTP/模型调用或浏览器操作。
- 唯一输入为 `--evidence-root` 指向同一全新 run 的 `evidence/`；显式 `--phase preview|final`。输出在该根 `manual-review/193-review-index-v1-preview.json` 或 `193-review-index-v1-final.json`，独占新建，拒绝覆盖。当前没有执行入口，也没有生成结果 JSON。

依据 [193 索引设计](193-evidence-review-index.md) 和外部 native-review-draft 已核的 full53 preflight，草稿保留同轮 manifest、冻结源/脚本逐文件 SHA、三次源/脚本摘要相同和 changed_paths 空的门槛。注册常量仅从本轮冻结 scripts 的有限 AST（literal tuple/list、import alias、tuple 相加、函数定义引用）解析，遇到其它表达式拒绝，不降级为 import/eval。精确核 9 基础 + 4 UI + 40 业务 = 53，以及 expected/actual/all_registered 的相同唯一集合。

`preview` 只允许全53报告 complete/passed/full_registered=true、每场 passed 且动作非空、UI计数193/111/70/9完整、原 scenario_exit_code=0 和 `post_test_review.phase=awaiting_external_stop`。provider/CLI 的终局门槛仍 pending，不能从预览声称最终通过。

`final` 还必须正常 stop-requested、原 summary complete/passed/full_registered=true、review.phase=stopped、无失败 reason、final provider 两项实际外联计数均0。现 runner summary 不存原 CLI 退出码，因此草稿不默认或推断 CLI0；要求根以 **原 runner 实际退出结果** 显式提供 `--cli-exit-code 0`。final 必须存在同生成器 SHA 的 preview，且其原自动文件/冻结合同完整 SHA 清单不变。running state/provider 允许按原 runner 终局改变，不纳入预览不变清单；其它原自动 JSON/PNG/CSV/DOCX 均纳入。缺门槛时拒绝生成，没有 selected/失败 run 合并模式。

## 逐项边界

合同始终完整枚举 HK-001 至 HK-193，每项原 module/group/title/check_id 与该轮 requirements_manifest 逐字一致。唯一检查从40个原业务 `business-checkpoint.requirements[].acceptance_checks[]`取得；browser报告只确认父场景状态，再对 business-acceptance-report 的逐项 checks 和 automatic_status。未知、重复或串项拒绝，非空事实按 dict/list 的实际长度判断，0/false 仍是合法原事实；diagnostic_checks_passed 不参与逐项自动汇总。

草稿遵守实际 `scenarios.finalize_business_report` 规则：缺完整 check 保留 `automatic.status=not_tested/check_presence=missing`，不因此拒绝完整 full53，也不制造 check。HK099 的现有 partial/local 范围另给精确 `/partial_requirements/<index>` 指针、相同源 SHA 与全场 actions 背景指针；原撤销事实、未跨Date范围和 `acceptance_check_submitted=false` 保存在原指针中，不进唯一完整 check 映射。未来完整 full53 的自动数需按原报告核实；预期192不能提前写成此次已得结果。Date supplementary 由根随后独立留证，草稿不读取或改写它来补原自动成绩。

动作只转换原记录 S/E 为真实 index `[S+1,E]`；严格核1..N连续。只存 end 或没有两端时保留未知起点/全场引用，不按合同数组、截图序号或执行顺序补起点。原同文件范围重叠标共享和 overlap，所有归属仍 unknown/pending，不生成独占点击数。

PNG 只接受 observation 的显式三位 HK label 与其 screenshot 指针，限定同一原场景目录，核普通文件、PNG/IHDR、尺寸和真实 SHA。缺图/无有效PNG继续 unknown，未读图片内容、未评分。目录里的其它图片不会批量归给每项；截图数字前缀不当 action index。network 仅背景指针，路径/状态200不作为某项原请求匹配，`network_action_match=unknown`。

原大型 facts/steps/report_sources/material_sources/warehouse_sources/source_preconditions 仅给原 JSON pointer 与共享范围说明；不复制 DB事实、BLOB、base64、附件正文或私有凭据。条件与 partial/pending 原值通过指针保留，catalog 的未测/建议文字保留；缺字段、false flag不能自动归为 not_applicable。

每行六个人工 rubric 评分均 `score=null/status=pending`；六类业务标准另外 pending，Chrome review_click pending、supplements为空、business_accepted=false。总计 screenshot_reviewed/native_review_clicked/accepted 均0，complete=false、full193_business_acceptance=false；`index_complete=true`只表示193行枚举齐全。

## 静态 schema 读审与修正

读取旧合成 `business-reports-complete-source-20261001-07` 的 catalog、provenance、自动报告和6份检查点结构，仅用于字段形状核对，不复用其成绩或图像内容。当前源码只读核 run.py、scenarios.py 及相关 checkpoint 构造/调用；C 独立发现的报告 provenance 异形已纳入有限分支。没有尝试拿这个 selected 旧run执行草稿。

1. browser-click-report.scenarios 没有嵌入 requirements；business-acceptance-report 是 requirements[].checks，而非顶层 checks。设计中两处简写不按字面使用，已快报根/C。
2. run.py 的 provenance.source_root 是原仓库路径；manifest.source_root 才是本run/source镜像。草稿仅保留前者为绝对路径元数据，不读取该路径；哈希校验只读取冻结镜像。已修正草稿最初错误的相等断言并快报根。
3. 物资等 mirror.sha256 与其它 mirror.provenance_sha256 均指同轮 provenance.json 文件SHA；只接受这两个有限别名，以及确切 source_sha256/script_sha256，未知key拒绝。
4. 普通 checkpoint.provenance 是 manifest 的指定五字段子集；report_business 的该字段则是精确 `{path,sha256,source_sha256,script_sha256}`，逐项核同run文件及摘要。依赖既有 `{scenario,runner_status,checkpoint_sha256,fixed_path,source_contract_sha256,current_run_only}` 与报告 `{path,sha256,scenario}` 两种记录分别核固定原文件、真实SHA及父complete/passed；来源合同字段缺失/null按原父实际字段对照，不造字段。

已向根/C快报 native-review-draft 的 mirror 和上述报告 provenance 异形；其外部草稿由根维护，本任务没有修改。本草稿需根在同一完整 fresh full53 证据到位后审阅/执行，才有可逐项评图的真实 JSON 索引。当前AST和schema读审不能证明预览、终局、图片体验、跨Date授权或193项业务通过。

## rcv11 冻结后的追加静态自审

根于本轮通知 rcv11/full53 原生候选已冻结启动；追加工作只读当前注册源码与外部索引草稿，不改冻结源码/测试/runner，不执行索引或业务。独立标准库 AST 符号遍历（未调用草稿 Registry、未import场景模块）核 SCENARIOS/BUSINESS_SCENARIOS/REQUIREMENT_SCENARIOS分别53/40/4个唯一三元组，函数均仅变成定义引用、timeout为正整数；39个涉及模块只使用草稿允许的字面tuple/list、Name、零级import alias及tuple相加。没有注册数组append/extend、下标修改或增量重绑。原193合同顺序及每项唯一check_id、原映射字段再次只读核齐；这属于结构读取，不是业务脚本执行或验收passed。

重新沿草稿的字段访问审计：conditions/conditional_checks无论原对象还是数组，草稿只保存其有限原JSON pointer，不调用这些值的items或按固定key取值，不会因合法数组形状把条件自动计为通过。报告的逐项检查从business-acceptance-report.requirements[].checks读取；已执行原check才读取scenario/scenario_passed/checkpoint。缺完整check的HK099只读取原not_tested且要求没有scenario，不访问不存在的结果字段，不由partial数组补check。因此原finalize_business_report合法的192完整+1缺check形状保留，不降低full53父场景状态门槛。

报告特殊provenance与prerequisite引用继续按已列的精确四字段/三字段形状核，不混同manifest provenance；未知字段/错路径/错SHA仍拒绝。所有人工、Date、接受状态不变。外部草稿字节保持 SHA `a6d521d86296e047d010174c854ba9bf1a4f1aa37e34c24ecda3d048672af4b6`；再次仅AST解析，未执行，未生成JSON索引。实际fresh证据尚须满足原门槛后由根审阅/调用，静态自审不保证任意未登记schema输入都可运行。
