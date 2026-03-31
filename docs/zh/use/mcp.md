# MCP

MCP(Model Context Protocol，模型上下文协议) 是一种新的开放标准协议，用来在大模型和数据源之间建立安全双向的链接。简单来说，它将函数工具单独抽离出来作为一个独立的服务，AstrBot 通过 MCP 协议远程调用函数工具，函数工具返回结果给 AstrBot。

![image](https://files.astrbot.app/docs/source/images/function-calling/image3.png)

AstrBot v3.5.0 支持 MCP 协议，可以添加多个 MCP 服务器、使用 MCP 服务器的函数工具。

![image](https://files.astrbot.app/docs/source/images/function-calling/image2.png)

## 初始状态配置

MCP 服务器一般使用 `uv` 或者 `npm` 来启动，因此您需要安装这两个工具。

对于 `uv`，您可以直接通过 pip 来安装。可在 AstrBot WebUI 快捷安装：

![image](https://files.astrbot.app/docs/zh/use/image.png)

输入 `uv` 即可。

如果您使用 Docker 部署 AstrBot，也可以执行以下指令快捷安装。

```bash
docker exec astrbot python -m pip install uv
```

如果您通过源码部署 AstrBot，请在创建的虚拟环境内安装。

对于 `npm`，您需要安装 `node`。

如果您通过源码/一键安装部署 AstrBot，请参考 [Download Node.js](https://nodejs.org/en/download) 下载到您的本机。

如果您使用 Docker 部署 AstrBot，您需要在容器中安装 `node`（后期 AstrBot Docker 镜像将自带 `node`），请参考执行以下指令：

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

安装好 `node` 之后，需要重启 `AstrBot` 以应用新的环境变量。

## 安装 MCP 服务器

如果您使用 Docker 部署 AstrBot，请将 MCP 服务器安装在 data 目录下。

### 一个例子

我想安装一个查询 Arxiv 上论文的 MCP 服务器，发现了这个 Repo: [arxiv-mcp-server](https://github.com/blazickjp/arxiv-mcp-server)，参考它的 README，

我们抽取出需要的信息：

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

如果要使用的 MCP 服务器需要通过环境变量配置 Token 等信息，可以使用 `env` 这个工具：

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

在 AstrBot WebUI 中设置:

![image](https://files.astrbot.app/docs/zh/use/image-2.png)

即可。

## MCP Client 子能力

AstrBot 现在支持按服务开启 MCP Client 子能力。当前首个接入的子能力是 `sampling`，它允许 MCP Server 在工具调用过程中向 AstrBot 发起 `sampling/createMessage` 请求，并复用当前 Bot 的聊天模型、人格上下文与会话来源。

目前也支持按服务开启 `elicitation`。启用后，MCP Server 可以在工具调用过程中向当前用户追问缺失信息，或要求用户完成一个外部确认步骤，再继续当前 MCP 交互。

目前也支持按服务开启 `roots`。启用后，MCP Server 可以通过 `roots/list` 请求 AstrBot 暴露给它的文件根目录列表。

您可以在对应 MCP Server 配置中加入：

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

当前版本的限制：

- `elicitation` 默认关闭，只有显式配置 `enabled: true` 的服务器才会声明该能力。
- `elicitation.timeout_seconds` 用于限制等待用户回复的总时长；超时后当前 elicitation 会以 `cancel` 结束。
- `elicitation` 当前只在对应 MCP Server 正在为当前 Bot 执行工具调用时可用；脱离当前交互上下文的请求会被拒绝。
- `elicitation` 当前通过聊天消息交互，不提供独立表单 UI。
- `elicitation` 的 form 模式当前支持顶层简单字段：`string`、`integer`、`number`、`boolean`、`array[string]`。
- `elicitation` 的 form 模式在单字段时可直接回复纯文本，多字段时可回复 JSON 或 `field: value` 形式。
- `elicitation` 的 url 模式当前会把 URL 和提示文本发送给用户，并等待用户在聊天中回复 `done` / `decline` / `cancel` 之类的确认。
- 开启 `elicitation` 的影响范围仅限对应的 MCP Server，不会改变其他 MCP Server 或普通聊天流程。
- `sampling` 默认关闭，只有显式配置 `enabled: true` 的服务器才会声明该能力。
- `roots` 默认关闭，只有显式配置 `enabled: true` 的服务器才会声明该能力。
- `roots.paths` 可填写内置别名（如 `data`、`temp`、`config`、`skills`、`plugins`、`plugin_data`、`knowledge_base`、`backups`、`root`）、绝对路径，或相对 AstrBot 根目录的路径。
- 当 `roots.enabled` 为 `true` 且未显式填写 `paths` 时，AstrBot 当前默认暴露 `data` 和 `temp`。
- `sampling` 仅在该 MCP Server 正在为当前 Bot 执行工具调用时可用；脱离当前交互上下文的请求会被拒绝。
- 当前版本仅支持文本采样结果。
- 当前版本不支持带工具的 sampling，也不支持图片、音频等多模态 sampling 输入。
- 开启 `sampling` 的影响范围仅限对应的 MCP Server，不会改变其他 MCP Server 或普通聊天流程。
- 开启 `roots` 的影响范围仅限对应的 MCP Server，不会改变其他 MCP Server 或普通聊天流程。

## stdio 服务输出说明

使用 stdio 方式接入 MCP Server 时，服务器应当只通过标准输出（stdout）发送 JSON-RPC 协议消息，并将日志写入标准错误（stderr）。

AstrBot 当前会尽量忽略空行以及 `npm run` 一类启动器输出的非协议横幅，减少测试时的噪声；但这只是兼容处理，不建议依赖。更稳妥的做法仍然是让 MCP Server 或启动脚本保持 stdout 干净。

## MCP Resources 桥接

如果某个 MCP Server 在初始化时声明了 `resources` 能力，AstrBot 会自动为它注册一组桥接工具，让 Bot 通过现有的工具调用流程与资源交互。

当前首版会按服务注册这些工具：

- `mcp_<server>_list_resources`
- `mcp_<server>_read_resource`
- `mcp_<server>_list_resource_templates`（仅在服务支持模板列表时出现）

这意味着 Bot 可以先列出资源，再读取某个具体 URI 的内容，而不需要修改普通聊天流程或额外配置 Provider。

当前版本的限制：

- 当前只做只读桥接，不支持 `resources/subscribe` 订阅与推送刷新。
- 当前不会自动把 MCP 资源注入提示词上下文，仍然需要 Bot 通过工具主动读取。
- 单个文本资源会直接作为文本结果返回。
- 单个图片 Blob 资源会按图片结果处理。
- 多段资源、混合类型资源以及非图片二进制资源，当前会被整理为文本摘要返回。

## MCP Prompts 桥接

如果某个 MCP Server 在初始化时声明了 `prompts` 能力，AstrBot 也会自动为它注册一组桥接工具，让 Bot 通过现有的工具调用流程查看和获取 MCP prompt。

当前首版会按服务注册这些工具：

- `mcp_<server>_list_prompts`
- `mcp_<server>_get_prompt`

这意味着 Bot 可以先列出可用 prompt，再按名称和参数获取某个 prompt 的展开结果，而不需要修改普通聊天流程或额外配置 Provider。

当前版本的限制：

- 当前不会自动把 MCP prompt 注入对话上下文，仍然需要 Bot 通过工具主动获取。
- `get_prompt` 的结果当前会整理为文本摘要，保留描述、消息角色和文本内容。
- 图片、音频、嵌入资源等非纯文本 prompt block，当前会被总结为文本说明，而不是直接转成多模态上下文。
- 当前不支持 `prompts/list_changed` 推送刷新，也不支持通过 MCP completion 自动补全 prompt 参数。

参考链接：

1. 在这里了解如何使用 MCP: [Model Context Protocol](https://modelcontextprotocol.io/introduction)
2. 在这里获取常用的 MCP 服务器: [awesome-mcp-servers](https://github.com/punkpeye/awesome-mcp-servers/blob/main/README-zh.md#what-is-mcp), [Model Context Protocol servers](https://github.com/modelcontextprotocol/servers), [MCP.so](https://mcp.so)
