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

## OAuth 2.0 MCP 服务器

对于需要 OAuth 2.0 的远程 MCP Server，AstrBot 现在支持在 WebUI 中直接完成授权登录。

一个典型的 HTTP MCP 配置如下：

```json
{
    "transport": "streamable_http",
    "url": "https://example.com/mcp",
    "headers": {},
    "timeout": 5,
    "sse_read_timeout": 300,
    "oauth2": {
        "grant_type": "authorization_code",
        "client_name": "AstrBot MCP Client"
    }
}
```

如果服务端使用预先分配的客户端凭据，也可以改为 `client_credentials`：

```json
{
    "transport": "streamable_http",
    "url": "https://example.com/mcp",
    "oauth2": {
        "grant_type": "client_credentials",
        "client_id": "your-client-id",
        "client_secret": "your-client-secret",
        "scope": "read write"
    }
}
```

在 WebUI 的 MCP 服务器弹窗中：

1. 填写带有 `oauth2` 字段的 JSON 配置。
2. 点击 `OAuth 2.0 登录`。
3. 在新打开的授权页面完成登录。
4. 返回 AstrBot，等待状态显示授权完成后再测试连接或保存。

参考链接：

1. 在这里了解如何使用 MCP: [Model Context Protocol](https://modelcontextprotocol.io/introduction)
2. 在这里获取常用的 MCP 服务器: [awesome-mcp-servers](https://github.com/punkpeye/awesome-mcp-servers/blob/main/README-zh.md#what-is-mcp), [Model Context Protocol servers](https://github.com/modelcontextprotocol/servers), [MCP.so](https://mcp.so)
