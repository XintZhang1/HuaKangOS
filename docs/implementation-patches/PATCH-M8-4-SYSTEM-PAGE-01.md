# PATCH-M8-4-SYSTEM-PAGE-01：原生会话页面的返回值绑定

2026-10-01，当前M8.1，仅 `tests/browser_click/system_followon_business.py`。system-followon02所选3场2通过1失败、退出1，源a2632178/脚本6d03251f镜像稳定，9完整自动check；登录图片上传/恢复及本人改密实际完成，随后失效旧页面复验遇到dict.expect_response错误，HK192整体未通过、HK193未开始。原new_staff_page返回(Page,登录事实)，password_check把第二个返回值误当另一旧Page。原件保留。

相关三实例均已结束。只把另一会话绑定为第一个Page返回值，继续原401重载、登录控件、零业务写和全部会话撤销核对，不修改任何生产或账号规则，不追加登录重放。AST与短审后新镜像复验；局部图片/改密事实不继承完整通过。

d30c0d87经根AST及独立(Page,dict)原helper返回合同短审，两个旧Page原401及零业务写核对保持。新联合镜像待出结果。
