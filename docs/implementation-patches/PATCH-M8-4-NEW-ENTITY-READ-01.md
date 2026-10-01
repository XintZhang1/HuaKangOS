# PATCH-M8-4-NEW-ENTITY-READ-01：新单读取精确关联

2026-10-01，当前M8.1，仅 `tests/browser_click/finance_followon_business.py` 本候选的新发票/新对账版本提交读取，原finance_business共享helper保持。finance-followon02已完整所选5执行4通过1失败、退出1、23完整check；HK095真实新批成功但partial，097蓝票实际58及独立差异核对完成后创建红票失败于观察关联，不计完整通过，原件保留。

真实网络记录原POST201后同时读取旧蓝票96和新红票97、均200，原helper用orders/数字前缀匹配而接到旧96；随后invoice_view将该读取对新97核字段导致失败。截图已显示实际新红票、8元和当前原蓝58元。该诊断是脚本关联缺口，不改变原页面、原票或金额规则，不称产品修复。

候选仅新增小型native响应观察：点击前订阅实际GET响应，原POST只点击一次、读取其真实新ID，以精确原路径等本次ID的响应和原URL；事件缓冲处理响应先于POST JSON读取的顺序，不额外请求、导航、重复写或重试。新发票创建/核账创建/重算复开用该观察；同ID核账动作仅等原精确当前路径。保留Cookie/CSRF/门店/幂等/HTTP/JSON/DB/全旧行严格核对、全部原失败，不修改正文断言来求绿。关联进程已退出后修、AST/独立短审，再新镜像原五场景复验。

候选SHA256 `b4a200c97d7f58e11b887ca73c98bd80926234e3da1716544a8eba0cc2b47918`，AST与独立只读短审通过；监听先挂、先到响应缓冲、精确新ID Future、超时无重放、finally移除监听及四处新版本接线均核对。fresh `business-finance-followon-20261001-03` 源a2632178、脚本038879b4稳定，同原五场景复验进行中，未预写结果。
