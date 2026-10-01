# 应收维修来源回执规范化独立审阅

2026-10-01，M8.1 同一浏览器交付；仅新增本报告。只读普通维修/返修/套餐 API、服务、前端与原浏览器脚本及仓库外 before 原字节，解析 AST；未修改生产源码、测试、runner或原证据，未导入 app/Pydantic 模型、执行脚本/SQL/浏览器或读取数据库/凭据。本结论是静态候选审阅，不是 rcv11/full53 的动态 passed。

## 已确认原因及有限修复

原 `tests/browser_click/receivables_business.py:repair_command` 对普通 `/api/repair-orders/{id}/actions/quote` 的回执重算额外补 `member_pricing=None`。普通 Quote 校验确实会先把该默认值写入 model_dump，但 `app/repair_service.py:399` 在 `_execute` 前明确删除值为None的 member_pricing。服务器实际 request digest 因而没有这个key；原测试 helper却含这个key，精确 JSON摘要必然不同。这是测试规范化与现有服务合同不一致，不能以生产摘要校验放宽或新增返修字段解决。

根当前修复仅对该函数 quote 分支：不再注入 member_pricing=None，并在实际values该值为None时只删除此key；有真实非空会员选择时保留它。继续补/保留原普通 Quote默认 `purpose='service'`、`discount_cents=0`、`retained_amount_cents=None` 和普通 Line的 `line_key=None`，原request值通过原后展开覆盖默认。allocate分支的 payer_id=None/payer_name空串、原 expect_response、真实 R.command 提交、返回值和 MF.flow_receipt 调用完全保留。没有补 source_line_id、charge_scope 或 package_retained。

已独立读 before `V/browser-click/launches/receivables-receipt-before-20261001.py`，SHA256 `e9f7149de607303ac5ceea00c83d89f9a9f414c2244bae9fc37d50141abf701f`。before函数701–713 SHA `99eba308ade9918f6767131b581dee0a768a97bee1550826187780b2bec021d4`；current函数701–715 SHA `453ef6f1c298858b98136725aa9b44c3ecd3b409b9ea0cc99c9f5e597569e5fe`。按上述唯一两处文本变化正向替换，当前函数原文完全相同；整文件原文也仅这一替换，函数外全部 AST相同。当前脚本 SHA256 `f71347c110a46a36834e417149e538c18eebc877fefe6edc7e8bbcdcab9ed7c9`。未执行这份脚本或断言。

## 普通、返修及套餐边界

静态解析 app 下409份 Python 文件，补充全app文字引用检索。`repair_api.py:77` 只有一次 SCHEMAS赋值，其 quote精确绑定普通 Quote；没有 `.update`、quote下标重绑或其它app模块导入该SCHEMAS再修改的路径。跨模块实际 import只见 rework_extension_api/repair_package_api继承 Line/Quote，以及main导入router；其它API的同名SCHEMAS属于各自模块，不合并为维修 schema。

- 普通 `repair_api.Line:34` 只声明 kind/source_id/line_key/quantity_milli/unit_price_cents；`Quote:40` 声明 member_pricing/purpose/lines/discount_cents/retained_amount_cents及继承reason。Strict的 extra='forbid'保留。普通路由96–100仅按 SCHEMAS.get(action) 校验/JSON model_dump后调用原service，不增加返修或套餐字段。
- `ScopeLine/ScopeQuote` 只在 `rework_extension_api.py:35–38` 声明，唯一使用是57行显式 `POST /api/rework-extensions/orders/{key}/quote`；它要求 charge_scope并允许 source_line_id。没有替换普通 Quote、Line或 SCHEMAS。
- `PackageLine/PackageQuote` 在 `repair_package_api.py:56–66` 单独声明，package_retained仅属显式 `POST /api/repair-packages/orders/{key}/quote`。该路由104–109保留套餐版本配对及删除null charge_scope/source_line_id的原规则。普通报价不能从此继承 package_retained默认值。
- `rework_extension_service.prepare_quote:267–271` 对没有extension的普通/旧内部单，只要lines出现charge_scope或source_line_id就拒绝；即便值为None也不能伪加该字段。这层守卫保持原文。

实际前端是 `web/repair.js`，仓库没有 `web/repairs.js`。`repairQuoteDialog:51–54` 在已有套餐/明确rework_extension时分流到各自专用dialog，其余普通send绑定 `/api/repair-orders/${row.id}/actions/quote`。普通行63仅发送真实kind/source/数量/价格；只有原已开工行真实line_key存在时才发送line_key。普通64发送 purpose='service'/reason/discount/lines；`web/memberpricing.js:28` 在未选会员价格时返回 `{}`，有明确选择时才返回 member_pricing对象。普通前端没有source_line_id或package_retained。显式 `web/reworkextensions.js:32/40` 才发送返修route及责任字段；套餐停止保留量由 `web/repairpackages.js:41` 发往套餐route。

## 原摘要与事实保护

`repair_service.command:399/477` 先删除空会员选择，再以实际 `{id,version,values}` 调 `_execute`；`_execute:154–160` 固定operation为 `repair_v3_+action`，调用 flow.request_digest，沿原prior_request本人/摘要守卫保存唯一回执并commit。工单即使是flow_version4，原事件名可以是repair_v4，回执operation仍按原 `_execute` 的repair_v3；不能擅改测试operation为repair_v4。

`flow_engine.request_digest:963` 与 `member_followon_business.flow_receipt:718–723` 原精确JSON规范同为 operation/payload、sort_keys=true、ensure_ascii=false、separators逗号/冒号；后者继续校验唯一request_key、actor_id、store_id=1、case_id和完整digest。建议只采用当前有限canonical修复，不删除digest断言、不降为“有一条receipt”、不丢版本/原values或全行保护、不换request_id重放以规避已提交结果。

源码指纹（本次只读字节）：

| 文件 | SHA256 |
|---|---|
| app/repair_api.py | `4fc76602c459c0503a057a5a8364fdf9b27701c08d5289c9cf81fa8892e99656` |
| app/repair_service.py | `ab51e9b2874b5f0bb44750c15c71d4c0622f4ff6130f27a0ea7da2db45cab4c4` |
| app/rework_extension_api.py | `224b83db315d06d1845917a43dd07c3cbec41b15ad4892f72ebf82b73aadaab9` |
| app/repair_package_api.py | `2450de75455e31f0e6859ce75c66ac52becfaaed15f748f055f678c0fb4deb17` |
| app/flow_engine.py | `f654ffa77e82f517f77cfc69f6937e2e2c2527c23874d87f937f7ab18e0bbaca` |
| web/repair.js | `91af2e2557ea637f6baab7db35699bfe4576cd63f2a98623014408fec8b51707` |
| web/memberpricing.js | `6e1cc9ea0308ccedc6c87dd5dd01c74bcf70cc419ac3f7c86bec2c1642ad8536` |
| tests/browser_click/member_followon_business.py | `2c8777cff4246b549c88be55cd7a7a95532ecb20493a497ac10b65fcb142fdb2` |

当前最新候选字节符合原普通报价规范化，静态未发现需要扩大生产或schema范围的缺口；原浏览器候选、失败和后续全量真实执行结果仍由根分别保留，不能由本报告替代。
