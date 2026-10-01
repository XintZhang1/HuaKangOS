# PATCH-M8-1-REMAINING-AUDITED-READ-WRITERS-01

2026-10-01，当前 M8.1 浏览器交付精确补丁，实施前登记。13:45 UTC 核对关联 Python 和 57132–57134 监听均已结束；finance09 原12/17局部证据无终局，记中断；receivables08、reports07 原完整失败保留，不继承成绩。

receivables08 实际文件86 GET带本人Cookie/当前店，返回503 JSON；原下载随后追加审计并commit，却仍普通get_db。日志有5/517但没有请求关联，不把517精确归给file86。静态逐链审阅见 audited-read-writers-current.md：228个GET中12个同步成功审计提交，4已接线，8尚未接线；普通读取、async/SSE与独立拒绝事务不概括为本次修复。

精确允许：app/flow_api.py download；app/dossier_grant_api.py record/files/download；app/stock_report_api.py export；app/material_value_api.py export；app/repair_material_api.py export；app/main.py export_csv。仅其db依赖改为已建立的get_audited_read_db并补必要导入，全部保持原db→get_user顺序。结构化8清单在外部launches/audited-read-writers-candidates.json，SHA fcea48139db0128f40cc76358847efd1afd72536b86fa588ba158940f7e3063d。原权限/门店/跨店逐件授权、扫描/摘要/字节、同范围CSV、访问日志与一次commit及所有错误响应不改；不重试、不提前返回数据、不开放助手能力。

tests/browser_click/sales_order_business.py 的generate只增加下载响应的即时诊断：在原expect_download内部监听同一文件GET，先核200与原二进制类型；真实503必须直接留证，不用等待下载超时掩盖。保留下载原字节SHA/大小、DOCX报价/VIN/原单、全旧业务行不变与唯一原审计。无Cookie桥接或fetch替代。

原路由返回asset.media_type，原生成文档的类型为标准DOCX；候选SELECT只补该原字段，响应类型精确与FileAsset及标准DOCX同时比较，不猜octet-stream。此处类型在静态审阅时纠正，尚未启动新运行。

收尾后实施、逆向AST/原字节核对和独立审阅；新外置镜像复跑受影响原11/17闭包，之后唯一同版本full53。当前193/111、真实Date、模型101/283、PG/Linux/员工/生产门槛与四默认关闭开关保持。不能宣称全部busy、异步或业务验收已解决。
