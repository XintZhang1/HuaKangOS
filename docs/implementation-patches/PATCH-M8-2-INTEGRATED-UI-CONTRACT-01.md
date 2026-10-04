# PATCH-M8-2-INTEGRATED-UI-CONTRACT-01

2026-10-04，main 已纳入业主要求的旧工作区界面。M8.2 只读配对确认三处原静态/Node 测试仍要求已被业主明确移除的独立交接按钮或旧统计侧栏地址；原生浏览器 iu1 已实际证明新界面的人工入口、原目录和权限仍可用。这是旧显示合同适配，不回退已批准的界面。

两平台 CI `37169614459` 已由 root 取消并确认均 completed/cancelled，之后才修改输入。其已执行观察仅留历史，不计完整回归通过。

精确范围仅为 V 原 overlay：

- `tests/runtime/test_m6_4.py::test_navigation_order_and_original_entries`：统计侧栏预期改为 `analytics/overview`；原其它导航、原模块兼容入口和权限断言保留。
- `tests/runtime/test_m6_5.py::test_original_surfaces_render_the_same_handoff_button`：原 task/case 兼容 helper 保留；模块/快捷卡独立助手按钮调用改为不出现，核原人工打开入口仍在。原员工发送、上下文 DTO、表单/草稿及身份守卫全部保留。
- `tests/frontend/test_m6_5.cjs` 原“共用按钮只渲染合法引用，三种来源各有确定的 ref 语法”节点：新统一 helper 对合法/非法/关闭开关均返回空，不再渲染独立按钮；相邻真实 parseRef/requestHandoff/send 守卫节点不变。

保留原测试 ID、节点数、74 个有序登记数组和全部 101 命令，以免把显示调整变成删测。历史名称仅作稳定 ID，函数内注明新授权合同。原文件、候选和差异外置保留；按精确 SHA 更新 `archive/baseline-restoration.json` 与新的 source-only capsule 清单，其它输入逐哈希不变。实际同候选双平台完整 strict/full 仍须重跑，静态矛盾不写成运行失败或运行通过。

静态实施及独立审阅完成：三文件前后原件、精确差异和来源保留在 V/closeout-20261003/integrated-ui-static-contract-candidate-20261004T021208Z-b967a1b437；未执行新测试。801 实际文件逐 SHA 一致；797 其它输入保持，主 manifest 字节不变。最终 v12 draft SHA `9895a246dc0b8dc1421388aae9797ce8232b8341ff15e76b50d5dd4e6ce63797`，封包 SHA `e0856fc33c3323d69524064175d3682ad2d43d9da8c9d1805f589db14ff3adf0`，draft release asset `608958756`。独立复查暂停原件没有反复停在同节点或死锁证据，不新增诊断设施，下一轮按原完整时限执行。
