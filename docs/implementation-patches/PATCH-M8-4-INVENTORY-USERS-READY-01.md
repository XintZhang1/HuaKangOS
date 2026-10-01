# PATCH-M8-4-INVENTORY-USERS-READY-01

2026-10-01，53/f45b817a四CLI全退出1后，当前连续点击授权内先登记。

Inventory03首次501管理员登录#users未等原列表，503 access_form→users_page立即reload捕获旧GET，随后正文失效。没有本场景员工授权PUT或500移库，员工19仍仅一店manager。本地库存非空读取与未经授权拒绝已有诊断，但HK071整体failed。

仅inventory_scope_business.py三处管理员登录（初次/恢复/失败恢复）在login_as前监听当前明确店的真实/api/users GET，读原响应JSON并核200/Cookie/当前店/员工账号h1后才进原users_page刷新。实际失败只501，另两处同契约接线；不改shared helper、不新增API调用/重试/fetch/回放/另一latest对象。原权/版本/回执/旧行/店内分录规则保持，旧原件不覆盖，新镜像复验。
