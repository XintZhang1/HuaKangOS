# PDI独立车辆来源静态审阅

2026-10-02；manual_review_draft 独立只读审阅。结论：未发现具体源码阻断，可通过原 `tests/browser_click/run.py` 全新联合入口实测。此结论仅为源码准许验证；没有执行新脚本、浏览器、模型或SQL写入，不记PDI、全53或193通过。

## 第15轮实际失败的确定来源

第15轮 source `76862a922e57832b92d6f9e68ec0804e2182a992da0cd3b150297487532a525b`、scripts `c7aa731d9e70242d51aa0d6bde9d2d57852999e7a3fc942fcc2bcfba5de0b6e3`。只读该轮已标记、已停止、WAL为空的外置合成数据库，使用SQLite mode=ro/immutable；未导入app或读取私有密码。

PDI旧依赖第244行比较车74与采购HK021旧原件。车74的id、VIN `LHKV44E11F24BCBF2`、store1、车型、inventory_generation=1、purchase_cost_cents=11000000均未变；唯一所比字段差异是approval_state从approved变void。不是车辆运营HK027成本调整，也不是旧行成本/代次被改写。

同轮 `interstore-original-hk020-024-047-055-084/business-checkpoint.json` 的HK024 `separate_rejected_transfer` 明确使用原退订车74。调拨transfer2/原号 `HKV1D179FD970BA4E04`，原店case183、目的店case184：实际dispatch追加position_entry13，vehicle_id74、location1、quantity=-1、value_cents=-11000000、evidence335、actor14；旧74位置转exited/location=null，旧行保留void。二店拒收后实际return_receive追加新车79、position7、position_entry14，原VIN不变，quantity=1/value_cents11000000/evidence338/actor14。transfer2状态returned、received_vehicle_id79；VIN identity3的custody当前车79/store1/generation2/version15，旧74/gen1仍为历史行。不能把旧local74当当前可售车，也不能删除当前实车/身份/位置守卫或重排场景绕过已发生前序。

车辆运营HK025确有另一独立VIN的退回77，第15轮HK020已接收的调拨来源为77→78；它与HK024拒收74→79是不同原车。HK024原件、来源guard和当前行共同确定上述因果。

## 精确补丁静态审阅

对照第15轮冻结 `scripts/sales_pdi_business.py` 与当前唯一修改文件，当前PDI SHA为 `f5b0caebaec7266c9b6145d6fcaaa5603a6dd904af72da8d018554c0a896d21b`。新scripts总SHA `66a265e65333b1f688f7dd74cb5de32acbb7a249059d1140c8239b7ca39502a4`；生产/source保持上文SHA。主任务登记 PATCH-M8-4-PDI-INDEPENDENT-VEHICLE-01，本审未改生产、测试或runner。

历史退订与采购关系仍严核原id/VIN/store/model/gen/cost及唯一receipt；旧approval仅记录事实，不再声称它是可用库存。新种子只取同轮HK177 new_hierarchy的已发布车型、HK171原供应商、HK178原整车仓/库位和原bank账户；原主档启用、版本、本店及仓位关系守卫保留。车型补brand_name/series_name来自原品牌/车系，使原quote选择输入形状匹配；不虚造车型或换原编号。

既有 `receivables_business.vehicle_precondition(e, context, credentials, fixture, supplier, model, warehouse, location, account, token)` 参数实参匹配。fixture沿原sales_order本店六角色；原helper经原UI建立一台新VIN采购、主管核价、请款、财务实际付款、发运、库管实际验收。该helper原合同成本80元/建议价100元，实际成本8000分由原付款/入库来源严格核对并留档；PDI原130000元售价及两笔收款合同不变，不能猜填旧11000000分成本。

AR返回source已有vehicle/model/position/custody/identity_link等原事实；`original_position=source['position']`准确满足原PDI dispatch的库位消费。旧receipt无剩余PDI消费；新helper仍实际核验原receipt/shipment/line/model/movement、唯一追加、VIN集团身份与当前custody。新采购全文保存外置checkpoint，最终report_sources追加独立采购case与真实cost。

独立新车必须不同历史车74、当前approved；原 `S.physical(...state='stored')`、当前VIN/custody/holds、原可用配车候选、PDI初检/整改/复检、付款幂等、负向拒绝、出库价值、提车与回访守卫均保持。未新增API/fetch桥接、SQL写路径、权限绕行、baseline第三车、重排或大helper。静态未发现具体阻断，后续仅以全新第16轮原入口实证为准。
