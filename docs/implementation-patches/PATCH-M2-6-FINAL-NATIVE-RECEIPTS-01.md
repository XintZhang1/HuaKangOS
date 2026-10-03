# PATCH-M2-6-FINAL-NATIVE-RECEIPTS-01

2026-10-04；依据业主“除了员工试用其他都要完成”及持续实施授权。四个原缺失领域合同静审结束后，单独回开原M2.6，补齐M7各族最终可靠原生命令回执，不创建另一套里程碑。原M2.6只支持通用Flow是阶段事实，不能免除最终M7合同；原历史记录、193/111、101/283与全部技术验收门槛保留。

精确生产范围：app/assistant_runtime_receipts.py只扩有限分派、来源前后签名、本人原GET集合与有限恢复记录校验；app/business_assistant_service.py只receipt_success_result纯映射新增服务器SubmissionSnapshot校验入口，保留旧调用契约。新增app/assistant_runtime_receipts_common.py（无业务写入的GET/envelope、严格原ID/digest/JSON签名及证据工具）；三个固定helper：assistant_runtime_receipts_commercial.py（原Flow专用、商业结果、财务结果及车辆收入），assistant_runtime_receipts_care.py（关怀/问卷/观察纠正/提醒、集团会员及清算），assistant_runtime_receipts_inventory.py（原接待、调拨及主数据/既有pointer）。业务API、模型、历史迁移、DTO、状态机、账务、权限、确认/重放规则均不改。只按已有源码和原有限报告的明确模板选择原模型，客户端不能提供表名、查询actor/nonce或自由URL，不建设动态发现/通用Agent框架。

三个helper共同约定：supports(operation_id)精确固定模板；read_source(db,user,snapshot)返回完整不可变签名，含精确原归一化command/digest、所有候选回执行身份/nonce/digest与冻结JSON结果或pointer及必要当前获权上下文；read_operations(snapshot)返回固定原GET模板；lookup_visible(db,user,snapshot,native_reader)严格原actor/store/nonce/digest/result及每个原对象本人GET；validate_lookup(snapshot,lookup)只认可本有限类型/基数/冻结目标和完整证据。无回执not_found、确实不可靠族unsupported、权限inaccessible、摘要/来源冲突mismatch；数据库/传输错误不伪装不存在。

固定原合同逐族重建日期/默认/nullable移除/key/action；typed-master哈希原raw values，字典哈希原DTO默认；Group会员委托核原membership purpose/values/版本和真实member原GET；提醒仅原receipt.as_of作为日期，旧Care与新Correction同nonce双记录歧义拒绝，created=[]只在此原生成族凭真实回执允许，非空逐原关怀GET。实体或物理到账/收货记录不是命令回执。跨族同数字ID不混，原result零/多对象不可强造一个Case。Dossier /record原GET写审计，不用于零写可见性。

原核心confirmation冻结、Proposal/Work/Run/Plan/Grant归属与CAS/fence/60秒proof、当前员工门店岗位/启用/授权版本、禁止聚合、不自动确认和request_id稳定全部保持。每次await前关闭清洁只读事务，await后新连接重读全部来源及当前权限；source签名包含原result变化，不能只核回执id/digest。恢复仅记原命令提交成功，不记后续到账/实物/外部手续成功。

外部验证仅现有V/tests/m82-closeout/shared-contracts/test_http_privacy_workspace.py与必要原领域overlay同节点兼容：追加少量真实员工原HTTP创建/原助手确认/回执核对、缺失/错actor/digest/失权/来源变动/零或多原对象组合。禁止手造Receipt/Cash/Event求绿；原节点/断言/失败原件保留，输入来源SHA与实际ordered collector注册完成后仅V/run_validation.py隔离镜像执行。不新增平行runner、读取公司库/原预览库或真实.env；本项无真实模型调用。计划当前M2.6/CP05、docs/architect及小型编码审阅报告允许维护；其他门禁仍按原顺序实际完成。

来源：外部m7-native-receipt-source-inventory-20261003T204848Z-f48f9ac422/inventory-v2.json SHAab1b920e7a22a99c4835cc6786f940d388a7b38ead4cf1ad50ac4ed81b36d41c；m7-native-receipt-finite-branches-20261003T212938Z-cdf98f4214/finite-branches.json SHA0f866d0739b277be9784c7518729b13de055b4cf3086620a323ca99f97b958ff。原81模板只表示当时静态路由匹配，不是当前全业务通过；四新领域以当前真实API另补。
