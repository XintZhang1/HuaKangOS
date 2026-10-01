# PATCH-M8-4-REMINDERS-SAME-PAGE-01

2026-10-01，M8.1，所有关联验证已结束。customer-reminders01 首次本地摘要读取在已有同hash CV页 page.goto 时没有新导航/GET，原15秒 response等待超时，尚未执行三个提醒业务。仅 tests/browser_click/customer_reminders_business.py 的 history 在同页先等待实际当前CV标题，再使用原 browser reload；不同页保持 goto，均先绑定真实 history GET。DB 只读/全旧行保护、同源Cookie/CSP、时限和原摘要断言保留，不用fetch桥接或合成响应替代。
