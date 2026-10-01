# PATCH-M8-4-BUSINESS-193-02：原整车采购至非空库存点击链

日期：2026-10-01。沿BUSINESS-193-01既定193项真实业务目标追加必要模块范围，不改变原业务规则或生产授权。

范围为HK-171供应商设置、HK-177品牌车系车型、HK-178整车仓库/库位、HK-026采购计划管理、HK-021车辆采购入库，以及有真实入库来源的HK-018车型参数筛选与HK-029库存查询。原UI产生新供应商、分类车型、仓库和库位；库管建采购计划，独立主管上传核价依据/核价/请款，财务登记本次实际合成付款，库管登记发运和重新核对VIN接收。文件、资金、实物和原任务分别核对，合成登记不声称真实银行或公司实物已发生。

允许修改：新增 `tests/browser_click/vehicle_purchase_business.py`，`fixture_server.py`仅增加finance/inventory身份及其store1真实岗位，不预造本轮业务结果；`run.py`仅随机凭据及同一脚本镜像接线；`scenarios.py`仅注册和同次逐check报告；`business_acceptance_catalog.json`只维护源合同；`README.md`、`rubric.json`及 `docs/architect/tasks/vehicle-purchase-click.md`、`business-fixtures.md`、`business-193.md`、`docs/architect/progress.md`记录本次范围/事实/限制。当前不扩展生产文件；实际生产缺陷另记精确补丁再修复。

负载分派如给demo员工，主管通过原任务转交界面交给本次可登录员工，不直接改Task或借用demo身份。库管、主管、财务使用不同账号，原审批/version/request_id/Cookie/CSRF守卫保持。文件只生成在外部合成运行目录，通过原上传表单及原文件安全记录；结构扫描不当ClamAV通过。车型指导价不当采购原成本；金额整数分，VIN/库位/来源关系原服务生成。

预期异常范围：错误VIN实际被拒绝且原库存不变；付款登记前后来源金额及预付/应付清晰区分；刷新不重复收款/收车/任务；岗位只能办理当前门店原授权动作。发生结果未知停止并查看原单，不换request_id重放。不以空页面、预置余额或手工DB改值取得通过。全新外部镜像与证据，生产四开关仍关闭，完整193及真实环境验收未完成。
