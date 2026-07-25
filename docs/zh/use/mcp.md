# MCP

MCP（Model Context Protocol）让 AstrBot Agent 连接独立的工具服务。当前实现支持 stdio、SSE 和 Streamable HTTP 三种传输方式；可以在 WebUI 的 **插件 → MCP** 页面创建、测试、启用和删除服务器。

## 选择传输方式

| 方式            | 适用场景                             | 关键字段                      |
| --------------- | ------------------------------------ | ----------------------------- |
| stdio           | AstrBot 在本机或容器中启动一个子进程 | `command`、`args`、`env`      |
| Streamable HTTP | 当前推荐的远程 MCP HTTP 传输         | `transport`、`url`、`headers` |
| SSE             | 仍使用旧 SSE 传输的远程服务          | `transport`、`url`、`headers` |

远程配置必须显式提供 `transport`。如果配置中没有 `url`，AstrBot 会把它视为 stdio 配置。

## 运行时工具

源码部署需要在运行 AstrBot 的同一环境中安装服务器所需的 launcher。仓库 `Dockerfile` 已包含 Node.js 26、npm/npx、pnpm 和 uv；使用当前仓库本地构建的镜像时，不要再按旧教程在容器里重复安装 Node。

主机源码部署可按 MCP 服务器自身文档安装依赖。AstrBot 不会通过 shell 解释 `command`，因此不要写 `bash -c`、`env ...`、管道或重定向。

## stdio 配置

例如用 `uvx` 启动一个 Python MCP 包：

```json
{
  "command": "uvx",
  "args": ["arxiv-mcp-server", "--storage-path", "data/arxiv"],
  "env": {
    "ARXIV_API_TOKEN": "replace-with-secret"
  }
}
```

`env` 必须是字符串到字符串的 JSON object，不能把 `env` 写成 `command`：

```json
{
  "env": {
    "RESOURCE_FROM": "local",
    "API_URL": "https://api.example.com",
    "API_TOKEN": "replace-with-secret"
  }
}
```

不要把 Token 放到截图、公开 issue 或插件仓库。修改环境变量后，重新连接或重启对应 MCP 服务器。

### stdio 安全限制

默认允许的 launcher 为：

- `python`、`python3`、`py`
- `node`、`npx`、`npm`、`pnpm`、`yarn`
- `bun`、`bunx`、`deno`
- `uv`、`uvx`

shell、PowerShell、`curl`、`wget`、SSH、文件删除和关机类命令会被拒绝。`command` 不能包含换行或 shell 元字符；Python `-c`、JavaScript eval/print 模式也被禁止。

只有在你完全信任另一个 launcher 时，才设置进程环境变量 `ASTRBOT_MCP_STDIO_ALLOWED_COMMANDS`。它是用逗号分隔的**完整替代列表**，不是在默认列表上追加：

::: code-group

```bash [Linux / macOS]
export ASTRBOT_MCP_STDIO_ALLOWED_COMMANDS='python,python3,node,npx,uv,uvx,my-launcher'
```

```powershell [Windows PowerShell]
$env:ASTRBOT_MCP_STDIO_ALLOWED_COMMANDS = 'python,python3,node,npx,uv,uvx,my-launcher'
```

:::

扩大白名单会允许 AstrBot 启动更多本机程序，应把它视为代码执行权限变更。

## Streamable HTTP

```json
{
  "transport": "streamable_http",
  "url": "https://mcp.example.com/mcp",
  "allow_private_network": false,
  "headers": {
    "Authorization": "Bearer replace-with-secret"
  },
  "timeout": 5,
  "sse_read_timeout": 300,
  "session_read_timeout": 60,
  "terminate_on_close": true
}
```

- `timeout` 是建立连接/普通 HTTP 操作超时。
- `sse_read_timeout` 是远程流读取超时。
- `session_read_timeout` 是 MCP session 读取超时。
- `terminate_on_close` 控制关闭连接时是否请求远端终止 session。

## SSE

```json
{
  "transport": "sse",
  "url": "https://mcp.example.com/sse",
  "allow_private_network": false,
  "headers": {},
  "timeout": 5,
  "sse_read_timeout": 300,
  "session_read_timeout": 60
}
```

新服务优先使用 Streamable HTTP；只有服务端明确提供 SSE endpoint 时才选择 SSE。

## 私网访问保护

远程 MCP 默认拒绝 `localhost`、loopback、私网、链路本地、multicast、保留地址和未指定地址，并拒绝 HTTP 重定向。这可以减少 SSRF 和重定向绕过风险。

连接你自己控制的局域网或同机 MCP 服务时，必须显式选择放开：

```json
{
  "transport": "streamable_http",
  "url": "http://127.0.0.1:8000/mcp",
  "allow_private_network": true
}
```

> [!WARNING]
> `allow_private_network` 会跳过目标地址的私网限制。只对固定且可信的 endpoint 开启；不要让普通用户控制 `url`、headers 或此开关。

容器中的 `127.0.0.1` 指向 AstrBot 容器本身。连接同一 Compose 网络中的服务时，应使用服务名，例如 `http://mcp-server:8000/mcp`，并同样显式评估是否开启私网访问。

## 故障排查

1. 先在 WebUI 中点击测试，查看连接错误和服务器 stderr。
2. stdio 报 “command is not allowed” 时，确认使用的是默认 launcher，而不是 shell wrapper。
3. stdio 找不到命令时，确认 launcher 安装在 AstrBot 进程的 `PATH` 中；容器内安装和宿主机安装互不相通。
4. 远程地址被拒绝时，先确认它是否解析到私网；只有可信服务才开启 `allow_private_network`。
5. 3xx 响应不会被跟随，请直接填写最终 MCP endpoint。
6. 修改配置后重新测试并启用服务器；ModelScope 同步只会启用成功同步的服务。

参考：[MCP 官方文档](https://modelcontextprotocol.io/)。
