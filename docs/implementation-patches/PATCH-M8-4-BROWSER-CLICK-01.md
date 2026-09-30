# PATCH-M8-4-BROWSER-CLICK-01：以实际点击组织当前浏览器验证

日期：2026-09-30。依据：业主本轮明确要求同步 feature 分支、热重载当前实现、删除旧测试和测试套件 CI，建立浏览器实际点击的新脚本及 CI。本授权取代旧测试保留在工作区和测试整体后移的执行限制；不改变业务、权限、人工确认或原验收门槛。

## 精确范围

- 移除工作区旧 `tests/assistant_offline/`、`scripts/check_category_vocabulary.py`、`scripts/check_money_input.cjs` 与 `.github/workflows/assistant-offline-checks.yml`；两条 scripts 仅为旧回归检查，生产无调用。先在仓库外保留可恢复副本，Git 历史和外部历史证据不改写。`scripts/build_workflow_guides.py` 保留。
- 新增 `tests/browser_click/` 的隔离执行入口、合成模型/数据服务、实际点击场景、统一评价标准和说明；新增 `.github/workflows/browser-click-checks.yml`。不恢复旧 Python/Node 单元套件或 ASGI 页面桥接模式。
- 更新 `AGENTS.md`、`README.md`、`implementation_plan.md`、`.gitignore` 中本轮执行指引；新增 `docs/architect/progress.md`、`docs/architect/tasks/browser-click.md` 及本轮检查点。补回当前缺失但 AGENTS 引用的 `CODEX_EXECUTION_PROMPT.md`、`DEEPSEEK_TESTING_HANDOFF.md`，只说明当前入口与未满足的原验收条件，不恢复过时的禁止本轮测试规则。`total_plan.md`、历史报告和既有迁移只读。
- 产品源码只有在实际点击发现缺陷并登记精确修复范围后修改；不预先重构，不降低原 API 的权限、版本、幂等与事实守卫。当前代码所有生产开关仍默认关闭。

## 执行合同

从当前工作树白名单复制 `app/`、`web/`、`migrations/`、`requirements.txt`、`alembic.ini` 到仓库外全新 NTFS 运行目录；不复制 `.env`、原数据库、私有附件、日志或配置。设置全新的合成 SQLite、随机合成账号密码、附件根和模型配置后才导入应用。模型响应可模拟，业务 API、浏览器登录、Cookie、CSRF、CSP、SSE、点击确认与数据库写入须走当前真实代码。阻止模型外网请求，不降级为 fetch/Cookie 桥接。

脚本与 CI 使用同一个入口，记录源码/脚本指纹、浏览器版本、逐场景动作、截图、真实请求状态与数据库核对。所有运行数据与报告留仓库外；失败、超时和空场景均非通过。CI 不使用秘密或生产服务。可复现的自动标准与人工界面/文案判断分别记录，不以开发者自测替代员工效率验收。

## 统一标准与边界

核对 390/768/1440 三种宽度下的显示与可点击性、关键业务操作数、简洁且准确的状态/按钮文案、前后端数据一致、准备前零业务写入与确认后唯一写入、原业务导航/草稿保护、切店与退出隔离，以及 Cookie/CSRF/CSP/SSE 和页面错误。已知缺陷必须修复并重走受影响点击路径。

本轮是独立的浏览器交付任务，M8.3—M8.10 按原条件如实登记；不得把本轮通过改称 PostgreSQL、真实模型、独立 Linux、员工试用或生产发布已验收。M8.1/M8.2 历史 implemented 与报告保留，不继承其计数为新测试成绩。
