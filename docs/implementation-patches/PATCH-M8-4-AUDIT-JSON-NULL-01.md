# PATCH-M8-4-AUDIT-JSON-NULL-01：原JSON空值读取

2026-10-01，当前M8.1，仅 `tests/browser_click/system_followon_business.py` 的 photo_audit 前值读取。fresh system-followon01所选3场2通过1失败、退出1；真实PNG上传200、公开JPEG解码、DOM与metadata摘要已核，随后脚本错误要求SQLite原before_data单元必须SQL NULL。外置只读核原AuditLog620确为JSON字符串 `null`，after仅实际JPEG sha256，原services.audit与JSON模型没有额外图片或凭据。HK192/193未完整通过，旧失败保留。

只按原JSON存储解码before_data后比较None，after仍严格等于单sha256对象／恢复默认的None；actor、门店、action、reason、唯一维护审计、metadata/字节和全部旧行保护保持。不是生产漏洞或脱敏修复，不接受任意空串／对象，不改原JSON字段或断言所需事实。相关注册验证进程全部结束后实施，AST与独立短审，新镜像复验；未执行不计成绩。

脚本5aeb5abb经AST、独立原JSON模型及窄修短审；实际新镜像待复验。
