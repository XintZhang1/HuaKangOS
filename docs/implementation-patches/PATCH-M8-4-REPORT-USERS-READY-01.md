# PATCH-M8-4-REPORT-USERS-READY-01

2026-10-01，53四关联CLI全退出后，当前连续点击授权内先登记。

report补源01在管理员登录#users只等identity/store，后续users_page立即reload监听抓到登录旧GET200；新document使原响应body失效，Network.getResponseBody失败。17动作，无员工PUT、无第三店Case/Item/Cash；真实权限未拒绝。

仅report_complete_source_business.py两处管理员#users登录，在调用login_as之前监听真实/api/users GET，立即完整读取同响应json并核200/当前店Cookie/原员工账号h1后才继续原authorize刷新。恢复处同样；不得改shared login/users_page/Evidence，不重试、不fetch/Cookie桥接、不取另一latest响应补绿、不重放未知业务。既有列表/改权/CAS/Receipt/Wake与全部旧行守卫保持，旧失效响应/失败原件保留。静态/独立源审后新fresh原UI验证。
