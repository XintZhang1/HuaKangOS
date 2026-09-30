# 任务：原需求表与真实入口覆盖清单

**任务 id 与负责人**：requirements-coverage；子代理 test_inventory，向 browser-click 负责人报告。

**依据与范围**：PATCH-M8-4-REQUIREMENTS-CLICK-01。只维护 `tests/browser_click/requirements_manifest.json` 与本记录；点击执行及外部结果由负责人和 browser-scenarios 任务维护。

**来源核验**：桌面 `全新搭建：功能需求表.docx` 与仓库 `docs/原始功能需求表.docx` 字节相同，SHA256 为 `ddf297678e5d6d35e1dbfffc5c232c3d56748934eb22b58bbb9f9d5343689aae`。只读 OOXML 提取的十模块、193 项，与 `docs/requirements.json`、`docs/workflow-source/coverage.json` 逐项一致；111 条源工作流与发布 `web/workflow-guides.json` 的名称、分类、需求关系、入口及岗位一致。完整源核验报告保留在仓库外 `runtime-v1/browser-click/requirements-20260930/requirements-source.json`，未改原文档。

**交付与结构**：清单保留原 `HK-001` 至 `HK-193` 编号、模块、分组、名称、工作流关系和入口。193 项通过 `target_routes` 关联70个原页面目标；111条工作流保留 `category`、`requirement_ids` 和完整 `entry`。目标保留原路由、带 `#` 的导航目标及反向关系。源未声明 `form_ref`，不猜填。全局 `execution_status=unexecuted`、`business_accepted=false`，不继承历史验收。

**分层验证决定**：实际浏览器另存需求搜索、指引展示、原人工页面及具体业务动作的证据；入口去重不扩大业务验收范围。当前九组关键场景中，客户确认对应 HK-098 客户档案的新增子动作；接待跟进对应 HK-002 展厅接待分派的第一原单确认子动作，第二原单只准备。夹具创建的 HK-001 接待及未执行的 HK-006 回访不计业务实测。HK-117 会员信息、HK-126 套餐购买的补充 GET 详情核查仅为受控读取，不能算会员办理或购买通过。

**清单生成检查（历史阶段）**：以当前发布源生成；核对源哈希、193项身份与关系、111条工作流、10模块、70去重入口，无缺项或重复编号。JSON解析和关系完整性检查通过；当时仅生成清单，未导入 app、启动服务或执行点击。后续负责人使用同一外部源码/脚本快照完成四组覆盖场景，07轮实际结果见下。

**交付指纹**：HEAD `71276037dc920069d6d5fa77311b0a7fdbbc3773`；清单 SHA256 `19840f4fc5fd816d94ea35a4602a31bde4674105e44621eeb4cfe42bdad27a1f`。HEAD 含未提交本轮改动，实际运行仍以隔离入口记录的全源/脚本指纹为准。

**原门槛**：本清单不是193项业务验收。资金、库存、退款、调拨、月结、真实模型、PostgreSQL与员工条件仍按原计划留待相应实测，不启用生产开关。

**最终分层覆盖（2026-09-30）**：已只读核对 `runtime-v1/browser-click/automatic-20260930-07/evidence/requirements-coverage.json`、四组 checkpoint、`browser-click-report.json`、`run-summary.json` 和 `provenance.json`。本轮13组预期/注册/执行/通过一致，退出码0，`complete=true`、`passed=true`。原表 SHA256、清单 SHA256 与生成阶段记录一致；生产源码 SHA256 `0ade3e7a781de93a963bc341242488abf386ee7d68bed55178838cc815e22f7a`，脚本 SHA256 `e4265ebdc23ce75c2d1767e272da5bc37167221f380d0c14d4857735eacff921`，快照复制前后稳定。

实际覆盖193项编号搜索、111篇指引（含10分类，共121次分类/文章检查）、70个去重原页面、9个原空表单打开/聚焦后取消；每组完整注册并执行，无省略。193项均记录帮助与关联页面显示已检查，原页面及空表单组均核对原业务无变化。9个表单为售前接待、整车采购、维修工单、物资采购、期间对账、客户档案、会员识别、供应商及员工管理，均未提交业务。静态清单仍保持 `unexecuted`，本轮实际等级仅在外部报告中记录。

外部逐项报告仅将 HK-098 客户新增一次确认/历史无重复、HK-002 第一接待分派确认记为通过的业务子动作；第二接待仅准备，全部193项的完整业务流程仍未测。`business_subactions_tested=2`、`business_flow_tested=0`、`business_acceptance=false`、`full_flow_tested=false`、`data_source_acceptance=false`。`visit-activity`、`vehicle-period`、`warehouse-period`、`procurement-cohort` 四页面保留来源不完整提示；页面显示通过不等于来源完整或经营数据验收。人工统一评价仍列 pending，员工效率未测。

退出短写事务另有外部 auth 探针和07轮慢查询退出通过记录，不扩大原193项业务覆盖。历史源核验报告、旧失败及原验收门槛保持；本次只读更新任务记录，未重新执行测试。

**随后主代理人工审阅结果（独立证据）**：manual02与automatic07生产/脚本指纹完全相同，实际IAB销售登录、三宽度、手机准备客户→单次确认→刷新→原客户页→退出已执行，数据库对应客户恰一条。六项人工评分3/3/3/4/3/3，详见 `V/browser-click/manual-20260930-02/evidence/manual-review.json` 和v2浏览器检查点；自动报告自身的pending保持当时事实，不改写原件。开发者审阅不替代员工试用或效率。
