# PATCH-M8-1-RECEIPT-CLOSEOUT-01

2026-10-03，当前唯一在办 M8.1；业主要求按计划收口至待人工验收。此补丁只补原故障合同第4/5/6/7/8组的合成装置，不更改业务目标、原确认、权限、事务或回执算法。

允许修改 `tests/browser_click/runtime_receipt_closeout.py`、本补丁和 `docs/architect/tasks/runtime-receipt-closeout.md`。共享 runner/provider/fixture/注册由 root 接线与审阅。所有应用导入、故障安装及运行均只在白名单镜像后的全新外部合成实例；本实施任务不启动验证或服务。

固定故障边界：原确认冻结commit之后、原invoke之前一次传输失败；原Flow201已被服务观察后，仅该确认结果commit一次失败；原Flow201已提交后一次丢返回。故障arm精确绑定真实本人、本店、原session/proposal/WorkItem、digest和完整冻结payload。只SELECT核对真实原单、Task/Event/Audit/RequestReceipt；不造receipt、改SQL、改钟或重放原业务。

回执核对使用原UI和原GET；可靠Flow成功须引用实际request_key/digest/actor/store/case/receipt。门控内部原GET返回时，由原UI开启已保存事项的Grant，让原协调器提交源版本变化，再释放原响应，应得到confirmation_source_changed。只读lookup与后台协调保存分别留证。依赖后继只能根据第一原卡的真实成功准备，仍待员工确认。

后端batch另记HTTP合同：使用本次浏览器真实Cookie与CSRF、本人当前门店和三张原卡digest，首规则失败或真实提交后未知时停止，C仅在本次返回skipped，原卡/WorkItem全字段保持。不称原UI调用了batch端点；前置准备仍由原UI，客户端合同POST次数单列。

异常必须留故障验证失败ledger；固定arm仅消费一次，未实际命中、错误来源、重复目标、未恢复或超时均失败。不扩大完整M8.1、193、独立环境、真实模型、员工或生产结论，四开关默认关闭。

实施/静态审阅及动态终局由任务记录追加；本补丁登记本身不表示任何场景passed。

2026-10-03 修订范围：closeout-contracts-02 两恢复场保留失败，原因是装置的依赖后继缺少原合同 completion_conditions。不变更生产条件算法。每个恢复场允许通过原 UI 先创建该场独立接待，读取其真实 assign Task/case/version/number和本店销售员工事实，由员工原指令明确提供；原首项真实成功后只准备该独立原单的分派。后继完成条件为原 assign Task done，不使用尚不存在的后继 proposal ID，也不把首卡成功误作后继完成。原首项六表追加审计和后继无写入审计从此前置之后计，原 UI 前置单列事实与请求证据。

2026-10-03 第二次前置修订：root 的 core03 已正常收尾（CLI 1、服务 0、forced=false），15 场中 8 通过、7 失败，原报告和失败不改写。原 Task 自动分派按实际待办数量选择合法接待，不能假定创建员工就是任务负责人。仅在本场独立 assign Task 的实际负责人不是创建员工时，允许经理通过原“转交任务”表单明确选择创建员工并填写原因，调用原任务转交接口；核原 Task ID、版本、负责人及单次 reassign Event，保留原 Case/Customer 创建、归属和状态。随后原 UI 退出经理并重新登录接待，读取转交后的实际 Task/Case 版本，再保存本人的计划、建立原业务审计基线。仍不改分派策略、不写业务 SQL、不自动确认后继；此修订待 root 动态复验。

2026-10-03 精确版本修正：经理转交 `key=assign` 不修改 Case，原事件追加不使 Case dirty；前置改为严格核 Case.version 不变、原 Task.version 恰好加 1。旧 Case.version 递增断言是装置错误，未执行新动态候选；此修订只影响独立装置和说明。
