# Reviewed short writers：独立审阅 B

日期：2026-10-01。复审 PATCH-M8-1-REVIEWED-SHORT-WRITERS-01 指定范围；未导入 app、启动应用/浏览器/测试或读取数据库。唯一写入为本记录。

## 输入与范围

清单：`C:\Users\tiefu\.codex\HuaKangOS-agent-validation\runtime-v1\browser-click\launches\reviewed-short-writers-127.json`。
清单 SHA-256：`f368df1018df2a4eb2f662ceba3a859f1a78badc75e1f1b10ad36d847f2cc521`。
原文件：同一 launches 下 `short-writers-before-20261001/<file>`；后文件：当前 `E:/HuaKangOS/<file>`。
按41个唯一文件路径排序后的第15–28个，合计14文件、44个同步原写入口；42个从 get_db 切换，reconciliation 的 create/batch_action 两个已使用 get_write_db。

## 审阅结论

在本范围未发现确定的机械接线缺陷。全部44个入口的 db 依赖均为 Depends(get_write_db)，并先于 user=Depends(get_user)；没有异步 handler 或 Await。
逐行比较确认只有原 .db 导入增加 get_write_db、42个指定函数的 db 默认依赖替换。恢复这两类差异后整模块 AST 与原版一致，其他签名顺序、函数体、装饰器、schema、权限/门店、状态/CAS、request_id、金额和原事务调用均未改变；普通读取未被本批替换。
逐项阅读44个原 handler 及其真实 service 委托，确认是业务/管理写入入口：create/save、原动作 command、配置发布/批准、核销/退款、提醒生成/来源同步与原单修改；不是只因 POST 方法而推断写入。服务原 add/flush/commit 或受控 _execute/execute/_command 写入链保持。原拒绝、重复请求和空生成可能无业务追加，这不改变原写入合同。

## 逐文件原/后指纹

函数名后 @ 为当前源码一基行号；指纹使用未归一化原始文件字节。

| 排序 | 文件 | 函数数 / 新替换数 | 原写入口 | 原 SHA-256 | 后 SHA-256 |
| --- | --- | --- | --- | --- | --- |
| 15 | `app/master_api.py` | 2 / 2 | `add_master@179`, `update_master@184` | `ab8e6fdc489cc72a16210cf0a78a27529235a3bf95961051f545c25841a23848` | `cc6ba39643c05c88aafcd0ba9ded31ea5a3f9d9caa82358aad40be55bff017fe` |
| 16 | `app/member_pricing_api.py` | 2 / 2 | `command@82`, `create@77` | `a3580a37f5ef6ea6c5ebfbe1c772b66d005f9dc923892f4882b98325b9e5fbcc` | `90ed0cbee66a4c018cc84e5f33445275c94c2baf45bcfad805ab679012a452b9` |
| 17 | `app/membership_api.py` | 3 / 3 | `command@78`, `create@72`, `rule@62` | `3ec9054048827a4685f5fd13d6c23191c15d7184044674d1868a643e36645a8a` | `44c0b7f7cfbcc5a33dfbff677b5d2f99e16aa899505eb44da4079ede2aeb389f` |
| 18 | `app/observation_corrections_api.py` | 4 / 4 | `command@62`, `create@58`, `generate@70`, `sync@73` | `38e450a63168457f2e86d7e2a9f774e2fb9e11224873d5a35f0850f91a4c3a25` | `4e63464bc4909afeaf7c4ce94e4f7e8a1b2a5e95f3b270b07358d1461b7e3091` |
| 19 | `app/procurement_api.py` | 2 / 2 | `command@70`, `create@60` | `5d3a1a2a2deaf9662723a18197ed9a2e9a0be1194aed1ad094276bf29b0986bf` | `a2283bb1995b8ec5b99f05164b6da2db7774a7802ed3ca440ceb8f2eeb1ceff5` |
| 20 | `app/recharge_bundle_api.py` | 3 / 3 | `command@71`, `create@67`, `create_rule@57` | `096e9d476f4927d4706f61c1f7096ab74fc19e318826473cd93b4691562a4425` | `947a51581ab3c25e29f795befa7326a77d10ab34c01cf038a4d3777c3895589a` |
| 21 | `app/reconciliation_api.py` | 4 / 2 | `batch_action@62`, `clearing_action@75`, `clearing_create@72`, `create@59` | `680a55e61551d2aae92b03058a675c0d4ea25d782e28da2132d71a20038456a9` | `d3262492b8e368b6c88b13a5fed684c16a017631745d83b8ba6142c63308f7bd` |
| 22 | `app/repair_api.py` | 2 / 2 | `command@95`, `create@89` | `f0ae5fc9d4431e77500352f906716da7732429aee55da342476f6189f14ff077` | `4fc76602c459c0503a057a5a8364fdf9b27701c08d5289c9cf81fa8892e99656` |
| 23 | `app/repair_package_api.py` | 9 / 9 | `capture@111`, `decision@84`, `mapping@86`, `material_return@113`, `purchase@93`, `purchase_action@95`, `quote@102`, `refund_action@100`, `rule@82` | `b2e50b8c61d859a2ecaee04fdc6ab09713650bd2de5b4c4aa3bfcf0d1bf14dc7` | `2450de75455e31f0e6859ce75c66ac52becfaaed15f748f055f678c0fb4deb17` |
| 24 | `app/retail_api.py` | 2 / 2 | `command@87`, `create@81` | `677eb064326fa241a53ddf90bdc9ef40f1d61e898a869bd786c3b981eff4f526` | `7fd6f1dc576f5e6a7619fd658ffef7d0d996b03d92fb8a9f0736d79794fbe764` |
| 25 | `app/retail_bundle_api.py` | 2 / 2 | `publish@49`, `sale@55` | `c1a559e49c90258c1948e712d1f4eafa2ee8fa59eb8e8a949abbcb7a0d485225` | `b9da09fb723674edd2e2767449d639ebb6785ab507eec1e3a2fcadbe1c68efee` |
| 26 | `app/retail_group_api.py` | 3 / 3 | `action@86`, `create_rule@91`, `rule_action@111` | `02ed47023749cac086163a768d2ec8ac2eb51dced8ed4450466b3ead42214d54` | `0a2142583d51ce08d18945e9c27e0c0ba718053c5ca2cb1cb1a6d309647242d4` |
| 27 | `app/rework_extension_api.py` | 4 / 4 | `accept@53`, `decide@50`, `propose@45`, `quote@56` | `d51d60137b0d2a6673744730bf918f407a3760318647d1b8030d2a3e92f7bcd3` | `224b83db315d06d1845917a43dd07c3cbec41b15ad4892f72ebf82b73aadaab9` |
| 28 | `app/sales_quote_api.py` | 2 / 2 | `create@38`, `revise@50` | `8a4311c49643353a8108879b0a622d0967ffaf9634ecc21666373c930184b95a` | `545847583c131798d9ed7ffc3805d4c22b1d57267c3222ed4b1035ae31035b6c` |

## 实际写入委托核对

- master：master_data.save_master；member_pricing：create_rule/command；membership：create_rule/create_order/command。
- observation_corrections：create/command/generate_reminders；sync 的局部 apply 调用 sync_insurance_basis，最终经原 _execute 保存原来源同步回执与失效事实。
- procurement：create/command；recharge_bundle：create_rule/create_order/command；reconciliation：create_batch/batch_command/create_clearing/clearing_command。
- repair：create/command；repair_package：create_rule/decide_rule/map_component/create_purchase/purchase_action/refund_request/refund_action/capture；其 quote 经原 repair_service.command，return-material 经 repair_package_aftercare.return_material。
- retail：create/command；retail_bundle：create_rule/create_sale；retail_group：command、retail_group_rules.create/command。
- rework_extension：propose/decide/request_create；quote 经原 repair_service.command；sales_quote：create/propose。

## 有限证据与待测边界

静态核对：14文件 AST 解析；44函数依赖/顺序/完整路由检查；全模块还原差异 AST 等价；逐行允许差异核对；原/后 SHA-256；原 service 写入委托人工审阅。没有执行原业务，没有写通过成绩。
本报告不代替其余27文件/83入口的独立审阅，也不单独证明 app/db.py OptionEngine 机制、SQLite 并发、实际 FastAPI 依赖执行/同 Session、PostgreSQL 或浏览器运行结果。这些属于根的共同依赖审阅与新鲜隔离复验；原真实失败证据保留。
