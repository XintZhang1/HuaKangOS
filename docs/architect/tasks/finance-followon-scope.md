# 财务后续：开票与期间核账最小来源合同

2026-10-01，负责人 test_inventory。根授权仅只读研究及新增本独立文档。财务五项候选保持冻结；本页没有新增或注册脚本，没有修改生产、fixture、运行入口或计划，没有导入 app、启动实例、浏览器或执行 SQL。以下都是待实际执行的合同，不继承历史成绩。

## 原目录范围与项数

核对完整193目录与发布工作流后，推荐仅两个完整 check：HK-097-business「开发票」（wf-invoice-issue-red，原入口 invoices），HK-095-business「月结查询」（wf-period-close，原入口 reconciliation）。目录将申请、外部办理、票据差异、原票冲红合为HK097，将非空核账、差异、重算、独立封存合为HK095；不能把这些动作拆成3–6个新需求成绩。HK096「客户月结处理」已在本轮前序五项中，不重复提交一个新完整check。

若必须达到3–6个独立新check，需另登记有真实源的金融业务范围。HK086「物资收款单调整」需要真实物资/采购/往来收款及正确分配，不能拿客户预收Cash替代；HK092「收款单退款申请」需要原销售退订或售后纠正及逐原款退款，不能拿已完成的A/B服务收款或预收退款替代；HK084「调拨出库收款」还需同轮双店调拨与实际双方往来。它们不在本次开票/核账最短链内，保持未覆盖。借款、资本投入、任意内部转账没有本批新增原需求check。

## 有限同轮来源与岗位

唯一直接前序是 finance-hk087-090-091-093-096 完整passed检查点中的 finance_sources。先核当前run报告注册且该场景passed、检查点complete、同轮镜像/脚本/目录五字段一致，再读取有限输出，不从全库寻找demo、最新收款或旧历史成绩。必要键为 customer_id/account_id/service_case_ids/quote_ids/advance_id/original_advance_cash_id/stored_correction_case_id/stored_correction_id/corrected_cash_id/credit_link_id/statement_id/collection_batch_ids/payment_link_ids/refund_cash_id；两张服务原单A/B分别净服务费6000分、已真实履约且完成结算。原FinanceAdvance本金余额及占额均0、原抵用4000分、两笔月结实际入款3000与5000分、原未用款退款5000分必须仍匹配，不以Task结束代款。

前序本身依赖同轮原销售客户及采购账户；后续只沿已经passed的有限合同追溯，不继承demo销售、财务或会员成绩。新身份/fixture均为0，复用 business_fixtures.sales_order 的 finance 与 manager、当前门店1的真实UserStore。财务创建及登记；另一manager独立批准/核对。不得用admin登录或demo身份绕过。

原invoice_service逐动作要求本人原Task：invoice_review、invoice_submit、invoice_result、invoice_result_review；manager若发现默认待办接手人为demo，应先经原Case页面明确转交给本轮随机manager。提交和结果Task由原单owner财务接手。原POST /api/flow/tasks/{task_id}/assign只有 version/assignee_id/reason三字段，没有request_id。开票批准及差异复核者不能等于申请/登记者。

reconciliation_service的batch_command当前按本店岗位、批次版本、Case版本和独立制备/提交者守卫；它没有invoice同款的本人Task前置检查，不在测试中虚构这条后端规则。仍核原reconcile与reconcile_seal待办产生/结束和独立manager身份，必要转交沿原UI办理。

## 一条完整输入到结果顺序

金额用整数分，前端填元。选择A为唯一开票业务源，原source_amount从已授权服务的fee_charge_cents取得6000分，与现金或会员流水相互独立。B作为同客户另一已结清服务源保留不动。

1. finance先进入 #reconciliation，新建包含前序所有原实际business_date和本次发票issued_on的明确期间；日期不超过原catalog业务今天、跨度不超过365日。先原GET确认该期间没有已有批次；有冲突不改日期绕过来源范围、不继承demo批次，应保留失败。POST /api/reconciliation/batches 返回本轮版本1。逐项核非空冻结Cash、原PaymentLink、预收更正/抵用/退款以及A/B服务来源，保存完整manifest/summary/digest；这是未封存原版本，不能写HK095通过。
2. finance在 #invoices「原业务开票依据」按精确A原业务号及ID点击 data-act=invoice-new / data-source=A。原UI有30条分页，用真实下一页查找A，不直接调用创建API。GET /api/invoices/sources/{A} 应为可开6000、已开净额0、pending0。申请蓝票60.00元，填写本轮唯一明确合成销售主体全称与15–30位大写字母数字税号、真实合成客户抬头（个人税号可空）、原业务今天/计划日及原因。若源已有经营主体快照，必须沿原issuer自动值，不用另一主体绕过冻结策略。POST /api/invoices/orders 携带 source_case_id/current source_version/direction=blue/original_case_id=null，生成approval的v3 InvoiceApplication、Case与invoice_review。
3. manager在原蓝票「独立复核批准」，上传本单evidence原件；finance在「登记已提交外部办理」填唯一合成外部申请编号及另一evidence原件，pending→working。两动作均携带request_id、当前Invoice Case.version和当前source_version；源Case在每个开票写动作更新，不能重复使用前序检查点版本。
4. 明确模拟合成外部票面为58.00元、批准60.00元的已知差异；finance先「记录票据差异」填observed_amount=58.00及唯一原件，再「登记实际发票」填唯一合法票号、原catalog今天、58.00和本单invoice类别原件。实际InvoiceResult为5800分且不可覆盖，原单转resolving并新增invoice_result_review；manager另件evidence「独立复核结果差异」后completed。不能把difference动作、申请或上传当真实结果；不得为了与批准相等而改真实票面字段。
5. finance从该已登记蓝票点 data-act=invoice-red「申请本票部分或全部冲红」，填8.00元及原票冲红依据。原表单自动沿用原票issuer/buyer，原original_case_id必须为本轮蓝票；另一manager批准，finance原submit与record登记不同唯一红票号、800分、本单invoice原件。原蓝票保持5800分，红票实际减少净开票至5000分；不会产生Cash退款或会员本金变动。随后回A原来源申请其余10.00元蓝票，经相同独立批准/外部提交/实际1000分记录，A净开票恢复6000、pending0、available0、correction0。三张原申请、批准、实际票据、原蓝红关联都保留；这组完整结果才允许提交HK097内部协同check。
6. 回版本1对账，GET应source_changed=true，因为新增invoice_results及原业务附件属于真实来源。原「提交独立复核」必须409「来源有晚到、冲正或余额变化，请重算产生新版本」，全原业务快照不变；不能直接封存旧来源、改digest或排除全部附件。finance原「重算新版本」生成版本2、previous_id指版本1，旧版本1只按原动作变superseded/结束Case与任务，manifest/summary/digest不改；版本2应包含本轮三个有限InvoiceResult及蓝红direction。
7. 在版本2实际UI可见的本轮Cash来源条目上点「记录差异」，差额0，说明「核对100元误记、冲回和90元正确记录的对应关系」，上传本批evidence；这表示有据核对事项，不编造现金缺口。随后「记录处理凭据」逐笔核原StoredCorrection、三Cash及实际账户/日期/流水，写明确核对结论、另一原件并携带issue_id/current issue_version。不能用说明替代未发生的账务纠正；本轮纠正已经在前序原UI真正执行。核ReconciliationIssue open→resolved，差额0保留，原理由/来源不可覆盖。
8. 版本2上传自身核对凭据后应source_changed=false；当前定义22仅把reconciliation原单的private_file_objects证明文件从业务来源剔除，业务原单文件仍纳入，历史定义1–21保持原口径。finance原「提交独立复核」draft→review；另一manager原「独立复核封存」上传不同本批evidence，review→sealed、sealed_by为本轮manager、Case completed，原Task/Event/Receipt一致。
9. manager从已封存版本2原「复开新版本」明确原因生成版本3，previous_id=版本2、revision=3；版本2仍sealed且manifest/summary/digest/sealed_by/时间及全部旧Issue不改。无新增业务来源时版本3的manifest/summary/digest应与版本2完全相等。再由finance提交、不同manager独立封存版本3，终局两个封存版本均可查看/导出，版本1留存superseded。HK095需这条完整非空核账、差异、真实来源变化重算和独立封存事实，不以打开页面计通过。

## 原UI、CAS、文件和导出合同

开票列表标题「开票与原票冲红」，详情「开票申请」「原票冲红」。选择器invoice-new/invoice-red/invoice-action[data-key=approve|submit|difference|record|review_result]，本单凭据与待办通过原open[data-route=case/{id}]进入。invoiceAction表单record文件类别invoice，其余Proof为evidence；每事实文件独立字节/SHA，上传后只输出metadata/size/SHA，不输出BLOB、密码/会话hash。实际下载发票通过原downloadfile使用GET /api/flow/files/{id}；该原下载会追加精确一条download AuditLog，其余原行不变，不排除整个audit表。

开票GET /api/invoices/orders/{id} 返回 current source_version和balance；commands POST /api/invoices/orders/{id}/actions/{key} 的values严格遵循实际schema。source_version和Invoice Case.version都实时重验，唯一request_id原样保留。InvoiceApplication/Approval/Result三表完全immutable，实际票号在issuer_tax_id维度唯一；过额申请、未批准提交、未提交登记、错类别文件、改抬头红票、未知结果均保留原拒绝，不重放求绿。

对账标题「业务对账与月结」，真实selector reconcile-new/reconcile-action[data-key=issue|resolve|submit|seal|recalculate|reopen|export]。POST /api/reconciliation/batches/{id}/actions/{key} 有request_id/version/case_version/values；resolve额外有issue_version。源digest必须依据完整冻结JSON重算，不能只比较页面200条或摘要金额。原UI只展示manifest前200条，没有分页或搜索：若本轮精确Cash条目不在可見范围，保留该真实UI条件、停止issue子流程并报具体缺口，不能注入DOM或API代点；完整CSV仍可核所有条目。

每个待封存版本实际点「下载本版本完整来源 CSV」，保存原浏览器Blob下载，再以utf-8-sig及csv模块解析，不调用Playwright response.body触发下载端点额外读取。原GET /api/reconciliation/batches/{id}/export源码没有export AuditLog/业务写入，故CSV前后全业务快照应完全相同，不能允许多余audit。必须核9列实际表头、行数等于完整manifest、原顺序/key/source/basis/case_id/整数金额/千分位数量/权益单位及JSON data逐字段一致，完整解析公式前缀转义（原字符串以=,+,-,@,制表或回车开头时加单引号）。保留实际字节大小/SHA和下载文件，不能自造CSV替代真实下载。

现金定义7保留前序六Cash：原误记10000入、账务冲正10000出、正确9000入、两月结3000/5000入、退款5000出。原cash_basis排除被纠正原款及仅作账务冲正，故本轮有效收入17000、有效支出5000、净12000；完整manifest仍有全部原六Cash，不能把源关联、抵用4000、InvoiceResult、集团本金及库存再加进现金。新票据5800-800+1000=6000是A原业务应开票额，不改变前序净现金12000、两服务收费12000或B6000的应开票可用额。

全店期间摘要可能含同轮其他已passed业务和明确demo背景，不能断言全店摘要恰为本批12000。应完整CSV重建定义7现金总口径，与原UI/API/冻结summary一致；再按有限来源ID单独核本批六Cash/四PaymentLink/预收Entries/更正和两个ServiceOrder/TenderSlice、以及新增三InvoiceResult。背景完整保留，不冒充本轮新事实或另项通过。Group本金、会员权益、库存及往来分别核原来源，不跨表相加。

## 全原行保护与边界

每动作先完成原登录再取全业务基线，登录自身Audit不混入只读守卫。只允许本轮有限Invoice Case及源A Case的version/updated_at、对应Tasks、原FlowEvent/Audit/FlowReceipt、三组Immutable InvoiceApplication/Approval/Result、所需File/私有对象/扫描metadata；sourceA收费、付款关联、Task原收款事实、ServiceOrder/Quote/Tender、全部Cash/FinanceAdvance/Entries/Statement及所有会员/库存在开票链均不变。Case金额/业务日/客户/归属/原状态及无关字段不能随便放宽。

对账只允许本轮Case/Task、ReconciliationBatch有限状态/CAS/提交封存者/时间、Issue有限resolved字段、ReconciliationEvent/Receipt和原FlowEvent/Audit及本批文件新增。ReconciliationBatch冻结case_id/start/end/revision/previous_id/prepared_by/reason/digest/manifest/summary不允许覆盖；Issue原line_key/difference/reason/opened_by/evidence_id不允许覆盖。任何旧票据、源现金、库存、会员、他店、旧对账批次及清算表全行保护，无旧行删除，无“派生”全表豁免。Read/CSV没有写入，原下载/登录/任务转交分别精确容许其原唯一审计/事件事实。

未来checkpoint建议保留 finance_followon_sources={customer_id,source_case_id,blue_case_ids,red_case_id,invoice_result_ids,reconciliation_batch_ids,reconciliation_case_ids,issue_id,period,definition_version,cash_definition_version}，另存每版本完整manifest/summary/digest、真实CSV元信息、原Task/Event/Receipt及有限事实。消费源时仍需同轮场景完整passed和指纹一致，未执行不产生tested/pass状态。后续不能据内部InvoiceResult声称税务实开或真钱退款。

当前页面/API/模型合同存在，没有发现须为这条计划新增业务入口的确定缺口。前200条限制、经营主体冻结、期间已有批次、默认Task接手与时间边界是实际执行需重验条件；原UI简洁度、布局、响应等待、SQLite并发及真实拒绝尚无本批运行结论。合成外部票据仅验证内部协同与保存，真实税务平台、银行/客户签字、病毒扫描、员工试用、PostgreSQL、跨店及193完整验收保持pending/false。源不足或原拒绝必须失败留证，不以空查询、静态hash或导航补足数量。

## 本次只读来源SHA256

原需求表source ddf297678e5d6d35e1dbfffc5c232c3d56748934eb22b58bbb9f9d5343689aae；requirements_manifest 19840f4fc5fd816d94ea35a4602a31bde4674105e44621eeb4cfe42bdad27a1f；business_acceptance_catalog eeea5ea2088ac932fe9f725ef1d4bd68073507bd23f695df360ef0036ba8a3ff。原标题HK095「月结查询」和HK097「开发票」已实际逐项对照，不能把group「月结处理」当原标题。

冻结直接前序 finance_business.py 71152135cc82695572f57cd098096dfd4dd03cdae8212567b528c7a98c006763；原财务scope f7c9c637595f0af8fa79310b07d603b1f0c8945190eb013f9f5a9e08c4610ffc。

invoice_api.py 27d231f11dc2e4fe802bfc328bf52d73cf356510d690d2b7f1f08dd9a4c7d378；invoice_service.py fab098e8a12fce8b644fdca82bfed39c5c575c7dbfe2bc39c34f538329e97dac；invoice_models.py 2973ea661f75337f230f46c4ac4cf94cde907906bbc6fc8e705798cf962e501c；web/invoices.js d8956df032256b4764f3ded0526bd2cbd421cc8e491b37d8106aab2561b74ca9。

reconciliation_api.py 06975c883b2152a1de05e14a9aedfa2ca22a3cad80246ffd1c6720431194d63a；reconciliation_service.py 4be23e53df58dc656544ae514f6c4c930c549c055508aaf00b507a55e49b92f5；reconciliation_models.py 4061e69ac63307c6da1545a8946e05ffc30cf34fad36b19065cc552dd3fc4bb4；reconciliation_v13.py 0d32fea5794c711dad5bcf0d43ec56558d0d4edd453c230f0dcbf3e1418b41ca；web/reconciliation.js e82e59ff56b0c58a2b0ae4b0e4d59feae84e0528348f916eb4f2e24056a850c2。本页为研究候选，根登记精确补丁后方可新增脚本。
