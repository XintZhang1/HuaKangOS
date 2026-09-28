# M5.1 v1：Run、Plan及回执HTTP接口编码审阅

2026-09-28，计划R4-20260928。新增assistant_runtime_api并由main注册，旧session_view仅附加last_request.run_id；其余原接口保持。

五条路由使用RunCreate/RunCancel/RunView/PlanView/ReceiptLookup严格DTO及原get_user、CSRF、single_store。身份参数不能提交，未声明query返回422。原请求的员工/门店/岗位/权限版本和登录来源先冻结，再独立读取当前登录、账号、门店和原会话权限；异步原GET前后及回包前复验。不从历史Run登录来源推断当前读取资格，也不为读取签发worker/Grant能力。

新消息先查完整digest对应原Run，再检查配置和入队；同号异内容409，关闭Runtime新POST503。配置读取期间的并发已接受请求可再次精确查回。缺表或数据库不可用固定503，不暴露SQL。取消复用原queue版本守卫，不回滚原卡/业务；只有当前可取消Run给出cancel动作。

GET关闭Runtime仍能读现有授权记录。Run只输出白名单字段，真实RunItem/WI/卡关联产生候选引用，再走原业务GET按当前权限过滤。Plan v2用完整manifest/carry投影，v1单独兼容只读映射，不升级、不推断整个业务完成。原对象引用和manual_route从当前原GET取得；不可见或暂时不可读时隐藏，不猜成功。Plan控制动作待M5.3实际路由接入，本项为空。回执GET先对卡所有权作404过滤，再纯读lookup，不协调、不POST、不改状态。

旧会话只在固定Run表确实存在时查同员工/门店/会话/请求号及原trigger key；无表run_id=null，关闭功能仍能找到已有Run。无须模型配置即可读取。作者、root及两名独立审阅者完成来源、身份、返回字段和兼容路径静态审阅，无已知阻断。

## 指纹与待测

外部Python -I -B仅stdlib AST/UTF-8/无U+FFFD/SHA-256，退出0；未导入应用、连接数据库、启动服务或运行测试。

| 文件 | SHA-256 |
| --- | --- |
| app/assistant_runtime_api.py | ae1b68bfae7ca8afcf8b607895f4a4e27f2d4b1d9a6fb272a0f87847f079ede9 |
| app/business_assistant_service.py | 08881020b33e7c9b0ceac6fbaa9e0ccacebc15c9e3ea4ccbd9f6154ea2a619e8 |
| app/main.py | 9d197cb9dce5669f032d70a54727ef0a11ff621b1b8b6eaf42ebcd5aa605ea24 |

真实ASGI Cookie/CSRF/Host、422额外字段、跨人跨店404、登录/权限/门店变更、同号相同/不同内容并发、配置缺失恢复、关闭开关读取、无新表旧会话、完整batch引用、v1/v2计划、原对象暂时不可读、取消版本冲突、GET数据指纹不变、原确认回归均交DeepSeek。Runtime worker尚待M5.6，入队不等于执行完成或worker健康证明。
