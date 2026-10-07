# 阿里云 main 交付（2026-10-07）

状态：in_progress。main 发布、备份重置、公网访问和真实队列轻量冒烟已完成；当前任务仍待 Cutie 实际回执。

业主已停止后续验收测试，要求把全部已完成源码推至 main，再更新阿里云已有 HuaKangOS 至 main，完全重置该系统数据、建立新管理员，并交付公网 IP 与端口。先备份 HuaKangOS 原数据；只操作该系统，不影响 dsh、QuantumAlpha 等其它服务。授权见 [PATCH-DELIVERY-ALIYUN-20261007-01](../../implementation-patches/PATCH-DELIVERY-ALIYUN-20261007-01.md)，新授权取代历史与之冲突的部署、公网及重置限制。

- 发布：GitHub 与云端应用代码均为 `2bdc7d13c70f0ef7648d2dcfbaa9fa524ab69ec2`；发布 context 为 `8bfef436e8d9fa808c02487b8d5ecc3e99c79372b271b7007afbcc16b26d9504`。
- 数据：旧业务库、运维队列和邮件 outbox 已先备份至 `/var/backups/huakangos/before-reset-20261007T122105Z`，再按授权重置 HuaKangOS。全新业务库迁移至 h53k，初始仅门店1、用户1、迁移版本记录1，无业务数据；新管理员密码只在私有文件中。
- 公网：[HuaKangOS](http://8.133.192.159:28180) 首页及 health 均200，管理员通过原 login／me 成功，原反馈接口201。五个 HuaKangOS 服务及既有 dsh active；MCP 仍仅 loopback。
- 业务助手：四个 `ASSISTANT_*` 开关已在此次授权试用环境启用；原 `app.assistant_worker` 独立 systemd 服务 active，`--health` 为 healthy、fresh=1，queued／running／expired 均0。业务模型使用独立私有配置 `deepseek-flash`，日报外发 off；员工身份、门店权限和原业务确认守卫保持。
- 队列：原 job `70fc2bc3-e84f-4615-9306-58d113d5bc24` 单条反馈、一次 attempt，5次真实 DeepSeek 调用、8次工具，prompt 49,022／completion 2,026 tokens，形成合法源码报告。SMTP 为 sent，Gmail `1a1165231485c6bb` 实际在 INBOX；状态仍 `awaiting_cutie`，无真实 Cutie 回执，不能声称完全闭环稳定。未重发反馈或邮件。

冒烟客户端 logout 缺少 JSON 导致的 cleanup 断言属于脚本问题；原反馈已成功，后续从原 job 恢复 receipt，没有重新提交。外部证据位于 `C:/Users/tiefu/.codex/HuaKangOS-agent-validation/aliyun-main-20261007`，凭据与备份不入 Git。

后续仅文档发布 `d32466a` 暴露部署脚本漏建空 `data` 目录，导致 Web／业务 worker 在只读服务沙箱启动失败；这不是业务库丢失。已在确切 release 下补齐 `root:root 0755` 空目录，保留原外置数据库及 `ProtectSystem`，公网首页、health 返回该 SHA、管理员登录／就绪／退出均200。部署脚本已补每次预建目录及 health SHA 就绪检查，维护说明同步；未重复重置或调用模型。业主已手动唤起 Cutie，独立回执仍按原 job 核对，不代填。

七字典原例114940结构及独立语义7/7、零关键／零写入已完成，原报告和旧失败保留。当前最终候选完整283／同批101与M8.6多轮、独立保留集未执行；M8.5、M8.6、CP-37保持 `deferred_by_owner`，非验收完成或 released，后续按用户反馈修复。此次为授权试用交付，不代替原生产验收；不影响 dsh／QuantumAlpha 等其它系统，不改写 total_plan.md。同步后续文档发布不重新重置数据或扩展测试。
