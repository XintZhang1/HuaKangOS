# M5.2 v1：持久SSE与旧聊天兼容编码审阅

2026-09-28，计划R4-20260928，补充范围PATCH-M5-2-01。只完成代码与静态审阅，未完成真实连接验收。

Runtime API共用accept_run及open_event_stream。后者在返回迭代器前完成真实登录、当前会话权限、游标与首批事件核对；after_seq/Last-Event-ID只接受非负整数，重连取较新位置，future/缺序409。每批核实际Run/event_seq，终态必须有最后生命周期事件并排空全部批次；每条缓存事件重新核当前身份与实际event、子项、卡、WorkItem、Plan，原对象引用走原GET过滤。数据使用RunEventView，id=seq，进度仅安全累计display。关闭Runtime仍可读已有事件。

订阅迭代器独立持有同Engine的空闲Session作为读取入口，真正查询在短reader完成；不跨sleep/yield持事务。1秒补读、15秒只读心跳，断开仅关闭迭代器；没有Run领取、业务提交、取消或模型调用。ASGI发送异常也显式关闭两个迭代器，运行时HTTP错误只发固定订阅错误后结束。

旧message/stream仅在Runtime开启时调用同一accept_run。普通接口等待最多600秒；超时504带原run_id，断线499结束订阅，失败/取消明确报告而非成功。成功必须精确核原Run trigger/request/digest、原user消息及唯一request_id:reply，不能拿后续新回复或进度替代。旧流只发处理状态，终态发一次持久回复delta及完整SessionView；不追加可能被改写的中间累计文本。delta/done前重新验权，失权不吐缓存会话；finally只关闭订阅。原legacy streaming_response的AST与HEAD一致，关闭开关保留原执行路径及原业务确认接口。

service旧会话用同一真实Run的queued/running投影processing，Runtime开启时显示busy；不修改busy租约或业务互斥。实现及来源、接口实参、终态顺序、最终回复和清理边界由作者、root及独立审阅交叉核对，无已知编码阻断。

## 静态指纹

外部Python -I -B仅stdlib AST、UTF-8、无U+FFFD及SHA-256，退出0。没有运行测试、应用、数据库、worker或模型。

| 文件 | SHA-256 |
| --- | --- |
| app/assistant_runtime_api.py | a13d1b7d939d430d52a136cff985c73c33d1135ef01bb8bf21a5d6283b53a209 |
| app/business_assistant_stream.py | 6d6b729d9bdfb6808237fd9b17670cda2c357c2bfb80ce7b97ee7f82d0acc9a3 |
| app/business_assistant_api.py | ffc02605a5b93bf887e2ba8c8e7e67106b9f5fe929f7fb080e20ac6ae9f2a030 |
| app/business_assistant_service.py | 498bb57d0ef3eb37b6a2cd4f7dc2acdb95ae27baeb323afe38eb94fe8b8fc541 |

## 待集中验证

真实Cookie/CSRF/CSP/SSE、反向代理缓冲、两个订阅者只读同一Run、after_seq与Last-ID重连、多批终态/缺序/future cursor、每帧撤权/退出、事件引用授权变化、DB错误、ASGI 2.4发送异常与旧断连、600秒等待/无流断线、累计展示改写、最终回复缺失或他轮回复、queued未租约状态、Runtime关闭旧聊天与新历史查询、同request并发及原确认均交DeepSeek实测。静态审阅不替代任何原验收条件。
