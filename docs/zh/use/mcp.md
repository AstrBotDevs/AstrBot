# MCP

AstrBot 使用 MCP Python SDK 2.x，以固定的 MCP `2026-07-28` 协议连接独立工具服务。在 WebUI 的 **插件 → MCP** 页面可以创建、测试、启用、查看目录和删除服务器。

支持的传输只有 stdio 和 Streamable HTTP。SSE、`initialize`/session 握手、旧协议探测回退及其旧超时字段已移除；只提供旧协议的服务会被明确拒绝。

## 配置

配置是严格对象，未知字段会被拒绝。远程服务必须指定 `transport: "streamable_http"`，并且 `url` 与 `command` 恰好选一个。

### stdio

```json
{
  "transport": "stdio",
  "command": "uvx",
  "args": ["arxiv-mcp-server", "--storage-path", "data/arxiv"],
  "env": { "ARXIV_API_TOKEN": "replace-with-secret" },
  "read_timeout_seconds": 60
}
```

默认只允许 `python`、`python3`、`py`、Node/Bun/Deno 启动器及 `uv`/`uvx`。shell、PowerShell、下载器、SSH、破坏性命令和 inline Python/JavaScript 均被拒绝。只有完全信任另一个 launcher 时，才可设置进程环境变量 `ASTRBOT_MCP_STDIO_ALLOWED_COMMANDS` 为完整替代白名单。

### Streamable HTTP

```json
{
  "transport": "streamable_http",
  "url": "https://mcp.example.com/mcp",
  "headers": { "Authorization": "Bearer replace-with-secret" },
  "allow_private_network": false,
  "connect_timeout_seconds": 15,
  "read_timeout_seconds": 60,
  "terminate_on_close": true,
  "auth_ref": "work-oauth"
}
```

`headers` 为写入型秘密：服务器列表不会返回其值，编辑未提交 headers 时会保留已有秘密；显式提交 `{}` 才会清除它们。不要在截图、issue 或插件仓库中公开 token。

远程 MCP 会在每次新连接和请求前检查 DNS/IP。默认拒绝 localhost、loopback、私网、链路本地、multicast、保留和未指定地址，且永不跟随 HTTP 重定向。仅在连接固定且可信的局域网服务时才设置 `allow_private_network: true`。

## 目录与调用

AstrBot 分页获取 tools、resources、resource templates 和 prompts；遇到重复 cursor 或过多页会拒绝该次更新，保留原子目录快照。`subscriptions/listen` 的目录变更会完整刷新对应目录，工具的启用/禁用状态会保留。目录订阅是可选的：服务端因配额拒绝订阅时，初始发现到的目录和连接仍可继续使用；Dashboard 的连接测试不会打开目录订阅。

工具调用受每服务器并发限制，读取超时传给 SDK。连接中断时会重建 Client 并刷新目录，但**绝不会自动重放**可能已在远端执行的工具调用。

资源和 Prompt 是不可信的外部内容：它们只在用户通过 Dashboard 明确选择后读取/获取，带有 MCP server 来源，绝不会自动注入模型上下文或作为模型自动工具。Dashboard 以安全的普通文本/结构化数据方式显示富文本。

## 用户输入与 OAuth

MCP 服务可在工具、资源或 Prompt 操作中请求用户输入。表单请求只接受受限的扁平 JSON Schema，不能收集 password、token、API key 或支付凭据；回复与原始消息、run、request 和 server 绑定，其他用户不能回答。URL 请求只显示其 scheme/host，用户确认后才在浏览器打开，AstrBot 不会把外部表单秘密回传给 MCP。

受保护的 Streamable HTTP 服务可配置 `auth_ref`。AstrBot 使用 OAuth 2.1、PKCE、state、issuer/resource metadata 校验和 SDK 的 `OAuthClientProvider`。token、refresh token 和 client registration 信息储存在权限为 owner-only 的 `data/mcp_auth.json`，不存入 `data/mcp_server.json`，也不会通过 API 或日志返回。Dashboard 提供启动授权、状态与本地撤销操作。

本次 MCP Core 范围不包含 Tasks、MCP Apps 或其他协议扩展。

参考：[MCP 2026-07-28 规范](https://modelcontextprotocol.io/specification/2026-07-28)。
