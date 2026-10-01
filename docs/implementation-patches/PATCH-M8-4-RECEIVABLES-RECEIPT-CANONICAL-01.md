# PATCH-M8-4-RECEIVABLES-RECEIPT-CANONICAL-01

2026-10-01，M8.1 当前浏览器候选精确测试修复，修改前登记。finance11 已完成17/17且原CLI0，receivables10 原CLI3，两轮正常收尾、关联Python进程已消失；合成provider均0/0/0。

receivables10 最后候选原到店、维修转换和报价POST200已实际成功，Case124、Quote2、Line3、Receipt141均为原事务产生；随后测试比较回执digest失败。原 app/repair_api.py Quote补默认值，app/repair_service.py command在计算原回执前显式去除为空的member_pricing；测试repair_command却人为补入该空字段。ScopeQuote/PackageQuote仅各自明确路由使用，不将其扩展默认值混入普通报价。

仅允许 tests/browser_click/receivables_business.py repair_command 的quote分支：保留purpose=service、discount_cents=0、retained_amount_cents=None和每行line_key=None；与原服务一致仅当member_pricing缺失或为None时去除该键。原请求全部显式值、非空member_pricing、版本、本人、门店、请求ID和精确operation/payload digest仍逐项比较。不删回执断言，不读取DBdigest充当预期，不更改生产、数据库或重放原请求。其余函数和allocate分支不变。

AST、精确差异及独立源码审后，使用全新外置镜像重跑原11场景闭包；完整53同版本验证和193逐项体验/Date待验证保留，禁止拼接旧局部结果为全量。
