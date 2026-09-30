# 浏览器实际点击验证

从当前源码建立全新的外部合成实例，再用浏览器真实登录、输入和点击。模型响应是确定性模拟；页面、Cookie、CSRF、CSP、SSE、原业务 API、worker 和数据库均使用当前代码。此入口没有页面桥接或浏览器失败后的替代模式。

在独立 Python 环境安装根 `requirements.txt` 和 `playwright==1.56.0`（与本轮实际脚本环境一致）。使用已安装 Chrome 时传 `--browser`；使用 Playwright 固定版本自带浏览器时先执行 `python -m playwright install --with-deps chromium`。浏览器未安装或显式路径无效时直接拒绝，不自动换浏览器。

```powershell
# 自动点击；Windows 默认产物位于 C: 的独立 NTFS 验证根。
python tests/browser_click/run.py --browser "C:/Program Files/Google/Chrome/Application/chrome.exe"

# 为交互式浏览器审阅启动一个独立实例。
python tests/browser_click/run.py --serve --browser "C:/Program Files/Google/Chrome/Application/chrome.exe"
```

`--source` 选择被测源码。`--output` 必须是仓库外尚不存在的新目录；Windows 必须位于 NTFS。默认 Windows 路径为 `C:/Users/tiefu/.codex/HuaKangOS-agent-validation/runtime-v1/browser-click/<UTC时间与随机标识>/`，Linux 为 `$RUNNER_TEMP/huakangos-browser-click/` 或 `/tmp/huakangos-browser-click/`。入口仅复制 `app/`、`web/`、`migrations/`、`requirements.txt` 和 `alembic.ini`，跳过环境文件、数据库、缓存和日志，不读取原预览配置。

`--serve` 会打印真实 URL、manifest 路径和随机合成用户名。密码仅在外部 `runtime/credentials.json`，不会写入日志、manifest 或 CI 产物。按 Ctrl+C，或在该实例外部 `runtime/` 内创建 `stop-requested` 文件，可正常关闭 Web/worker并记录 `stopped=true`；未收到请求的服务退出仍报失败。数据与失败证据保留，不覆盖历史目录。交互启动和正常停止均不产生自动通过结论。

合成指令：`查询本店张姓客户`、`新建客户 浏览器客户Demo`、`浏览器接待计划`、`慢速查询本店张姓客户`、`模拟异常`。客户卡片需要员工点击确认；接待计划使用两个真实合成接待单，开启跟进和每次业务确认分别由员工点击。接待分派沿用原岗位规则，使用合成管理员；普通客户场景使用合成销售。

统一评价标准见 `rubric.json`。自动结果与人工显示、文案和流程判断分别留证。390/768/1440 三种宽度、原业务导航、草稿保护、切店/退出隔离、准备前零业务写入、确认后唯一写入和页面错误都绑定同一次源代码与脚本指纹。自动脚本通过不替代 PostgreSQL、真实模型、HTTPS 部署、员工效率试用或发布验收。

原需求表清单为 `requirements_manifest.json`：10 模块、193 项、111 个发布工作流、70 个共用页面。桌面新提供的表与仓库原表字节一致。除九组关键助手场景外，四组扩展通过原 UI 检索全部需求编号、选择业务分类、打开每条指引、点击所有共用原人工页面，并打开九个代表表单后取消。金额、库存、退款和月结等完整操作没有足够合成前置时留待对应业务验证，不由列表或空表单代替。

每项结果记录于仓库外 `evidence/requirements-coverage.json`，分别显示搜索、指引、页面、代表表单和已实际执行的业务子动作。HK-098 仅验证客户新增与历史唯一性，HK-002 仅验证第一张接待分派确认；夹具预先创建原单不计员工点击实测。会员和套餐详情的补充 Cookie GET 单独计数。清单自身始终标记 `unexecuted`，没有历史成绩继承或 193 项完整业务验收结论。

每次输出包含 `source/`（被测生产镜像）、`scripts/`（执行脚本）、`runtime/`（合成数据与凭据）、`evidence/`（报告、截图和日志）与 `manifest.json`（无密码的实例信息）。初始化应用前核对源码与脚本复制前、复制内容、复制后三份逐文件指纹；发现并行修改则保留 `snapshot_stable=false` 证据并拒绝启动。CI 只上传 `evidence/`，不上传凭据、数据库、配置和附件。

退出码：`0` 自动点击完成且证据完整，或交互服务正常被停止；`2` 预检拒绝；`3` 执行、超时、空场景或证据失败。自动通过以 `evidence/run-summary.json` 的 `complete=true` 且 `passed=true` 为准。
