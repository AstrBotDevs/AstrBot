# MCP

AstrBot uses MCP Python SDK 2.x and the fixed MCP `2026-07-28` protocol to connect independent tool servers. Create, test, enable, inspect catalogs, and remove servers in **Plugins → MCP**.

Only stdio and Streamable HTTP are supported. SSE, the `initialize`/session handshake, legacy protocol fallback, and their former timeout settings have been removed. A server that only supports an older protocol is explicitly rejected.

## Configuration

Configuration is strict: unknown fields are rejected. Remote servers must declare `transport: "streamable_http"`, and exactly one of `url` and `command` is required.

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

The default allowlist contains `python`, `python3`, `py`, Node/Bun/Deno launchers, and `uv`/`uvx`. Shells, PowerShell, downloaders, SSH, destructive commands, and inline Python/JavaScript are rejected. Set `ASTRBOT_MCP_STDIO_ALLOWED_COMMANDS` only when you fully trust another launcher; it is a complete replacement allowlist.

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

`headers` are write-only secrets: server-list responses never return their values. Editing without submitting headers preserves stored values; submit `{}` explicitly to clear them. Never expose tokens in screenshots, issues, or plugin repositories.

Remote MCP performs DNS/IP checks for every new connection and request. It rejects localhost, loopback, private, link-local, multicast, reserved, and unspecified addresses by default, and never follows HTTP redirects. Set `allow_private_network: true` only for a fixed LAN endpoint you trust.

## Catalogs and calls

AstrBot pages through tools, resources, resource templates, and prompts. A repeated cursor or excessive page count rejects that refresh and preserves the previous atomic catalog snapshot. `subscriptions/listen` catalog notifications fully refresh the relevant catalog while retaining each Dashboard tool enable/disable state. Catalog subscription is optional: if a server rejects it because of a quota, the initial catalog and connection remain usable; a Dashboard connection test does not open a catalog subscription.

Calls use a per-server concurrency limit and pass the configured read timeout to the SDK. If a connection is interrupted, AstrBot rebuilds the Client and refreshes catalogs, but **never automatically replays** a tool call that might already have run remotely.

Resources and prompts are untrusted external content. They are read or fetched only after an explicit Dashboard action, are labeled with their MCP server source, and are never automatically injected into model context or auto-invoked by a model. Dashboard displays rich content as safe plain/structured data.

## User input and OAuth

An MCP server may request user input while running a tool, resource, or prompt operation. Form requests use a restricted flat JSON Schema and cannot collect passwords, tokens, API keys, or payment credentials. Replies are bound to the original message, run, request, and server, so another user cannot answer. URL requests show their scheme and host and open only after user confirmation; AstrBot never returns an external form secret to MCP.

Protected Streamable HTTP servers can set `auth_ref`. AstrBot uses OAuth 2.1, PKCE, state, issuer/resource-metadata validation, and the SDK `OAuthClientProvider`. Tokens, refresh tokens, and client-registration data are stored with owner-only permissions in `data/mcp_auth.json`, never in `data/mcp_server.json`, and are never returned by APIs or logs. Dashboard exposes authorization start, safe status, and local revoke actions.

This MCP Core work does not implement Tasks, MCP Apps, or other protocol extensions.

Reference: [MCP 2026-07-28 specification](https://modelcontextprotocol.io/specification/2026-07-28).
