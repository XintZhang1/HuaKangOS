# PATCH-M8-4-SALES-ADDON-PAGE-READY-01

2026-10-01，05475f4a/6b9edb4a关联四CLI均收尾（1/0/1/1）后先登记。finance04 的销售加装创建原POST201/本单GET200成功，Case105/Task262/Event466/Receipt1成立；原创建后的catalog请求仍在途便退出换员工，旧catalog响应可能抢先满足 read_as 登录前的响应监听。随后本人新本单/通用单/catalog均200、页面已显示，但首次核价读取超时600.14秒。该场和全run已落盘网络没有5xx；无路径/时间的一条engine code5日志不能归为该HTTP故障。

只修改 sales_followon_business.py 的 addon_business 新建成功之后、第一次 responsible/logout之前：等待原“销售加装明细”标题及新原单号码出现在原 .pagehead，再进入原换员工读取。web/addonorders.js的原详情按 detail→FlowCase→catalog顺序读取后才写完整页面，此等待使原创建的在途目录响应完成后才登记下一次读取监听。保留原单ID/版本/来源、独立员工/Task、原请求/Cookie/CSRF/回执/Guard，不改超时预算或增加sleep、重试、HTTP替代、响应伪造或后台业务写。

创建后的全业务行与事实不再重放；旧run整体失败和原timeout/未执行后继保留。AST及独立增量审阅后同新镜像财务17最小闭包重走真实全部父，再按最终指纹全注册联合。四生产开关/193人工/真实日期/历史期间及环境门槛保持。
