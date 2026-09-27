> 2026-09-27 清理注：本文保留版本设计与历史验收口径；文中测试脚本、入口和证据已移至仓库外 `E:/HuaKangOS-cleanup-20260927-082922/removed`，需恢复后使用，历史数字不代表本次清理验收。

# R4-B1 本地 MCP 接入说明

内置 DeepSeek 的一键评测 **不需要执行本页**。只有将同一套业务能力接到支持本地 stdio MCP 的可信客户端时，才用这个入口。

## 1. 先启动独立测试系统

使用项目原来的启动/部署方式，配置独立合成数据，不要指向公司正式库。此 MCP 适配器不启动、不初始化数据库，也不保存 DeepSeek 密钥。

本版固定 tools-only `2025-11-25` 协议。必须使用能协商该版本的客户端；未声称支持任何特定第三方客户端或新版无状态协议。

## 2. 普通员工登录

在已安装项目依赖的 Python 环境运行：

```text
python scripts/configure_business_mcp.py
```

输入独立系统地址、员工登录名、隐藏输入的密码和门店编号。地址只能是 HTTP 回环地址或 HTTPS 根地址，不接受附带用户名/密码、路径、查询、片段或重定向。门店和账号由原系统重新校验；有初始密码修改要求时先在原界面完成。

程序创建一个普通助手对话，保存登录会话和 CSRF 信息到项目外本机私密配置：Windows 默认 `%LOCALAPPDATA%\huakangos-mcp\session.json`；其他环境默认 `~/.config/huakangos-mcp/session.json`。配置不放进项目、报告或 Git；密码不保存。POSIX 使用本人读写权限；Windows 依赖个人配置目录的实际 ACL，未单独完成原生 Windows ACL 审计。

**这个文件是原账号的登录凭据，具备该员工原有会话权限，不是额外的最小权限 token。** 只放在可信本机，不上传、不截图、不共享。客户端若不可信，不应接入。过期后重新运行配置脚本；不会保存密码自动续期。

## 3. 客户端配置

上一步会输出你本机的 Python、脚本、配置文件的绝对路径。把其 JSON 填进客户端的本地 MCP 配置。示意如下（不要原样照抄占位路径）：

```json
{
  "mcpServers": {
    "huakangos": {
      "command": "<已安装依赖的Python绝对路径>",
      "args": ["<独立R4项目绝对路径>/scripts/huakangos_mcp.py"],
      "env": {"HUAKANGOS_MCP_CONFIG": "<本机项目外session.json绝对路径>"}
    }
  }
}
```

客户端是否支持这一配置外层格式由其产品决定；核心是以该命令启动 stdio 子进程，协商 2025-11-25 协议。不要把 API key 直接写入这些参数。

可以查询原单、查当前动作、准备草稿和保存计划。准备后，用相同员工账号和门店在 HuaKangOS 业务助手历史中打开 **“MCP业务工具独立对话”** 核对确认。MCP 不提供确认工具；它也不能通过工具参数换人、换门店、执行命令、读任意文件或连接任意地址。

## 4. 失败与退出

登录过期或权限不足会返回错误，不声称没有业务。等待超时可能已有部分草稿；先回原对话刷新，不能盲目重发。适配器不自动重试，stdin 关闭后退出。单调用同步处理，暂不支持调用进行中的协议取消；异常/终止后仍以原卡状态核对。

这不是可直接公网发布的远程 MCP 服务。远程 HTTP、OAuth、多租户授权和外部正式客户端兼容要单独实施、测试。

## 5. 协议依据

以下官方文档是实现所参考的协议版本，不表示通过了官方认证：

- https://modelcontextprotocol.io/specification/2025-11-25/basic/transports
- https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle
- https://modelcontextprotocol.io/specification/2025-11-25/server/tools

离线协议与真实进程集成测试：`python scripts/check_assistant_mcp.py`。该脚本使用合成原系统与自己的测试客户端，不调用外部大模型。
