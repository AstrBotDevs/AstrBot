
# MCP

MCP (Model Context Protocol) is a new open standard protocol for establishing secure bidirectional connections between large language models and data sources. Simply put, it extracts function tools as independent services, allowing AstrBot to remotely invoke these function tools via the MCP protocol, which then return results to AstrBot.

![image](https://files.astrbot.app/docs/source/images/function-calling/image3.png)

AstrBot v3.5.0 supports the MCP protocol, enabling you to add multiple MCP servers and use function tools from MCP servers.

![image](https://files.astrbot.app/docs/source/images/function-calling/image2.png)

## Initial Configuration

MCP servers are typically launched using `uv` or `npm`, so you need to install these two tools.

For `uv`, you can install it directly via pip. Quick installation via AstrBot WebUI:

![image](https://files.astrbot.app/docs/en/use/image.png)

Just enter `uv`.

If you're deploying AstrBot with Docker, you can also execute the following command for quick installation:

```bash
docker exec astrbot python -m pip install uv
```

If you're deploying AstrBot from source, please install it within the created virtual environment.

For `npm`, you need to install `node`.

If you're deploying AstrBot from source or using one-click installation, please refer to [Download Node.js](https://nodejs.org/en/download) to download to your local machine.

If you're using Docker to deploy AstrBot, you need to install `node` in the container (future AstrBot Docker images will include `node` by default). Please execute the following commands:

```bash
sudo docker exec -it astrbot /bin/bash
apt update && apt install curl -y
export NVM_NODEJS_ORG_MIRROR=http://nodejs.org/dist
# Download and install nvm:
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.2/install.sh | bash
\. "$HOME/.nvm/nvm.sh"
nvm install 22
# Verify version:
node -v
nvm current
npm -v
npx -v
```

After installing `node`, you need to restart `AstrBot` to apply the new environment variables.

## Installing MCP Servers

If you're deploying AstrBot with Docker, please install MCP servers in the data directory.

### An Example

I want to install an MCP server for querying papers on Arxiv and found this repository: [arxiv-mcp-server](https://github.com/blazickjp/arxiv-mcp-server). Referring to its README,

We extract the necessary information:

```json
{
    "command": "uv",
    "args": [
        "tool",
        "run",
        "arxiv-mcp-server",
        "--storage-path", "data/arxiv"
    ]
}
```

If the MCP server you need requires environment variables to configure something (e.g. access token), you could use the command-line tool `env`:

```json
{
    "command": "env",
    "args": [
        "XXX_RESOURCE_FROM=local",
        "XXX_API_URL=https://xxx.com",
        "XXX_API_TOKEN=sk-xxxxx",
        "uv",
        "tool",
        "run",
        "xxx-mcp-server",
        "--storage-path", "data/res"
    ]
}
```

Configure it in the AstrBot WebUI:

![image](https://files.astrbot.app/docs/en/use/image-2.png)

That's it.

## MCP Client Sub-Capabilities

AstrBot now supports enabling MCP client sub-capabilities per server. The first integrated sub-capability is `sampling`, which allows an MCP server to send `sampling/createMessage` requests during a tool call and reuse the current bot's chat provider, persona context, and session origin.

AstrBot also supports per-server `elicitation`. When enabled, an MCP server can ask the current user for missing input or require an external confirmation step while the current MCP tool call is still in progress.

AstrBot also supports per-server `roots`. When enabled, an MCP server can call `roots/list` to learn which local file roots AstrBot is explicitly exposing to it.

You can add the following to an MCP server configuration:

```json
{
    "url": "https://example.com/mcp",
    "transport": "sse",
    "client_capabilities": {
        "elicitation": {
            "enabled": true,
            "timeout_seconds": 300
        },
        "sampling": {
            "enabled": true
        },
        "roots": {
            "enabled": true,
            "paths": ["data", "temp"]
        }
    }
}
```

Current limitations:

- `elicitation` is disabled by default and is only advertised for servers that explicitly set `enabled: true`.
- `elicitation.timeout_seconds` bounds the total time AstrBot waits for the user's reply; timeouts are returned as `cancel`.
- `elicitation` is only available while the MCP server is actively serving the current bot tool call; requests outside the active interaction context are rejected.
- `elicitation` currently uses plain chat messages instead of a dedicated form UI.
- Form-mode elicitation currently supports flat top-level fields with simple types: `string`, `integer`, `number`, `boolean`, and `array[string]`.
- For single-field form elicitation, the user can reply with plain text. For multi-field form elicitation, AstrBot accepts JSON or `field: value` lines.
- URL-mode elicitation currently sends the URL and instructions to the user, then waits for a chat reply such as `done`, `decline`, or `cancel`.
- Enabling `elicitation` only affects the configured MCP server and does not change other MCP servers or standard chat flows.
- `sampling` is disabled by default and is only advertised for servers that explicitly set `enabled: true`.
- `roots` is disabled by default and is only advertised for servers that explicitly set `enabled: true`.
- `roots.paths` can contain built-in aliases such as `data`, `temp`, `config`, `skills`, `plugins`, `plugin_data`, `knowledge_base`, `backups`, and `root`, as well as absolute paths or paths relative to AstrBot root.
- If `roots.enabled` is `true` and `paths` is omitted, AstrBot currently exposes `data` and `temp` as the default safe roots.
- `sampling` is only available while the MCP server is actively serving the current bot tool call; requests outside the active interaction context are rejected.
- The initial implementation only returns text sampling results.
- Tool-assisted sampling and multimodal sampling inputs such as image or audio are not supported yet.
- Enabling `sampling` only affects the configured MCP server and does not change other MCP servers or standard chat flows.
- Enabling `roots` only affects the configured MCP server and does not change other MCP servers or standard chat flows.

## Notes for stdio servers

When using an MCP server over stdio, the server should reserve stdout for JSON-RPC protocol messages and write logs to stderr.

AstrBot now tolerates blank lines and common launcher banners such as `npm run` output to reduce noise during local testing, but that behavior is only a compatibility fallback. The robust setup is still to keep stdout protocol-only.

## MCP Resources Bridge

If an MCP server advertises the `resources` capability during initialization, AstrBot now registers a small set of bridge tools so the bot can interact with those resources through the existing tool loop.

The first iteration exposes these server-scoped tools:

- `mcp_<server>_list_resources`
- `mcp_<server>_read_resource`
- `mcp_<server>_list_resource_templates` (only when the server supports listing resource templates)

This lets the bot discover available resources and read a specific resource URI without changing the normal chat flow or provider integration.

Current limitations:

- The bridge is read-only and does not support `resources/subscribe` push updates yet.
- AstrBot does not auto-inject MCP resources into prompt context; the bot still needs to read them explicitly through tools.
- A single text resource is returned as text.
- A single image blob resource is returned as an image-style tool result.
- Multi-part resources, mixed results, and non-image binary blobs are summarized into text in the first iteration.

## MCP Prompts Bridge

If an MCP server advertises the `prompts` capability during initialization, AstrBot also registers a small set of bridge tools so the bot can discover and fetch MCP prompts through the existing tool loop.

The first iteration exposes these server-scoped tools:

- `mcp_<server>_list_prompts`
- `mcp_<server>_get_prompt`

This lets the bot inspect available prompt templates and resolve a specific prompt by name with optional arguments, without changing the normal chat flow or provider integration.

Current limitations:

- AstrBot does not auto-inject MCP prompts into the active chat context; the bot still needs to fetch them explicitly through tools.
- `get_prompt` results are currently summarized into text, preserving descriptions, message roles, and text blocks.
- Non-text prompt blocks such as images, audio, and embedded resources are summarized into text in the first iteration instead of being converted into multimodal context.
- The bridge does not support `prompts/list_changed` push updates yet, and it does not use MCP completions to auto-complete prompt arguments.

Reference links:

1. Learn how to use MCP here: [Model Context Protocol](https://modelcontextprotocol.io/introduction)
2. Get commonly used MCP servers here: [awesome-mcp-servers](https://github.com/punkpeye/awesome-mcp-servers/blob/main/README-zh.md#what-is-mcp), [Model Context Protocol servers](https://github.com/modelcontextprotocol/servers), [MCP.so](https://mcp.so)
