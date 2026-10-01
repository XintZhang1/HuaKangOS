# PATCH-M8-1-REFUSAL-SHORT-WRITER-01

2026-10-02，M8.1 修改前登记。full13 HK188 原申请人单次自批返回真实403及“申请人不能自批会员价格，管理员也不例外”，但没有 refusal DTO 或数据库拒绝行；服务器实际记录 `Refusal evidence not recorded (OperationalError)`。不能把规则拒绝改成权限不足、删除严格断言或制造拒绝行。

仅允许 `app/main.py note_refusal` 在自己拥有的短 SessionLocal 中、首个 User 查询之前调用既有 `get_write_db(db)`：复用原有限 SQLite writer 合同，先保留写事务再读取本人、分类、追加原拒绝、清理和提交。PostgreSQL沿用原事务；原路径排除、身份/门店/当前岗位、403/422范围、分类、can_escalate、原响应及记录失败不覆盖原拒绝的保护保持。

不把异步业务会话或远程模型调用包进写事务，不新增重试、全局锁、默认管理员或测试数据库写入。须独立检查原路由依赖在异常处理前释放，以及自身新事务无 await 后才实施；未证实时不改源码。新真实点击仍严格要求唯一真实规则拒绝、正确本人/门店/原路径及其余业务全行不变，再核完整53。
