# PATCH-M8-2-CASE-DETAIL-CONTRACT-01

2026-10-04，M8.2 当前完整 CI `37170796831`（main `ef4f62d`）两平台均已自然终局 failure，之后才修改输入。Linux 原件已验证官方 artifact digest；实际执行到 B 组 33 节点，前 32 通过，最后节点在原单 GET 返回后读取 `values` 发生 KeyError。此前完整收集、矩阵和 A 组通过不代表本项完成；后续 97 命令未执行。Windows 原件另核，不拼接结果。

原 API `app/flow_api.py::describe_case/case_detail` 明确返回 `data`；`values` 仅为创建输入。该节点已实际完成原卡员工确认、成功回执和由回执编号查询原单。缺陷属于新增测试对原接口的字段观察，不改变生产接口或原业务合同。

精确修改范围：V 的 `tests/m82-closeout/shared-contracts/test_database_integrity.py::test_explicit_legacy_upgrade_and_real_id_fill_keep_goal_and_grant`，仅将 `actual.json()['values']['customer_name']` 改为 `actual.json()['data']['customer_name']`。保持真实 API 路径、身份、同名客户值、真实编号、历史升级和后续 goal/grant 完整保持断言。原节点、33 个 B 节点、全部 74 有序数组及 101 命令不变，不添加 mock 或放宽断言。

在独立外部目录保留原文件、差异和两平台失败证据；同步主 manifest、restoration 中该补充输入的精确 SHA，并生成新的 source-only capsule 登记。其余输入逐 SHA 保持，旧 capsule 不覆盖。静态审阅后按原双平台 strict/full 原时限复跑；本补丁不声明新运行通过，M8.2 仍唯一 in_progress。
