# 开票与期间核账两项候选交接

2026-10-01，test_inventory；范围 PATCH-M8-4-BUSINESS-193-15，冻结设计 finance-followon-scope.md SHA256 60c28fc3a6bb6d1791475a66a049ecb3e5dc928e3c77b57b7bba17a22dc8ac71。只新增本页及 tests/browser_click/finance_followon_business.py；其余生产、fixture、注册/runner/计划只读，未导入app、启动应用或运行浏览器。

候选 SCENARIO 为 finance-followon-hk095-097，函数 finance_followon_business，原生导出 FINANCE_FOLLOWON_SCENARIOS，预算600秒。只提交 HK-095-business「月结查询」、HK-097-business「开发票」两个原目录check，不把蓝/红/差异/重算拆成新需求，不重复HK096。当前未注册、未执行，全部运行成绩仍为待测；根短审/独立短审及接线后由唯一真实镜像运行判断。

## 实际前序与顺序

必须读取同轮 runner expected_scenarios 中已passed的 finance-hk087-090-091-093-096，固定该目录 business-checkpoint.json；检查点complete/passed、所有原check、原193目录SHA、五路径provenance与当前镜像/脚本指纹均一致。不接受静态设计、旧运行、fixture成果或demo非空数据。根随后报告完整28场景退出0、财务五项首次实际通过（源1597eb7b／脚本7cc1267d，稳定提交8993ca8）；这是根报告的另一镜像历史事实，本候选没有自行读取其证据，也不能跨轮继承。新镜像同轮源缺失时仍停止。

限定使用 finance_sources 的本客户、本账户、两6000分服务原单A/B、两Quote、原预收/更正/抵用、两月结批次、四PaymentLink及原退款ID。SELECT重验真实完成服务与逐原款、原Advance初10000/纠正-1000/余额占额0；六Cash方向金额依次为10000入、10000冲正出、9000正确入、3000入、5000入、5000退款出，原Entry接收10000/纠正-1000/抵用-4000/退款-5000。0新角色/fixture，复用随机finance与另一manager的本店真实UserStore。

原UI先建非空核账版本1，期间从这些有限来源业务日期和原catalog.today确定，旧同期间存在即失败；不改日期躲来源。接着A蓝票申请60元→不同manager原批准→finance原外部提交→明确合成票面58元先difference再record→manager独立结果差异复核。原蓝票关联红8元，批准/提交/实际红票登记；原A再新蓝10元并批准/提交/实际登记，5800-800+1000净6000，三独立原InvoiceResult和原蓝红链接保留，发票不写现金或会员账。

版本1因三票据实际结果改变来源，finance真实submit必须409且全业务不变，原关闭/明确放弃后重算版本2。版本2包含本次有限票据、原款和服务事实；实际UI在原Cash条目登记差额0的核对事项，逐真实更正与六原款核对后resolve，凭据与原Issue内容保留，不用说明补造账务。finance提交，另一manager独立封存。manager明确复开版本3，未变业务的manifest/summary/digest等于已封存2，再财务提交/独立manager封存；版本2全部批次列原样、版本1冻结内容不变。

HK097及HK095各自完整check仅在对应真实操作链结束后记运行passed；发生中途失败时当前原项failed，已执行但未结束的另一项partial，未运行保留not_tested，不把取消或证据可序列化当通过。最终全193/人工/生产仍false或pending。

## 保护及真实文件

每个写动作完成原登录后取全原业务快照；15个有限原表的追加数、本人actor/store/case及旧行/列逐一守卫，所有其他表不变。不排除整表audit，不覆盖Cash、会员本金/权益、库存、原服务/报价/分配、预收或旧冻结版本。Invoice三表完全追加且immutable；原source A Case只允version/updated_at，Invoice自身只有submit可改external_reference data；ReconciliationBatch冻结period/revision/previous/manifest/summary/digest不得覆盖，Issue原来源/差额/理由/原件不得改。

本人Task交接等待真实genericCase GET和原h1渲染，再等待唯一assign按钮可见/可用；原AssignInput只version/assignee_id/reason，没有伪造request_id。Invoice动作双CAS为自身Case和当前source版本；对账双CAS为batch和Case，resolve另核Issue版本。原回执完整参数digest、本人事件/唯一审计、原状态及Task完成分别核。reconciliation原服务没有Invoice同款_task守卫，不虚构规则，实际核原任务并通过原UI明确交接。

每事实使用不同外部合成TXT、明确本单evidence/invoice类别，原UI上传。BLOB实际字节只在内存与选中文件比较；检查点只File metadata/size/SHA，不输出正文bytes、base64、密码hash或会话hash。当前合成入口blob储存、structure_only，不声称ClamAV、私有对象储存或真实税务/银行/客户签字通过。

三张实际票据都实际点原下载按钮，保存浏览器下载字节与DB BLOB/SHA/长度一致，精确一条本人download原审计，其余旧行不变。版本2、版本3和复开后旧封存2都下载原完整CSV；不调用response.body、不额外HTTP取下载。utf-8-sig/csv解析与原9列表头、完整manifest每行/key/basis/case/整数分/千分位/权益单位/JSON及公式前缀转义逐项一致。reconciliation原export没有写审计，下载前后全业务快照相同。

完整CSV按定义7排除被纠正原误记与账务冲正，保留全部六源用于追溯；本批有效入17000/出5000/净12000，与A/B服务总收费12000守恒。全店可能另有本轮或demo背景，不把全店摘要硬等12000；完整manifest重算全店现金摘要，并单独按有限ID核本批。Cash、票据、资金关联、会员和库存不能相加；原票冲红8不代表退款8。

## 待验条件及输出

原页面只展示前200个manifest条目；本轮Cash不在此真实UI范围则硬失败并留具体条件，不API/DOM注入代办。期间已存在、主体策略、原Task接手、运行跨业务日、真实权限/409、布局与等待、600秒预算仍需实际镜像验证。真实税控、银行、ClamAV/private_local、跨店/旧定义1–21、员工体验、PG/Linux、模型及193全部业务验收不由这两项替代。

未来 finance_followon_sources 保留 customer_id/source_case_id/blue_case_ids/red_case_id/invoice_result_ids/reconciliation_batch_ids/reconciliation_case_ids/issue_id/period/definition_version/cash_definition_version；完整三个版本事实、回执、事件、保护、实际CSV与票据下载均在同轮外部证据。后继需当前场景完整passed才能消费，不从旧库扫描。

静态检查已完成：候选AST，已引用helper符号，15原模型表映射、两原标题/check绑定、5个SELECT-only DB调用及有限f-string白名单、零app导入、零下载response.body、空白检查。静态来源检索助手先遇到BOM/编码别名读取错误，已改为有限五个原模型文件的utf-8-sig读取并完整通过；没有改原生产文件或运行app。这些只证明可静态审阅，不是两个check实测成绩。

实际运行和独立审阅由根安排；源码冻结SHA由本页完成后的交接消息记录，未来结果须追加同轮真实证据，不覆盖本次未运行事实。
