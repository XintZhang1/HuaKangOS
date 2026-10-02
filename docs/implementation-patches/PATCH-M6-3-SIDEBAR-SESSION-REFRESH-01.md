# PATCH-M6-3-SIDEBAR-SESSION-REFRESH-01

2026-10-02，业主虚拟数据优化后交付授权，当前仍只 M8.1。在receipt-unknown37实际17号截图，B结果不明、C待确认、A已成功的三原卡存在，左侧却全部0；24号原刷新/历史后才变attention2/finished1。独立读原网络确认初始workspace GET早于Run/三卡，原准备终态和A/B确认后只读session、没有重读workspace。原_cards后端实际允许三卡，问题是展示缓存未刷新，不修改服务器计数或权限筛选。

修改前virtual-critical38实际CLI0终局、关联Python/57391监听均0。精确生产范围仅 web/businessassistant.js 的两个原收尾边界：Run终态已实际读回event.session并通过原Alive守卫后一次workspace.load；businessAssistantTask finally在原work/RefreshWork完成、再次Alive通过、释放busy后且仍助手页调用一次。整组批量结束只刷新一次，不逐卡发新查询。不从session卡数猜侧栏总数、不增加轮询/模型/自动选事项/写入；沿原workspace owner/context/serial丢弃迟到或乱序。原load读取失败在本模块显示原error，不等待或改写已经成功的原确认结果，不把反馈失败当业务失败。原输入、草稿、卡选择、权限、API、状态、默认关闭开关均不改。

精确测试范围仅 tests/browser_click/runtime_batch.py 原两批量场：准备/确认后无手动刷新时等待侧栏真实原proposal key，核原三卡当前待确认/结果不明或未办成/已完成展示与原确认阶段一致；继续所有原UI/卡、冻结提交与业务全行断言。不为了列表求绿预先调用load/fetch/直接写DOM或只改断言。若列表按原分页/授权不返回该卡须真实失败并核查，不能杜撰数量。新最终指纹关键路径重复及完整57 CI验证；37/38和此前结果保留，原M8.1其它合成/正式待测边界不变。
