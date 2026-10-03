# PATCH-M8-1-VALIDATION-WORKTREE-BINDING-01

2026-10-03；M8.1 正式外部入口接续。业主要求在当前工作树收口全部技术项；V 是已批准的仓库外 NTFS 验证根。当前 V 的 `binding.json` 和 manifest 仍指向 `E:\HuaKangOS`，实际本次工作树为 `C:\Users\tiefu\.codex\worktrees\5502\HuaKangOS`。只读 Git 验证两者 common-dir 均为 `E:/HuaKangOS/.git`，origin 均为同一 HuaKangOS 仓库。

精确允许范围：在 V 新建不可覆盖的 `binding-history/<本轮唯一目录>` 保存原 binding、原 manifest 的字节、SHA-256 和迁移记录；随后将当前两个 repository 字段一次性绑定到本轮工作树。保留原 `isolation.bind` 对完全相同绝对路径的严格检查，不增加 fallback、别名、跳过或宽泛目录允许。原 runs、报告、合成库、旧归档和依赖不改，不继承旧通过成绩。

正式 M8.1 注册保留旧两个定向合同，追加固定 adapter，调用当前 `tests/browser_click/run.py` 完整注册入口。adapter 和精确 registry/provenance 只在 V 维护，新的当前源码、runner、脚本、依赖指纹由真实新 run 记录。M8.2 的严格基线仍须按新绑定重新取得匹配的 M0.1 证据。

正式 isolation 的原排除范围含全部 `tests`，因此本次补齐精确源码白名单：仅当前浏览器入口 `SCRIPT_FILES` 的明确 `.py/.json` 相对路径进入新镜像及 source fingerprint，并在当前 manifest 冻结同一完整文件清单。仍排除所有其他旧测试、环境、数据库、凭据、截图、日志和外部文件；仍拒绝符号链接/越界与复制时指纹变化。adapter 从该镜像入口再次建立全新外置浏览器实例，校验白名单、原入口清单与脚本 SHA 全部相同，不从工作树或旧归档偷读被测应用。允许修改 V 的 `harness/isolation.py` 这一精确源码过滤范围；`bind`、数据库/网络边界及原结果验证合同保持。

本补丁是当前工作树的明确验证绑定迁移，不授权访问 E 盘原预览数据库、配置或客户附件。绑定及注册本身不表示任何验收通过。
