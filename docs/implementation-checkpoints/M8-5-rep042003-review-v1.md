# M8.5 九例真实模型复验审阅 v1

2026-10-07。M8.5 `in_progress`，M8.6 `todo`，CP-37 `not_ready`。记录本轮九个原代表，不替代完整283或同批重叠101，不继承上一轮语义裁定。

## 冻结与实际运行

基线源码 `a3dab3771bb5737e9537238b24a9a5b5dcf8fa67`，当时干净工作树；源码指纹 `5a8fdd07618de2aa5ce3364cf0cb23ec7a372285f4414fb8725e461e12245381`。仍使用原 S03、V03、V05、V08、M03、M04、F05、F08、Y07 九例 `--representative --thinking`，原283/101定义、适配器、评分和确认合同保持。

受审来源门禁重绑及单独费用ACK后，post-strict `20261007T041541Z-6f51ba8462` 为同五输入权威来源：实际18 passed/18 collected/18 tests_run、零skipped/零模型调用，八项标记及commands_ok全true；run SHA `f47515ba66ee8da74c25412e0f965b246abae0d6112cb6083be49e1579406545`。harness `31965e2d058651088040f4203bd09dab656e3f6c6a1cd5e096deb0926974405f`；外部输入 `f864cf2aeb1b550b6a179f0463e0d8378079b5796a10b03498149bfb3cf0f9f4`，依赖锁与installed保持。

真实 `deepseek-flash` 运行 `20261007T042003Z-bd05a94572` 经V/run_validation.py执行，自然CLI0、318.25秒、未超时、进程已排空。原/R4结构9/9；源码、镜像、overlay、依赖、harness、外部输入、manifest快照、全部输入八项不变性与commands_ok全true；strict_reference权威五指纹一致且drift为空。run SHA `5c55ae46e266cc50543dc45bd54c835fb68391362d41857543d1b15a73ce0d27`，`milestone_complete=false`；结构通过不代表业务语义或M8.5完成。

## 独立逐例语义

| 案例 | 裁定 | 本轮实际结果或问题 |
|---|---|---|
| S03 | 可接受 | 原意向客户尚未确认下周来店。唯一follow pending卡针对原单13/version6，准确保留预算不变及考虑下周看车，下一联系日期2026-10-08；须本人点击才记录，不当成已确认预约。 |
| V03 | 可接受 | 原采购号与实车到店事实未定，正确等待、不备入库卡；供应商说法不等于原发运或实际验收。无原单未来建计划只是概述，未声称列举为完整必填清单或资料已足以制卡；不因非穷举沿用上轮失败。 |
| V05 | 可接受 | 本次授权候选实际12台、VIN后缀001—012，全部未定位、仅001—003有销售约定阻挡。未选车、无真实库位时等待，先登记实际位置后再按原条件准备店内移动；无额外主档或移车卡。 |
| V08 | 可接受 | 原catalog核实请款为admin/manager、发运到货为admin/inventory；各批独立，试执行回滚后由另一主管复核、原编制人确认。发运及到货都引用已确认原请款行，发货通知不足以证明到店，到货另核同VIN发运、实际日期和真实库位。本轮没有误述自动固定CSV转换、没有假称已读具体采购或已办。 |
| M03 | 普通失败 | 四张原领料34/31/29/26与真实状态准确、客户关联未知且无卡。但仅读父33/30（trace14/15、27/28）返回404“业务不存在或当前账号不可查看”，没有读28/25；回答却概括父33/30/28/25全读取不到，未查对象须保持待核。 |
| M04 | 可接受 | 来源仍未知，四可见领料均4000千分之一实际数量，显示4升，不能认成用户两只滤芯。父33/30/28/25本轮逐个实际查详情并全部404，不能继承M03两对象范围；父版本、状态仍未知。正确按条件区分3/4库管原维修明细退回与1/2技师/服务顾问申请、库管在原退料子单入库，并等待有权读取岗位，无补单号即授予本人权限/制卡承诺。404原因仍不能区分。 |
| F05 | 可接受 | 原12来源编号、版本、金额均匹配，10正额/2零额及蓝票正数条件正确。问计划办理日期、选来源和真实购买方；销售方在最终所选来源读取冻结快照，缺快照才条件补问，未把source35的issuer:null泛化。等待、零卡。 |
| F08 | 普通失败 | 无到账事实不得标已收、原实收由财务办理的边界正确。回答却沿发布wf-customer-statement错误的roles/entry.roles，称业务财务页仅admin/finance/manager、销售不能进入；原READ含sales等且保留本人客户/来源授权范围，页面只读访问不能与收款动作权限混同。没有越权写入。 |
| Y07 | 普通失败 | 原传输前NativeReadRolePrecheckDenied、全局admin组合权限、非admin敏感日志排除和账号级升级边界正确。末句却指管理员在“员工账号”页导出权限及全类别日志；原员工账号与“操作记录”页分离，两页均无声称的导出入口。具体导航/能力误述，零卡、无提权。 |

A为3可接受/0普通/0关键，B为2/1/0，C为1/2/0，最终合计 **6可接受/3普通失败/0关键失败**。三普通仅记录本轮具体事实；未来条件句结合完整前文判断，不因概述非穷举自动失败。

九例各467张业务表前后等值，仅S03一卡 `a7eabfb1-37c7-44ab-8ce0-8b7e6f213456` 为pending，零业务确认/执行请求。查询原403/404与岗位预检拒绝分别留证，不能称所有工具均无错误；预检拒绝不冒充原接口refusal。

外部独审原件在V/closeout-20261007：

- A `rep042003-semantic-A/review.json` SHA `5d26f8d0bc16e7c77c3df023ebf04cc2f502f2ef82be80d610d3f1136d6f1759`。
- B `rep042003-semantic-B/review.json` SHA `07435dfa07538f11aa18d45dd8f7d427da219e879d46a9f9d8fa63a1c1741545`。
- C `rep042003-semantic-C/review.json` SHA `689228a9f1a73bfab5341ad693fd90c42aa68f6a2273b4fc44e9fce53463b281`。
- root最终终态 `rep042003-terminal/audit.json` SHA `3dffeac34bcb8b18db1847afe7f08315e242365743929fc5ab77760e768cccda`，实际6/3/0已回填。旧原件、case SHA、trace与逐例理由保留，不覆盖历史。

## 费用、有限候选与待复验

58次新请求全结算0.590883元；累计9704次（9697已结、七旧未知、零预留），已结算230.449432元，加七旧未知66.322432元，保守占296.771864元。预算400元/12000次、单次reserve5.242880元保持。排空后root仅设halted/halt_reason暂停，账本SHA `f71317353320d8b93e64aa06b19baed460e998994040a3b080976c6367b30121`；旧attempt、费用及未知占用保持。费用与停机事实取排空后的终态审计。

按 [PATCH-M8-5-FAILED-CASE-SCOPE-11](../implementation-patches/PATCH-M8-5-FAILED-CASE-SCOPE-11.md)，已登记生产候选只在原gateway的已执行JSON GET /api/flow/cases/{case_id} 403/404外层回包附本次真实正整数queried_case_id及detail未核实说明，原status/data/route/refusal/error分类保持；提示词原段按每个实际ID分别陈述父单结果，未读父单保持未知。bool、非法ID、参数错误、非JSON、成功查询及原传输前岗位预检不伪造该查询事实。不新增原GET或权限，不改变原API和业务规则。F08对应的 `docs/workflow-source/business.json` 仅在wf-customer-statement的roles/entry.roles补原READ八岗位（admin、manager、finance、sales、service、reception、customer_service、auditor），并在原前置说明中区分本人授权范围查询、财务创建与实际收款；manual原办理岗位和实际权限保持。Y07只替换原prompt组合交办句，账号/账号级角色用“员工账号”，日志用“操作记录”，不承诺两页没有的导出。原构建脚本同步三生成物，build/check193/111通过。

root AST2/2与diff检查通过；A此前仅对M03回包/父查询范围完成独立有限静审，无阻塞，`patch11-static-review-A/review.md` SHA `e2ac7b014783bb49d2e99119b0b729ed49e7fd60243e7d80100713dfaa0c68d7`。两读取路径沿同一原gateway，预检失败仍与真实403/404分开。A的有限静审不覆盖后来追加的F08/Y07；C已独立完成补充范围静审，无静态阻塞，报告`V/closeout-20261007/patch11-supplement-static-review-C/review.json` SHA `96183409d271465e4135b6ca5d55a217b7b765d61743b16373975308f94d9297`。C核对原READ八岗位、查询与财务办理分工、账号/审计各自页面及无导出说明，manual、193/111映射与原API/UI保持；静审不能证明新模型已正确陈述。

三项实际问题的有限说明修复均已按PATCH11登记并落盘，A与C分别完成相应范围独立有限静审，无静态阻塞；不把已落盘和静审当成模型问题已消失。候选仍待冻结、新同输入strict、来源门禁重绑、post-strict、单独费用ACK及原九例真实复验；实际问题消失后才从零完整283、逐例语义并单列同批101，不拼接旧批次。total_plan.md未改；M8.5仍`in_progress`、CP-37`not_ready`、M8.6`todo`。
