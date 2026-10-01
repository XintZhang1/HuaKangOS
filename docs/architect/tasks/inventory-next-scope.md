# 下一批车辆、物资与维修业务点击范围（只读研究）

记录日期：2026-10-01。基于当前 HEAD `8993ca8c755194a42a48e7323fe355e80c6bf9ae` 与工作树实际源码；只新增本页，不修改生产、候选、目录、共享入口、夹具或计划，不导入 app、不启动实例。下列场景名为待登记建议，状态统一为 `not_tested`，人工六类评价 `pending`、`business_accepted=false`。原题名与 `HK-xxx-business` 均来自 `tests/browser_click/business_acceptance_catalog.json`。

## 已有范围与防重复口径

直接读取仓库外 `automatic-business-20261001-09/evidence/browser-click-report.json` 及该轮业务 checkpoint：注册/执行/通过均 28，失败 0；84 个唯一完整自动 check，没有重复 ID，业务接受数仍为 0、人工待审、193 全部接受为 false。目录中 `execution_status=not_tested` 是合同目录状态，不据源码审阅改为 passed。

| 本次已核实的来源或后继 | 需求范围及状态边界 |
| --- | --- |
| 整车采购 `vehicle-purchase-hk171-177-178-026-021-018-029` | 7 项在上述完整运行通过；HK019/020/023/024/025/027/028/030 均未有完整 check。HK029 的原占用分支另保留 conditional 未测。 |
| 物资 `materials-hk069-045-054-083-070-072-073-051-061` | 9 项通过；原采购、启用、移库和盘点事实可作为有限前序，不覆盖其它入出库、精品采购与精品销售。 |
| 首维修 `repair-selfpay-hk031-034-044-049-053-079` | 6 项通过；洗车/快捷 HK032/080/033、客户直收保险赔款 HK042 另已通过。**HK025 是“车辆其他出库”，不是维修项。** |
| 销售 HK008/009/011/022、退订 HK010、后继 HK012/015/016/017 | 均在上述运行通过；PDI 通过动作没有独立证明 HK037 的不合格、整改、复检合同；原加装出库没有自动增加 HK065；原收款没有自动增加 HK075/076。 |
| 保险后继 | 根报告最小 4 场景运行已通过，其中新增完整 HK013/014/077/113/114/115/116 七项；是独立运行，不能与 09 拼成同指纹全套。 |
| 财务后继 `finance-followon-hk095-097` | 实际候选仅 HK095/097 两项；“最小五组”是前序加目标的场景数量，不是新增五需求。当前运行结果由根留证，本页不继承结果。 |
| 系统后继 / 报表后继 / 会员后继 | 系统 HK192/193 两项；报表当前收窄为 HK146/147/148/149/150/151/155 七项，HK152/153 两项 partial；会员授权范围 HK123/124/125/129/130/132 六项。分别按各自新鲜运行登记，未跑候选不计通过。 |

报表 HK150/151 读取真实入出流水，与本页新的实物办理需求分别验收。会员后继实际 Retail 及权益核销仅供有限来源，不把其纯集团付款冒作 HK082 店内现金收款，也不自动追加 HK062/064。

报表首轮 `business-report-followon-20261001-01` 五前序通过、目标失败退出1；六报表仅 local passed。HK153 新采购两行/五原账已核对，四条本店当日历史 purchase 简表缺不可变逐行来源，原 complete=false/全范围金额null/无完整图正确。按新增 `PATCH-M8-4-PROCUREMENT-HISTORY-SCOPE-01` 保留153 partial，原全图/全期间汇总未测，不算第八完整项；新脚本静态修订不能覆盖首次失败。与 HK152 的历史窗口缺口分别留待真实原来源。

## 优先建议：单店车辆六项

固定候选建议名 `vehicle-import-operations-hk019-027-028-030-025-023`，导出六个独立完整 check；依赖固定本轮采购 7 项 checkpoint 的车型、供应商、整车仓/原库位及账户来源。原采购已付且两车已收，不足以登记另一笔合法请款。必须通过原 UI 建立并独立批准**新采购单**，两行或同一明确车型两车均须符合原采购数量；两个新 VIN 与旧单、库存及销售均不重复，不按 `SELECT latest` 取车。另通过原主档 UI 在同一整车仓增加第二实际库位，仅作为前置，不重复声称 HK178 通过。

建议人物：inventory 原采购建单/实物办理，manager 独立采购批准；manager 准备 funds，admin 作为不同原主管复核该批，原 manager 确认；ship/receive 批 inventory 准备、manager 复核、原 inventory 确认。admin 的独立主管复核属原岗位，不替代库管或财务实物/到账办理。每个任务先原 GET 取本人/当前版本；需要交接时走原任务或该域原 reassign。

| check ID / 原题名 | 真实输入到结果，原 UI 与 API | 必须保留的原事实 |
| --- | --- | --- |
| HK-019-business 车辆请款导入 | `#vehicle-procurement/{case_id}` → 原单与待办 → `#vehicle-imports/{case_id}`；上传 funds CSV、预检、trial、不同主管 review、本人 confirm。POST `/api/vehicle-imports/orders/{case_id}/batches` 及 `/batches/{id}/actions/{trial,review,confirm}`。 | 新采购 Case/Line、ImportBatch/Row/Claim/Request/Result、confirmed funds manifest 与逐行 FundsRequest 对应。trial 回滚原业务结果，仍允许该批任务/日志/收据真实追加；正式请款不生成 CashEntry、Vehicle 或已收库事实。 |
| HK-027-business 请款导入车辆发货 | 使用本次 confirmed funds manifest ID、相同 VIN；原 UI 上传 ship CSV，再 trial/review/confirm，执行原 purchase ship。 | 每一 ImportRow 对应本次 FundsRequest 与 Shipment；原发运日期、预期日期、库存在途及 source_reference/hash 正确。发运不算收车。 |
| HK-028-business 请款导入车辆到货 | 使用该 VIN 的真实本次 Shipment；receive CSV 明确当前业务日和本店整车库位，再 trial/review/confirm。 | 原 Shipment/Movement、一个实车库存代次、Custody/IdentityLink/PositionEntry 与实际收车位置对应；资金、发运、收车三来源分开；旧车辆不被改写。 |
| HK-030-business 车辆店内移库 | 新收车 A → `#vehicle-operations` 建 local_move → `#vehicle-operation/{case_id}` 另一主管 approve → inventory dispatch → 目的位实际 accept。POST `/api/vehicle-operations/orders`、`/orders/{case_id}/actions/{approve,dispatch,accept}`。 | 源位、同店在途、目的位数量/价值守恒；同 VIN、同 Vehicle ID/代次、店总量不增加；原任务及双方位置分录可追溯。 |
| HK-025-business 车辆其他出库 | 车 A 新位置 → 建 other_out，明确实际去向/接收人 → 独立 approve → 实际 dispatch；另建 other_return 选本次 completed 出库原单 → 独立 approve → 实际 receive。 | 出库库存及 PositionEntry 扣减、Custody 离店；实际退回创建新 Vehicle ID/代次，原成本和原出库引用保持；原出库车与旧分录不覆盖。回收后后继必须用新 current_vehicle_id。 |
| HK-023-business 车辆采购退回 | 车 B 保留原收车状态，用其原采购 Shipment：return_request → 不同主管 return_approve → 原 inventory return_dispatch → finance 原退款。POST `/api/vehicle-procurement/orders/{case_id}/actions/{...}`。 | VehiclePurchaseReturn/Movement/Position/Custody、原成本、供应商应退，以及原付款账户上的 CashEntry 退款分别对应。前置 finance 原 pay 需真实合成凭据、账户/流水与 FundsRequest；不能拿付款申请、退运凭据或未付采购当已退现金。 |

导入格式只按 `app/vehicle_imports_csv.py`：funds=`source_row,line_id,vin,amount_cents`；ship=`source_row,manifest_row_id,vin,shipped_date,expected_date`；receive=`source_row,manifest_row_id,vin,received_date,location_id`。严格 UTF-8、最多 200 行/128 KiB；金额整数分、VIN 17 位，manifest 只用本次确切原行。上传文件放外部隔离目录，记录元信息/长度/SHA，不写原字节到 checkpoint。每个批次及原采购的 CAS 都从当前 GET 取得；错误 CSV 全批拒绝与来源重复不产生第二业务结果，错误拒绝可有原批预检记录，按实际原合同允许有限追加，不能粗断整库零变化。

必需例外：若收齐后同一原采购进入 completed，剩余导入动作仍必须符合原 batch/current_case_version；不手改状态使导入可用。车 A 已 other_return 后不能再用旧采购 Vehicle ID 测采购退回，因此车 B 单独保留。拒收移库退回、批次 replacement/cancel/reassign、超上限等分支按实际合同另列 conditional/suggested 未测，不继承为已执行。此范围暂未发现明确缺失路由；真实 UI/任务/文件检查仍待首轮。

## 紧邻建议：单店仓储八项

固定候选建议名 `warehouse-original-flows-hk046-056-048-059-050-057-060-085`。复用本轮主档的真实 materials 仓、确切库位、供应商和财务账户；新增两项有明确名称/计量的合成耗材与礼品，通过原物资主档 UI 从零库存建档，并经 `#warehouse` activate 分配 **0 实物**、主管 approve，不能写数据库启用。之后原 other_in 才增加实物/原批准成本。旧 material_sources 的当前库存需 GET 重读，不能用历史库存快照当当前可用量。

统一原 UI `#warehouse` → `data-act=wh-new` 的明确 operation → `#warehouse/{case_id}` → 原任务本人；API POST `/api/warehouse/cases`，`/cases/{case_id}/commands/{approve,execute}`。quantity 为整数千分之一；库位启用提交 locations[]，不能误选不存在的单一 destination。other_in approve 必须由不同 manager 核对本单可用 receipt/invoice/signed_contract/procurement_contract 与明确总 value_cents；其它实物批准/执行按原 evidence。库存 POST 只发生在真实 execute，预占/prepare 与 approve 不算实际收发。

| check ID / 原题名 | 本批独立原事实与办理动作 |
| --- | --- |
| HK-046-business 物资其它入库 | 本批新耗材、礼品各真实零库存 activate/approve 后 other_in → 独立 approve 总成本 → inventory execute；Entry/StockMove/库位与批准的量、值一致。 |
| HK-056-business 耗材领用出库 | 从上述耗材实际源位建 consumable，明确领取人/班组、量与原因；approve/execute 原出库及原成本。 |
| HK-048-business 耗材领用退回 | 原 consumable StockMove → consumable_return，原剩余量内实际退回、approve/execute，原成本及位置恢复；旧领用留存。 |
| HK-059-business 礼品出库 | 本批礼品 gift 明确真实合成接收人 → approve/execute；原库存成本减少，不生成收入或现金。 |
| HK-050-business 礼品退货入库 | 仅本次 gift 原 StockMove → gift_return，原未退范围 approve/execute，原量/成本恢复、旧赠礼保留。 |
| HK-057-business 其它入库退货 | 仅本次 other_in 原 StockMove → other_in_return，原剩余范围 approve/execute 实际发出，StockMove purpose=wh_other_return、original_id 对上原入，不用采购退货代替。 |
| HK-060-business 物资其他出库 | 本次耗材明确实际处置去向/原因，disposal approve/execute，当前可用数量和原平均成本减少。 |
| HK-085-business 其他入库退货收款 | finance 在 `#business-finance` “其他入库退货应收”选本次 completed wh_other_return，建 other_return → 另一 manager approve → finance collect 实际合成到账，原应收与 CashEntry 分列。 |

可控样例：耗材 other_in 4000 milli/1600 分，领 1000、退 250、原其他入库退 500、处置 250；礼品 other_in 2000 milli/600 分，赠 500、退 250。此为待 UI 输入值，不是预制状态；每步先读本物资、本库位、原批可退量和真实成本，再按原服务算法核对，禁止浮点/猜成本。每个旧 Item/Balance/Entry/StockMove 仅允许该动作确切 ID/列变化，其它店和旧原单全行保护。

085 的精确创建封包：POST `/api/business-finance/orders`，purpose=other_return、customer_id=null、values={stock_move_id,source_version,supplier_id,amount_cents}；随后 `/orders/{id}/actions/{approve,collect}` 的 order version 与 case_version 均为当前原 GET。收款 account_id/reference/amount/evidence 必填，Supplier 必须启用且原 StockMove 未建过应收。供应方应退目标 adjust 与超收 refund 是独立追加分支，不能拿实际发出物资当供应方到账。无外部银行联调成绩。

## 精品采购和销售独立后批

建议固定候选 `boutique-purchase-retail-hk074-052-058-062-064-082` 六项：通过原 UI 新建有明确精品分类/计量的两商品并真实零库位启用，原采购多行 create/approve、分批原 receive、真实付款；部分原批次退货 request/approve/dispatch/refund；本店客户原 Retail 多行报价、独立 approve、同版 authorize、库存 dispatch、技术 install、客户 accept、财务 receive。安装需真实 WorkItem 与 technician，本目录 HK062 明列实际安装，不能为缩短改为无安装即完整通过。

| check ID / 原题名 | 必需独立观察与原 API |
| --- | --- |
| HK-074-business 精品采购订货 | POST `/api/procurement/orders` 的本批精品多行及 Supplier/qty/unit_cost 原审批；不能从 HK069 普通物资订货共页继承。 |
| HK-052-business 精品采购入库 | 原 `/api/procurement/orders/{id}/actions/receive` 各真实 receipt 与 warehouse prepare 原位、StockMove/成本/应付对应；prepare 不增加库存。 |
| HK-058-business 精品采购入库退货 | 同源原 receipt 部分 return_request/return_approve/return_dispatch/refund，原数量/成本、供应商应退及原 CashEntry 退款独立。 |
| HK-062-business 精品销售单 | POST `/api/retail/orders` 的真实两商品 lines、work_item_id/安装价；原 `/orders/{id}/actions/{approve,authorize,dispatch,install,accept,receive}` 闭合原 Line/Dispatch/Payment、客户接收与库存/现金。 |
| HK-064-business 精品销售出库 | 已授权该原 Retail 整单实际 dispatch，冻结量、具体库位/StockMove/成本及库存预占释放一致；不能以 approve/prepare 算出库。 |
| HK-082-business 精品销售收款 | 该原 Retail 原 finance receive（可分两次），实际账户、流水、凭据、CashEntry/RetailPayment 与累计实收及应收匹配；集团核销另源，纯集团核销无 Cash 不够。 |

同轮有限来源用 master_data 真实 WorkItem、MaterialCategory/Brand/仓库/库位和原本店客户，不扫描旧单。原字段/API 为 `app/procurement_api.py` 与 `app/retail_api.py`；UI `#procurement/{id}`、`#retail/{id}`。库存读当前 original_source/available，而不是物资或会员脚本的旧余额。HK063“维修精品销售单”及 HK066“维修精品销售出库”另须明确 related_repair_id 与同客户；HK065“精品加装出库”另须原销售/VIN/Addon 原出库独立 check；HK067“精品销售退货”另须 RetailDispatch 部分退、可售整改/复检、原现金/权益退回与安装保留费；HK068“精品销售套餐设置”须 RetailBundleRule 版本、安装/商品分摊、真正套餐 Order 完整履约，不用充值组合规则代替。

## 跨店范围：明确前置后再登记

现 fixture 的 manager/inventory/finance/service/technician 仅门店1；sales 同时有两店销售岗不代表两店业务管理/库管/财务。系统新员工接收账号门店2 service 与第三店 auditor 也不足以完成跨店实物/财务。须原管理员 UI 为全新合成员工明确授门店2 manager/inventory/finance（或原可恢复新账号有限更权），真实会话撤销/重登录及当前门店角色核对；并用原 UI 建门店2实际适用仓/库位与物资目录、明确双方对应物资。此为新前置范围，不能静默增 fixture 或借 admin 代办物理接收。

| 需求 / 建议同组 | 原 UI / API、双方事实与必要条件 |
| --- | --- |
| HK024 车辆调拨出库、HK020 车辆调拨入库 | `#vehicle-transfers/{id}`；POST `/api/vehicle-transfers` 与 `/{id}/actions/{approve,dispatch,accept,reject,return_ship,return_receive}`。真实同 VIN 双店批准、源出库、在途、目的新代次/原成本；再用另一真实车辆证明拒收/原车返运分支。双方 case_version + transfer version，凭据属各自店/原单，不跨店借 file_id。 |
| HK055 物资调拨出库、HK047 物资调拨入库 | `#transfers/{transfer_id}`，POST `/api/transfers` 及 `/{id}/actions/{approve,dispatch,receive,return_ship,return_receive}`；双店原 approve、源实际库位 allocate/dispatch、目的原 receive 逐行 accept_milli/reject_milli 分批收拒与明确原返；TransferReceipt/Movement/在途与原成本守恒。目的 Item 应独立明确匹配，不能修改 store_id 造调拨。 |
| HK071 机构库存查询 | 原切门店2后 `#master/items` 及原仓库详情 GET `/api/flow/master/items`、`/api/warehouse/items/{id}/stock` 读取非空库存/位置/在途，原 scope 只该店；未授权身份拒绝，集团汇总只读不作门店可用量。空店和仅门店1的 HK070 不替代。 |
| HK084 调拨出库收款 | 同轮真实 material 或 vehicle 调拨形成 ClearingBucket；原 `#clearing`、GET `/api/reconciliation/origins`，POST `/api/reconciliation/clearing` 及 `/{id}/actions/{pay,receive}`，付款店 pay/收款店 receive 的双方实际 Cash 与往来占额/offset 对应。两店财务和实际凭据为前置；系统只记实际收付款，不自动向银行付款。 |

以上可分为车辆两项、物资加查询三项、清算一项；拒收返运不能用一张已目的接收完成的单直接改状态补测，必须再产生明确实际来源。

## 维修未覆盖项与最小先决

| 需求 / 可独立后批 | 原入口与 API / 必须事实 |
| --- | --- |
| HK039 保险账核价单 + HK035 保险理赔维修 | 新维修 current Quote 原行 → `#claims` POST `/api/claims` party_type=insurer、payment_route=repair_receivable；assess、不同主管 approve、实际 transmit/result（补件与部分批准逐行）、当前版本 bind/allocate；原维修领料施工、独立质检、原保险方/客户分担收款及 release。评估/批准/保险方结果与门店 Cash 分开。 |
| HK040 索赔账核价单 + HK036 厂家索赔维修 | 另一真实新维修，active “厂家”原主档，party_type=manufacturer；对应独立核价、真实外部合成结果、冻结 manufacturer 分配、实际收款/施工交车。已通过的客户直收赔款 HK042 无门店收款且不是本合同。 |
| HK041 内部账核价单 | 可接上述新维修的单独内部原行，party_type=internal/payment_route=internal，明确内部主体、assess/独立 approve、当前 allocation/binding；没有对外 transmit/result，不造 Cash。 |
| HK038 返修单 | 首维修 report_sources 的已交付原单、最终 quote 行、同 CV/VIN/共享客户与车辆身份。使用 `#rework-extensions` 原责任授权 → 原店另一主管 approve → 指定接收人承接 `/api/rework-extensions/requests` → 原 `/api/service-intake/reworks/{id}/actions/{approve,convert}`；convert 同时登记实际到店和建立新维修，没有单独 rework arrive 动作。`/api/rework-extensions/orders/{id}/quote` 原责任 original_liability 与新增 customer_extra 分行，再原维修批准/同版授权/材料/施工/质检/分配/自费到账/交车。 |
| HK037 新车检测(PDI) | 尚在有效销售流程的本次新已配 VIN，原 inspect 不合格阻 dispatch → 原 rectify → 同 VIN reinspect 合格，缺陷/凭据/Task/FlowEvent 匹配。原已完成销售不可回退补测；可与新 VIN 的另一次完整销售及 HK075 同批。 |
| HK043 维修套餐设置 | 原 mixed PackageRule work+part 组件三价 C/P/S、不同主管 approve、同店 mapping；真实 Purchase authorize/issue/原 Cash，原新维修 Quote 选择本批 Lot/Reservation/capture/Entry，原材料、施工及承担守恒。当前 proposed 可读夹具和会员组合中的旧 BenefitRule.kind=package 不代替 mixed 套餐。可与 HK133/126/127 后续合同联合登记。 |

上述 claim API 都是 `/api/claims/{id}/actions/{action}`，封包 Claim.version 与 source_version 必须同时当前；内部核价不虚构外部回执。`claims_service.validate_allocation/bind_after_allocation` 要求冻结的当前原 Claim 金额和实际 payer 对应。已结清的首维修 allocation、Cash 与 customer_direct claim 不可改成保险/厂家承担；035/036/041 因此需要新维修完整前序，不能只新建索赔单即通过。优先可登记两维修原单五项（039/035/040/036/041），材料和当前维修工位现场重读。

HK038 的传统 `#service-intake/reworks` 显示“本次全部费用由明确的内部主体承担”，不足以覆盖目录“原责任与新增自费分行”。原 rework_extensions 已有真实独立 API/UI，`/api/flow/catalog` capabilities.rework_extensions=true；同店同 CV 可选，仍须 `/targets/{source_id}` 返回明确身份/指定 service 接收人，不能按手机号或 VIN 名称自行匹配。授权冻结原 Source.version/最终 quote/责任行、申请/审批/接收者 role+access_version；先承接，再本次独立主管批准并实际到店转换。首次原已完成修车的明细领料/资金不可复制到返修。

## 资金调整及边界清单

HK075“车辆销售收款”及 HK076“代办服务收款”虽已有销售/代办原现金事实，仍需各自完整 check 原累计、分期、凭据/账户/流水和手续费/代缴来源核对，不能从 HK009/015 自动增计。HK078“整车收款单调整”、HK081“维修收款单调整”、HK086“物资收款单调整”可基于同轮确切原 CashEntry，在原 `#business-finance` correction 创建 → 另一主管 approve → finance execute；已退原款的 `remaining_after_refunds`、原账户/业务日/reference/分配必须对应，冲正和正确记录追加，不重交车、不重施工、不二次物资收入。当前 HK090 通用误记更正只其已执行具体来源，不自动覆盖三业务类型。

尚不具备原 source 的条件明确待前置：两店岗位/仓库/双方实际款；新的已配且未终结销售 PDI；真实第三方承担的新维修与冻结 allocation；mixed 套餐发行/原维修核销；跨期 HK152 原期间开账。不能造银行、保险机构或厂家的真实外部处理；本轮外部回执为明确合成文件/UI 输入，真实外部条件仍待独立门槛。

执行者须保留每个 check 的真实 UI/API/只读 DB、旧行保护、当前 actor/store/task/CAS、一次提交和未知结果不重放；附件仅元数据/长度/hash 可入 JSON，BLOB 原字节只在内存比较。推荐批次没有执行成绩；首次失败必须区分产品、脚本适配及执行器，不能放宽来源或旧行保护求通过。

## 已核源定位

- 车辆：`app/vehicle_imports_api.py`、`vehicle_imports_csv.py`、`vehicle_imports_service.py:174/193`，`vehicle_procurement_api.py`、`vehicle_procurement_service.py:223/229/354`，`vehicle_operations_api.py`、`vehicle_operations_service.py:247/289/322`，`vehicle_transfer_api.py`/`vehicle_transfer_service.py`；原 `web/vehicleimports.js`/`vehicleprocurement.js`/`vehicleoperations.js`/`vehicletransfers.js`。
- 仓储/现金：`app/warehouse_api.py:19/48/79/85/93`、`warehouse_service.py:158/208/209/222`，`business_finance_api.py:60/92/98/104`、`business_finance_service.py:160/323`，`transfer_api.py:39/47/52`、`reconciliation_api.py:67/71/74`；`web/warehouse.js:45/62/79`、`businessfinance.js:93/99`、`transfers.js:8/49`、`reconciliation.js:59/66/71`。
- 精品/维修：`app/procurement_api.py`、`retail_api.py`、`retail_service.py:18`，`claims_api.py`、`claims_service.py:168/210/218/280`，`rework_extension_api.py`、`rework_extension_service.py:75/135/167/201/218/278`，`service_intake_api.py`，`web/retail.js`/`claims.js`/`reworkextensions.js`/`serviceintake.js`。分类/角色/单位从这些原源码读取，不照历史 demo 任务人或旧 flow_version 猜。
- 原需求合同：`tests/browser_click/business_acceptance_catalog.json`；发布工作流源 `docs/workflow-source/business.json` / `services.json`。本页不重写目录，也不把工作流存在作运行通过。

静态研究收口：最先建议单店车辆六项；下一单店仓储八项；精品六项、第三方维修五项与返修一项分别登记独立批次；跨店六项和 mixed 套餐须先满足上述新前序。最终文件 SHA 在交接另报，避免自引用。
