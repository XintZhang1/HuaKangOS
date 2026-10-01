# HK188 本轮拒绝证据诊断与精确源码复审

2026-10-02，只读审阅 `automatic-business13/evidence/member-points-tier-hk121-122-188-120-119-131` 的原 network／actions／observations／business-checkpoint 与当前源码。本审未执行应用、浏览器、SQL 或测试，未读取密码／配置，未修改生产或测试源码。

## 已观察事实

该场原动作 267（原申请人点击自批）请求 `POST /api/member-pricing/rules/1/actions/approve`，同源 Cookie／CSRF／门店 1，响应 HTTP 403。`price_action` 第 543 行先要求 HTTP 403 和完整原 detail“申请人不能自批会员价格，管理员也不例外”，随后第 545–547 行要求真实 rule／can_escalate=false refusal，后者失败。因此不是误查其他页面 notice 或原拒绝文案过时。原 failure 的可见文本在当前自批 modal 显示同一服务器原文，没有被改称权限不足或可评审。

原 `server.log` 第 105 行唯一记录 `Refusal evidence not recorded (OperationalError)`。父任务另报告对标记合成库的只读检查未找到对应拒绝行；本审不读取该库。失败前未持久化 response refusal DTO，不能仅由失败截图还原 DTO；结合服务器记录与父任务事实，原因是原拒绝证据未写成，而非分类错误。日志其他 code 5／517 不逐行认定为本业务失败，也不能从未记录具体 SQLite code 的该 warning 断言它必为 517。

`app/escalation_service.py` 第 23–24、37–44 行的原有限分类对本 detail 不匹配任何额度／权限提示，结果为 rule；`app/main.py` 只由真实记录返回 category 与 can_escalate。`web/app.js` 第 119–125、132 行将服务器 detail 原样构成 Error 并显示到 modal `.formerror`；会员价格原表 `web/memberpricing.js` 第 21 行仍调用原 API。测试断言不能删除、改宽或造拒绝行。

## 原事务释放与自身短 writer

原 `member_pricing_service.command` 第 107 行先更新并 flush 原 Case；第 115 行禁止申请人自批并抛 403。`group_service._execute` 第 96–98 行 `except Exception` 明确 `db.rollback()` 后重抛。对于本次已进入该 operation 的 HK188，原业务事务在进入 HTTP exception handler 前已显式回滚释放；不需要依赖推测整个框架的延迟依赖清理时序，也不据此扩展到所有异常路径。

原 `main.note_refusal` 自己打开 `SessionLocal`，先读 User、再 `record_refusal` 的 flush、清理及 commit。它此前没有写事务选项，存在 SQLite WAL 首读后升写的并发窗口。仅在该 own session 首读前复用既有 `get_write_db(db)`，与有限短 writer 方案一致；该辅助方法只对 SQLite 设请求／本 session 的 OptionEngine 并启动连接，PostgreSQL保持原事务。该函数自身无 await，无远程模型／业务持续操作。此静态链支持最小修复，不能保证消除所有并发错误。

## 修改后独立字节复审

按已事前登记 [PATCH-M8-1-REFUSAL-SHORT-WRITER-01](../../implementation-patches/PATCH-M8-1-REFUSAL-SHORT-WRITER-01.md) 核对：

- 外部 `launches/refusal-main-before-20261002.py` SHA256 `c6df782f65a95ce6d24ffd4cde18b1e8a2581b9c57835341be90a9c02777862d`，与 `automatic-business13/source/app/main.py` 原字节完全相等。
- 当前 `app/main.py` SHA256 `a778b6443d79d45c24106c34672f12dd7a37b87f9b7450fc12672866ddf5b528`；仅 `note_refusal` 局部导入增加 `get_write_db`，在 own `SessionLocal` 内首个 User read 前增加调用。
- 标准库 AST 解析通过；排除该函数后整文件原字节完全相等，所有其他顶层 AST 相等。身份／当前店岗位、路由排除、403／422、分类、DTO、清理、原提交、原响应及记录失败不覆盖原响应的保护均未改。

源码静态审通过，不是动态业务 passed。后续新轮必须仍要求一次原自批 403、完整原 detail、一条真实 rule／can_escalate=false 拒绝、正确本人／门店／原 method/path，全部旧拒绝及其余旧业务保持；明确放弃也不得消费拒绝。原第 13 轮 HK188 failed 与后续 not_tested 保留，图像审冻结为 partial／accepted=false，不继承到第 14 轮或完整 53／193。
