# PATCH-M8-4-REPORT-REFUND-ORIGINAL-BALANCE-01

2026-10-01，M8.1 同一实施项的原浏览器候选精确修正范围，先登记、不立即实施。当前 finance08/receivables07 仍运行，生产/测试/runner 冻结到关联进程全部收尾。

reports06 在当前 a2cd8704/02c316ba 完整执行6项，5父通过；最后 reports-complete-source-hk152-153 停在原退款表单选项核对，未发退款POST。新第三店原Case94、Payment5原付2000分/账户3、已退0；真实两个1000千分位批次，第一批已退500、全单供应商应退500。没有启用预付款Facility，没有付款抵用Allocation。原web/procurement.js在prepayments为空时，本笔剩余=原付款−同原款已退=2000，全单供应商应退=500；它们是不同上限，均正确。候选误把本笔剩余硬写为5.00，不能改生产显示或补造预付来源求绿。

只允许 tests/browser_click/report_complete_source_business.py 的 procurement_action：保留 responsible 返回的财务本人原GET详情，退款时核prepayments为空、原Payment唯一且关键身份/店/金额/账户/凭证/方向/原款关系与只读DB相同；同original_id退款与DB相同，按整数分计算原款未退额，并核UI本笔剩余等于该真实额。同时独立核真实本单应退500、填写实际退款500、选择本原付款和原账户。其余原Task/版本/请求唯一/实物退回/现金/回执/全旧行/文件字节守卫和20−5=15净款/库存1500检查保持，不放宽上限。

生产API、UI、原服务、目录、能力、模型与runner/CI不改。原失败和截图保留，收尾后才实施、独立精确源审和AST，再从全新外置目录复跑受影响6项；与不同脚本指纹父结果不拼全53，最后同当前指纹单次完整53联合、193分层体验/真实Date及原门槛保持。
