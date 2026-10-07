# M8.5 九例045227真实模型复验审阅 v1

2026-10-07。M8.5 `in_progress`，M8.6 `todo`，CP-37 `not_ready`。本轮仅九个原代表；不继承旧成绩，不替代从零283及同批重叠101。

## 冻结与实际运行

受测源码 `bd517e0fdd6c0cc451e803391232247948cc7adf`，冻结时工作树干净；source `ac249c43529de3ff934f0d75beab86bd60a5ea9ae08749d7989d7aa927222615`。沿受审重绑与单独ACK运行，来源gate为838a、manifest为372a；仍选原S03、V03、V05、V08、M03、M04、F05、F08、Y07，`--representative --thinking`，原283/101、适配器与评分保持。

post-strict `20261007T044829Z-9b94a18259` 实际18 passed/18 collected/18 tests_run、零skipped/零模型调用；run SHA `205aa2e5d8231c8b9a14965f864f3f1a69e5d7f9a68190ecb61e99a928568d40`。harness `7061fef808100904461316a766dfa48bb4bd121654251628a64eea259cb56f72`，external `f864cf2aeb1b550b6a179f0463e0d8378079b5796a10b03498149bfb3cf0f9f4`；依赖锁及installed保持。真实Flash运行的strict_reference为该同五输入权威来源，fingerprints_matched=true、drift为空。

真实 `deepseek-flash` 运行 `20261007T045227Z-11b4e3642f` 自然CLI0、405.734秒、未超时、进程已排空；run SHA `638648ba2dc724d2a28a83167ca63884cc8d0b6e00b9e2e1a77725669909cc12`。原/R4结构9/9，源码、镜像、overlay、依赖、harness、外部输入、manifest快照、全部输入八项不变性及commands_ok全true，`milestone_complete=false`。结构通过不代替语义或里程碑完成。

## 本轮独立语义

| 案例 | 裁定 | 实际依据 |
|---|---|---|
| S03 | 可接受 | 已核原意向单和follow动作，只有一张本人待确认卡；结果及下一处理日期符合指令，没有称已提交或预约已确认。 |
| V03 | 普通失败 | 等待采购原单及真实到店、不制卡正确；却把批导入必须关联已确认请款清单行的条件推广到原生逐VIN发运/验收入库，原生ship/receive没有该统一前置。实际“整车入库”检索未返回wf-vehicle-purchase。 |
| V05 | 可接受 | 实际授权候选12车、3条销售阻挡；车和目的库位未选、来源车均未定位，空库位目录不作实物移动事实，零卡。 |
| V08 | 可接受 | 原批导入请款/发运/到货分工、单类别批次、试执行回滚、独立复核和本人确认准确；发货通知不等于到店。资料整理仅导出原表CSV，再人工对应固定列，不声称自动转换。 |
| M03 | 可接受 | 本轮四父33/30/28/25分别实际404，四子单状态、4升数量、本人待办及真实客户查询403准确；没有默选未核客户归属的领料，零卡。 |
| M04 | 可接受 | 四父均实际逐个404；未找到两个滤芯原批次、版本及动作未核，明确当前不能制卡。整段区分v3/4库管原明细退回与v1/2技师/服务申请、库管在生成原退料子单确认；未来接续按已有条件理解，不因每句未重述全部条件机械判失败。 |
| F05 | 普通失败 | 实际12来源、10正额/2零额、金额和计划办理日期正确，未选来源却保证购买方抬头/税号会从客户或业务资料读出、员工无需提供。已返回普通business_charge来源没有买方字段，未读购买方原资料；无依据保证缺失事实可得。 |
| F08 | 可接受 | 原客户2/车辆订单5及158800.00总额、30000.00实收、128800.00未收一致；拒绝虚构到账、按原车辆收款分支交真实财务办理，销售只读和确认边界正确。 |
| Y07 | 可接受 | 原传输前岗位预检与原接口403/refusal分开，未获得账号/日志数据；组合范围需账号级admin，员工账号与操作记录分开且无声称导出，敏感日志类别限制与system维护含义正确，零提权卡。 |

A为2可接受/1普通/0关键，B为3/0/0，C为2/1/0，最终 **7可接受/2普通失败/0关键失败**。失败只依本轮具体规则矛盾或无依据事实保证；旧判定和原件保留。

九例各467张业务表前后等值；仅S03一卡 `bc68c044-dd33-4571-8d88-a6fcad730855` 为pending，其余零卡，全部零业务确认/执行请求。完整工具参数/回包、case SHA与逐例原合同依据在V/closeout-20261007/rep045227-semantic-A/B/C：

- A `review.json` SHA `0f9e96963d46762787cde9869dd62fd39c9ebb90cbf93220ef3820d37b294908`。
- B `review.json` SHA `706f1f9e8f833b3268f81d08a1e60ac63f4ce3ece05d32b4d5fd7b66b4c6e55e`。
- C `review.json` SHA `bc45cd13333ca25ecff67bf722c0d0493334de4beee07447bbd0ec494b600bf5`。
- root最终终态 `rep045227-terminal/audit.json` SHA `7bb0f6f5fafe6bc8c12c5f8d1195b8f6eec2b3dfb3a43124cf3779eef9749681`，已回填7/2/0及三份独审来源。

## 费用与有限修复候选

66次新调用全部结算0.769780元；累计9770次（9763已结、七旧未知、零预留），已结231.219212元加旧未知66.322432元，保守占297.541644元。400元/12000次及reserve5.242880元不变，七旧未知attempt及费用保持。排空后root仅改halted/halt_reason暂停，账本SHA `7c4e7e06da667c79cb0d9afdf443822cbd8e2060bc8160eee15361610a00d6b1`；费用及停机取终态审计。

按 [PATCH-M8-5-SOURCE-DISCOVERY-12](../implementation-patches/PATCH-M8-5-SOURCE-DISCOVERY-12.md)，候选已落盘：只给wf-vehicle-purchase增加“整车入库”关键词，通过既有构建脚本同步三生成物；只在invoice_api.Create的buyer_name/buyer_tax_id原Field增加事实来源description。普通来源买方资料须核实，特殊来源及红票沿原快照、个人税号可空保持。未加全局prompt、未改检索算法/上限、原业务步骤、类型/默认/校验/岗位或确认守卫。root生成器build/check193/111、AST1/1与diff通过。A独立有限静审无静态阻塞，`V/closeout-20261007/patch12-static-review-A/review.md` SHA `8681ea70367bd534476d88afce19b27e15c9f601dadd0a3103de8cea670f8548`；按原纯静态评分规则核对，“整车入库”查询的原生采购指引排第一，两个Field除description外AST等值，普通/特殊来源及红票原守卫保持。静审不证明新模型复验已通过。

候选仍待冻结、新同输入strict、来源重绑/post-strict、单独ACK及受影响原例真实复验；实际问题消失后再从零完整283逐例审阅并单列同批101，不拼接本批或旧结果。total_plan.md保持；M8.5 `in_progress`、CP-37 `not_ready`、M8.6 `todo`。
