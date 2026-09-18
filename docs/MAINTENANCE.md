# 自动维护与飞书审批 — 0.2 接线说明

## 先了解边界

多门店、账号和意见收集不依赖飞书、Git、Docker或DeepSeek。只运行普通启动脚本即可。自动维护是可选功能，需要一次性完成下面的接线。

本版实现「受限源码修改 → 隔离测试 → Git候选分支 → 飞书人工审批 → 本机版本切换」。不是能自动完成任意后端开发的通用Agent。白名单为 `web/app.js`、`web/style.css`、`web/index.html`、`docs/USER_GUIDE.md`。源码外发仅含这些文件、固定说明和所选意见正文，不包含数据库、.env、客户表、财务表和私钥；意见本身不得夹带这些信息。

模型的 `risk=low` 不是安全证明，自动测试通过也不能保证界面没有业务缺陷。尤其不要仅凭AI摘要盲目批准；卡片提供真实Git diff供核对。任何有权限读写宿主机数据库或控制器目录的人，均处于本系统信任边界内；这里不是防御宿主机管理员的隔离方案。

## 一次性准备

使用一台固定电脑运行，安装Python 3.11–3.13和Git。自动测试还需要Docker（Windows/macOS使用支持Linux容器的环境）。先正常运行一次 `start.ps1` / `start.sh`，建立账户与数据库，然后停止启动窗口。

为DealerDesk建立一个独立的私有Git仓库。不要指向你的量化项目或其他工作仓库。把当前这份**完整0.2代码**提交到主分支，保持项目根目录结构。不要提交 `.env`、`data/`、`backups/`、`.venv/`、任何证书或数据库；`data/.gitkeep`占位文件可保留。本包的.gitignore和.gitattributes已处理通常情况，但提交前仍需检查暂存内容。

示例命令由你在本机执行，替换为专用仓库地址：

```bash
git init -b main
git add .
git status --short
# 核对没有凭据、真实数据库或备份后再执行：
git commit -m "DealerDesk trusted baseline 0.2.0"
git remote add origin git@YOUR_GIT_HOST:YOUR_ACCOUNT/dealerdesk.git
git push -u origin main
```

使用限于该仓库的写权限密钥或凭据管理器。URL里不能嵌入token或密码。控制器仅普通推送，不使用force-push，也不会修改远端保护规则。如果仓库要求必须走PR审核、不允许这个发布身份快进主分支，本版会停止发布；它尚未接GitHub/Gitee的PR审批接口。卡片链接是分支差异页，而不是已创建的PR。仓库页面须支持 `/compare/BASE...HEAD` 路径，其他Git平台需由维护人员适配链接。

## 安装可选组件

Windows：

```powershell
powershell -ExecutionPolicy Bypass -File .\setup-maintenance.ps1
```

macOS/Linux：

```bash
bash setup-maintenance.sh
```

脚本安装可选Python依赖，并从**这份经过审阅的基线代码**构建 `dealerdesk-tests:0.2` 测试镜像。初次构建需联网下载基础镜像与依赖。候选测试时禁止容器联网，禁止访问数据库、密钥、Git元数据、Docker socket，使用非root用户与资源限制。Docker不可用就停止处理，不会偷偷退回宿主机执行AI代码。

不要使用AI候选重建受信任测试镜像。AI不能改测试文件、依赖或镜像脚本。测试镜像的维护是人工操作；长期使用仍须关注依赖安全更新。

## 飞书应用机器人

在飞书开放平台使用企业自建应用，启用机器人能力，允许负责人使用该应用。需要应用身份的发送消息权限 `im:message:send_as_bot`，以及卡片回调 `card.action.trigger`。回调订阅选择长连接（SDK）接收方式，按控制台要求发布应用版本并使配置生效。代码使用官方 `lark-oapi` SDK的WebSocket连接，不提供公网HTTP审批入口。

把App ID、App Secret及负责人在**此应用下的open_id**填写到本机.env。不是姓名、手机号、user_id或union_id。通过平台开发调试工具获取并核对自己的open_id，不能猜测。私聊方式默认发给首位审批人；群方式需要把应用机器人加入专用审批群，并配置群chat_id。不要发到所有员工都能看见的业务群；虽然非白名单人员不能批准，卡片仍包含改动摘要和仓库链接。

```dotenv
MAINTENANCE_ENABLED=true
ALLOW_CODE_EXTERNAL=true
MAINT_REPO_URL=git@YOUR_GIT_HOST:YOUR_ACCOUNT/dealerdesk.git
MAINT_REPO_WEB_URL=https://YOUR_GIT_HOST/YOUR_ACCOUNT/dealerdesk
MAINT_BASE_BRANCH=main
DEEPSEEK_API_KEY=在本机填写
# 可单独设置编码密钥与模型；留空时复用上面的DeepSeek配置。
DEEPSEEK_CODE_API_KEY=
DEEPSEEK_CODE_MODEL=
FEISHU_APP_ID=cli_在本机填写
FEISHU_APP_SECRET=在本机填写
FEISHU_APPROVER_OPEN_IDS=ou_在本机填写负责人ID
FEISHU_RECEIVE_ID_TYPE=open_id
FEISHU_RECEIVE_ID=ou_在本机填写负责人ID
```

群审批改为：

```dotenv
FEISHU_RECEIVE_ID_TYPE=chat_id
FEISHU_RECEIVE_ID=oc_在本机填写群ID
```

多个允许审批的人用英文逗号分隔 `FEISHU_APPROVER_OPEN_IDS`，不需要多个人共同批准，任一白名单成员均可批准。选填 `FEISHU_TENANT_KEY` 可以额外校验租户，填错会阻止审批。不要把任何真实密钥发给聊天助手，也不要提交到Git。

先运行本地检查（在Windows使用 `.venv\Scripts\python.exe`，Linux/macOS使用 `.venv/bin/python`）：

```powershell
.venv\Scripts\python.exe -m maintenance.doctor
# 此命令会真的发送一条无操作按钮的测试消息：
.venv\Scripts\python.exe -m maintenance.doctor --send-test
```

检查只验证字段、SDK/镜像可用和Git读取/基线；不能代替真实写入权限、DeepSeek输出、Docker实际测试及飞书回调的端到端验收。

## 日常使用：仍然一个启动窗口

配置完成后照常运行 `start.ps1` / `start.sh`。不要改用旧版裸uvicorn命令；启动器会拉起业务服务、维护Worker和飞书SDK进程。意见页顶部可查看维护器状态与需要处理的配置问题。

员工提交意见并勾选外发授权，或管理员点击「授权AI处理」。模型每次最多返回12项精确替换，修改总规模上限500行。默认每个UTC自然日最多3次模型请求，每条意见最多3次尝试，避免失败后无限付费重试。预算是请求次数，不是金额上限；费用仍以你使用的模型计费为准。

测试通过后只推送 `dealerdesk/change-编号-次数` 分支。飞书卡片显示基线、候选SHA、改动摘要、文件清单与测试结果；批准或拒绝绑定该SHA及24小时有效随机令牌。模型摘要不能修改按钮动作。重复回调去重，非指定open_id拒绝，旧卡片、已变更分支、过期卡片不能发布。

批准后：核对分支与代码基线 → 导出确切提交 → 临时关闭业务API → 停旧服务 → 一致性备份SQLite → 启新服务并检查版本/数据库连通 → 普通快进Git主分支 → 保存运行版本指针 → 恢复访问 → 发送发布成功卡片。发布期间可能短暂显示维护提示；不承诺零停机。当前健康检查是进程/API/数据库连通与SHA检查，不是完整业务正确性证明。

回滚按钮仅对当前最新部署有效，默认24小时内使用。回滚创建Git revert提交并恢复上一代码树，但绝不覆盖现有数据库。发布后新录入的业务记录继续保留。需长期回滚能力时应另行由维护人员处理，而不是重放过期卡片。

电脑关机、休眠或网络断开时，服务、日报和机器人都无法持续工作；任务状态保存在数据库里，重启后可恢复待审批等状态。生成/测试中断的任务会标失败，不会静默重复计费。飞书掉线时请等SDK重连，卡片点击失败不代表批准成功，以反馈任务状态为准。

## 发生失败时

无法测试、权限错误、Git主分支变化、飞书不通都不会推定为同意。新版启动失败会尝试恢复旧代码；如果Git发布结果因断网无法确定、切换中断、或回滚失败，系统在 `data/maintenance/PAUSED` 留下标记，暂停后续自动发布以免连续扩大故障。

PAUSED不是点一下「忽略」即可安全清除。维护人员要先核对 `.env`、`active.json` 中的运行SHA、Git主分支SHA、反馈日志和备份。若只是确认的健康检查失败且Git仍等于旧基线，修复原因后可以停止服务、保留PAUSED内容作记录、清除该标记再启动；无法确定时不要继续自动覆盖。此机制减少日常操作，不消除异常情况下的人工维护。

本版保存备份和旧版本但不自动清理历史目录。定期检查磁盘，并将SQLite一致性备份加密复制到另一台机器；同盘备份不能防止整机或磁盘损坏。备份包含账号哈希和经营数据，应限制系统账户权限。

## 外部文档

接口文档与SDK按2026-09-18查看，平台权限和控制台名称可能变化：
- 官方SDK：https://github.com/larksuite/oapi-sdk-python
- 飞书卡片回调：https://open.feishu.cn/document/server-side-sdk/python--sdk/handle-callbacks
- 飞书消息发送：https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/im-v1/message/create
- DeepSeek API：https://api-docs.deepseek.com/

## 当前验证边界

本交付环境已测试应用权限、数据迁移、模型输出策略、审批绑定、真实临时Git仓库的候选/发布/revert流程，以及模拟新进程失败的回退。没有你的API凭据、飞书租户和专用仓库，尚未进行真实DeepSeek、飞书消息/SDK长连接审批及实际Docker容器全链路验收。首次启用务必用演示库与「仅调整一个文案/样式」意见完成批准、拒绝和回滚验收后，再用于真实经营系统。
