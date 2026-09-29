# PATCH-M8-1-SIDEBAR-ERROR-01

2026-09-29；M8.1 保持 in_progress。

现 `renderSidebar` 在初次加载尚未成功或读取失败时仍渲染三组“0／没有事项”，又追加“这不是空列表”等解释文字：显示含义矛盾，且缺少直接重试入口。

允许只修改 `web/assistantworkspace.js`：区分“尚未读到视图”和成功空结果，初次加载/失败不伪造空列表和零统计；失败后保留已读事项，提供短按钮“重试”，不重置对话草稿，不增加说明性文案。移除该处冗余解释句，保留明确错误、全部原业务入口、授权和上下文竞态守卫。

测试精确范围：`tests/assistant_offline/tests/assistant_plan_ui.test.cjs` 与 `tests/assistant_offline/tests/test_browser_ui.py`。前者覆盖未加载、加载中、初次失败、保留上次数据、真正空结果；后者在原页面注入一次/临时 GET 503，点击原刷新和重试按钮，核对真实服务恢复、事项和未发送草稿。native 与 fixture 模式分别记录，不改 CSP 或浏览器策略。

先保存旧页面代码的失败回归，再修复并复验；其他页面和样式不作顺手调整。
