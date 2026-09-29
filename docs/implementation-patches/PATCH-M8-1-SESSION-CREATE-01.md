# PATCH-M8-1-SESSION-CREATE-01

2026-09-29；M8.1 保持 in_progress，接续本轮侧栏和代办核对。

## 问题与边界

本轮桥接 Chromium test_07 在调用模型之前，原 `POST /api/business-assistant/sessions` 返回 409，页面留下“另一项操作正在处理，请刷新查看”。前一个门店查询仍可与新页面并行，不能通过等 worker 完全空闲来掩盖实际使用冲突。静态检查显示登录依赖先建立 SQLite WAL 读取快照，创建对话随后在同一事务写入；先建立并发提交的确定性原 HTTP 复现，确认具体错误码。

## 精确范围

- `app/business_assistant_api.py`：仅新对话入口，在无待写业务内容的前提下结束原认证读取事务；SQLite 在重新核验原 Cookie、CSRF、账号及门店岗位之前预留一个短写事务。使用原会话模型及原 create_session；不重试业务提交、不生成新 request_id、不放宽权限、不新增接口。
- `tests/assistant_offline/tests/test_session_create.py`：原 HTTP + 独立 SQLite 提交复现；验证只新增一段对话且业务计数不变，退出/停用/换岗/强制改密不得复用旧身份；并发创建可各自正常完成。数据库和凭据只在隔离输出目录。
- 不改变通用 commit、原业务重试规则、worker 单槽、生产数据库配置或浏览器策略。仍须真实页面复验。

首次故障、确定性红灯和修复后结果分别保留；只有真实执行后追加检查点结果。
