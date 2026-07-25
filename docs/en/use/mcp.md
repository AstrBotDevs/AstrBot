# MCP

MCP (Model Context Protocol) connects AstrBot Agents to independent tool servers. The current implementation supports stdio, SSE, and Streamable HTTP. Create, test, enable, and remove servers from **Plugins → MCP** in WebUI.

## Choose a Transport

| Transport       | Use case                                                       | Key fields                    |
| --------------- | -------------------------------------------------------------- | ----------------------------- |
| stdio           | AstrBot starts a child process on the host or in its container | `command`, `args`, `env`      |
| Streamable HTTP | Current remote MCP HTTP transport                              | `transport`, `url`, `headers` |
| SSE             | Remote servers that still expose the older SSE transport       | `transport`, `url`, `headers` |

Remote configurations must declare `transport`. A configuration without `url` is treated as stdio.

## Runtime Tools

For source deployments, install the server's launcher in the same environment that runs AstrBot. The repository Dockerfile already includes Node.js 26, npm/npx, pnpm, and uv. Do not follow older instructions that reinstall Node inside an image built from this checkout.

Install host-side server dependencies according to that MCP server's documentation. AstrBot does not interpret `command` through a shell, so do not use `bash -c`, `env ...`, pipes, or redirection.

## stdio Configuration

For example, start a Python MCP package with `uvx`:

```json
{
  "command": "uvx",
  "args": ["arxiv-mcp-server", "--storage-path", "data/arxiv"],
  "env": {
    "ARXIV_API_TOKEN": "replace-with-secret"
  }
}
```

`env` must be a JSON object whose keys and values are strings. Do not use `env` as the command:

```json
{
  "env": {
    "RESOURCE_FROM": "local",
    "API_URL": "https://api.example.com",
    "API_TOKEN": "replace-with-secret"
  }
}
```

Do not expose tokens in screenshots, public issues, or plugin repositories. Reconnect or restart the MCP server after changing its environment.

### stdio Security Rules

The default launcher allowlist is:

- `python`, `python3`, `py`
- `node`, `npx`, `npm`, `pnpm`, `yarn`
- `bun`, `bunx`, `deno`
- `uv`, `uvx`

Shells, PowerShell, `curl`, `wget`, SSH, destructive file commands, and shutdown commands are denied. `command` cannot contain line breaks or shell metacharacters. Python `-c` and JavaScript eval/print modes are also rejected.

Only when you fully trust another launcher should you set `ASTRBOT_MCP_STDIO_ALLOWED_COMMANDS`. It is a comma-separated **replacement list**, not an addition to the defaults:

::: code-group

```bash [Linux / macOS]
export ASTRBOT_MCP_STDIO_ALLOWED_COMMANDS='python,python3,node,npx,uv,uvx,my-launcher'
```

```powershell [Windows PowerShell]
$env:ASTRBOT_MCP_STDIO_ALLOWED_COMMANDS = 'python,python3,node,npx,uv,uvx,my-launcher'
```

:::

Expanding this list allows AstrBot to start more local programs and should be treated as a code-execution permission change.

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

- `timeout` covers connection and ordinary HTTP operations.
- `sse_read_timeout` controls remote stream reads.
- `session_read_timeout` controls MCP session reads.
- `terminate_on_close` asks the remote server to terminate the session when closing.

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

Prefer Streamable HTTP for new services. Choose SSE only when the server explicitly exposes an SSE endpoint.

## Private-Network Protection

Remote MCP rejects localhost, loopback, private, link-local, multicast, reserved, and unspecified addresses by default. HTTP redirects are also rejected. These checks reduce SSRF and redirect-bypass risk.

To connect to a LAN or same-host server that you control, explicitly opt in:

```json
{
  "transport": "streamable_http",
  "url": "http://127.0.0.1:8000/mcp",
  "allow_private_network": true
}
```

> [!WARNING]
> `allow_private_network` bypasses the target-address restriction. Enable it only for a fixed, trusted endpoint. Do not let ordinary users control the URL, headers, or this flag.

Inside a container, `127.0.0.1` refers to the AstrBot container itself. Use a service name such as `http://mcp-server:8000/mcp` for another service on the same Compose network, and still make an explicit trust decision about private-network access.

## Troubleshooting

1. Use the WebUI test action first and inspect connection errors and server stderr.
2. If stdio reports that a command is not allowed, use a supported launcher instead of a shell wrapper.
3. If a command is missing, make sure it is on the AstrBot process's `PATH`; host and container installations are separate.
4. If a remote address is rejected, check whether DNS resolves it to a private range. Enable `allow_private_network` only for a trusted service.
5. 3xx responses are not followed; configure the final MCP endpoint directly.
6. Retest and enable the server after editing it. ModelScope sync enables only successfully synchronized servers.

Reference: [official MCP documentation](https://modelcontextprotocol.io/).
