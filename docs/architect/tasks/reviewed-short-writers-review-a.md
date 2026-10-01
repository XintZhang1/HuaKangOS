# Reviewed short writers：独立审阅 A

2026-10-01，M8.1，针对 `PATCH-M8-1-REVIEWED-SHORT-WRITERS-01` 的静态编码审阅。审阅者 `/root/click_scenarios`。当前 HEAD `8993ca8c755194a42a48e7323fe355e80c6bf9ae`；使用当前工作树实际字节，未用 HEAD 内容代替未提交源码。

## 精确集合及结论

依据外部 `C:/Users/tiefu/.codex/HuaKangOS-agent-validation/runtime-v1/browser-click/launches/reviewed-short-writers-127.json`，SHA256 `f368df1018df2a4eb2f662ceba3a859f1a78badc75e1f1b10ad36d847f2cc521`。按唯一文件名排序取第 1–14 个，与外部 `launches/short-writers-before-20261001/<file>` 保存的原字节逐一比较。

本组 14 文件、46 个登记函数：45 个 `Depends(get_db)` 改为 `Depends(get_write_db)`，13 个文件补导入；`flow_api.generate` 原已使用 `get_write_db`，本次保持。没有发现超出登记范围的变化或确定静态阻断，允许进入新隔离目录实际点击复验。

| 顺序 / 文件 | 登记函数数及函数 | 原 SHA256 | 当前 SHA256 |
|---|---|---|---|
| 1 `app/addon_api.py` | 2：`command`, `create` | `eb19f09aff981f4a486bc0ee010acdf07f1e7c7c4d0f40c3fb13bb6156f3f4ce` | `5ece6068820a3a53449d353cc939e6f8f085fc26ecd2d36947c7cf0c0c1e18ef` |
| 2 `app/aftercare_api.py` | 2：`command`, `create` | `f5c70310d72c8a6ceecff7ab0594eb7a7bfff88c3aedc7468a5fe5f56b8488f1` | `94dd1df34ad026680b090e16087a3c494569ff96bccfb0613ead9a3872ae0809` |
| 3 `app/business_finance_api.py` | 2：`command`, `create` | `5d582589f56b8b9dbe047aafe1c9a496230b7a0f75b442151023b234ad28ccd5` | `b31e508a0dab071fb4f6f865226f8170a3fc0ca8788b0697a00070f45a0c00e4` |
| 4 `app/claims_api.py` | 2：`command`, `create` | `a5bd8bac5040e8c3eef07b447c95ecd6a9c37b58e66d50b50e52f0182a345162` | `eac13e54e3c55a4b2c7a56bd5b4315ac043fcf223f474afbd2a8d5b7bc2db4d0` |
| 5 `app/customer_service_api.py` | 13：`action`, `edit_vehicle`, `generate`, `link_history`, `new_case`, `new_grant`, `new_rule`, `new_vehicle`, `observation`, `questionnaire_propose`, `questionnaire_review`, `revoke`, `update_rule` | `b83bb4c354dba5ecddf58c2d76c7f7cf2811e657918e89c8fd8062469f6c241d` | `280164918803c8eb3421d4c60f4c4165115fe2dc96600e20f2918359a2278d8b` |
| 6 `app/dictionary_api.py` | 2：`create`, `update` | `12e4619bc117c6390946eb3acec55adde6e1d826d89216306f026e3b71901f66` | `4de4fdf6232c70f9122797017cfd00ca64eeb096e09dbc335abe7f469ce37fc4` |
| 7 `app/dossier_grant_api.py` | 2：`action`, `propose` | `dc3719ff796a7b0a9323536b6a00cb5ccde6b6a28ed49e6f87a8a42fc2cccfee` | `a8ec3e4c56cc36d1c3dd8069c7f4dcbcd5a3691f1de2e34a31505d60692dd8b6` |
| 8 `app/escalation_api.py` | 1：`submit` | `b2aa3cafba521b934bad0960f5812b50cc2dba66c10f69504eb13db8cac6b056` | `bdee85e635348848fe71629694b50b7d35bce7b7133e25d37570888c678238b3` |
| 9 `app/flow_api.py` | 6：`act`, `add_master`, `assign_task`, `create_case`, `edit_master`, `generate` | `b453a1088e324b8b7f79f1c9c14f1c24f63970ece00df3c827e9af38d116df8e` | `e6b2a3b8442da3bcef3b45d701e0304930ff5127f5fca22a613e00c43b9139c3` |
| 10 `app/gate_visit_api.py` | 5：`command`, `correct`, `create`, `repair_exit`, `review` | `01691351391143f2b9c9fd7563fdf7ce3f047f84319e8e9ed4e53250f8cd35f0` | `6a94b9e95f3ef33bb9a2761d4287a82014eb7dc55a08404727bf57c1a88ca486` |
| 11 `app/group_api.py` | 3：`issue_member`, `link_identity`, `member_action` | `4e3edd8c5d9ac493c77b9d9fbd9ceaabbf05fc826fe34ef0fc8b8cfe1c0c1794` | `ac0cdb730810976e95b389eb4a806355f3b6f0bdb814f35f60a7e722029930e3` |
| 12 `app/group_benefits_api.py` | 2：`command`, `create_rule` | `632859947654ac3313995cabd87e28f2db3c53a2897b44ca5751202bb6eee974` | `64798cd79a8e88e11a80be7a5918b084834598737d1f4b2da50161cce282ccba` |
| 13 `app/insurance_api.py` | 2：`command`, `create` | `c9c1910f48c192080448d245aeec334c0db98e687409bb1ff637386dd25bc1f7` | `5f89b03b8f7d7ac768b4075eedaf8b23e708cf6ebb114fee30510859722915df` |
| 14 `app/invoice_api.py` | 2：`action`, `create` | `27d231f11dc2e4fe802bfc328bf52d73cf356510d690d2b7f1f08dd9a4c7d378` | `188b72cb7e88fc3217d4e2522d24adbfa3706577971344923280c127a06a0f88` |

## 实际核对内容

原后 28 个模块均可由标准库 AST 解析。对新增导入和精确 `db` 默认依赖反向规范化后，整模块 AST 与原模块一致；另外逐行保留行结束符比较，只有登记导入和登记函数签名行发生变化，45 个签名均是原 `Depends(get_db)` 的一次字面替换。全部函数体、装饰器、schema、其余函数与模块原文保持；本组没有参数重排。

46 个处理函数均为同步 `def`，没有 `await`、`yield` 或 `yield from`。原方法和完整路径均与清单逐项相符。每个当前函数的 `db=Depends(get_write_db)` 均位于 `user=Depends(get_user)` 前，14 个原 `APIRouter` 与46个装饰器均没有更早的认证依赖；补读 `app/main.py` 的 `include_router` 也未发现提前认证依赖。

逐项追踪原实际写服务：加装、售后、财务、核赔、保险和发票创建/动作均进入原事务执行器；客服的车辆、观察、历史关联、服务、规则、授权和问卷处理均实际建立或变更原记录并保存回执。客服 `generate` 会委托 `observation_corrections_service.generate_reminders` 创建原服务、基准、替换关系和回执，属于同步实际写入口，不是查询或外发通知。字典创建/更新进入原 `save` 和 `master_data._command`；档案授权建立/决定原授权；升级请求建立原请求并消费 refusal；人工业务的创建、办理、任务转交、主档更新与文件生成均保留实际写入、事件和提交。到店及更正动作保留原进出场事实和评审；集团会员/权益动作保留原身份、会员、规则和流水。本次未把只读函数纳入改动，也未新增助手自动提交能力。

`get_user` 原 `db=Depends(get_db)` 保持。新的 endpoint 写依赖先解析原 `get_db`，其与认证沿默认依赖缓存共享同一请求 Session；不是先认证读后才调用写依赖。补读当前 `app/db.py` 确认 SQLite 写选项在首次 Connection 前放在请求自己的 bind 上，后续同 Session 再开事务仍能携带选项；默认读 Session、全局 Engine/SessionLocal 和 PG 分支保持。`app/db.py` 本身不属于本组14文件的原后字节审阅范围，其独立审阅由根协调。

## 边界及待测

本次只写本审阅文档，没有导入 app、启动服务/浏览器、读取数据库或凭据、运行测试或重放任何业务请求。静态审阅无确定阻断不代表消除了实际 SQLite 竞争，也不代表业务或193项验收通过。原身份/门店、权限、任务、版本、幂等、拒绝、回滚和旧行保护须由新隔离目录同指纹真实点击重新核验；现有失败原件和关闭开关、PG/Linux、真实模型、员工与生产门槛保持。
