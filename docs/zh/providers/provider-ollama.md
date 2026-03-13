# 接入 Ollama

🦙 Ollama 是一款免费、开源的应用程序，让您能在自己的电脑上运行大型语言模型（LLM）。（硬件需满足要求）

## 下载并安装 Ollama

您可以在 [https://ollama.com](https://ollama.com/download) 下载 Ollama。

## 选择想要使用的模型

在 https://ollama.com/search 上选择想要使用的模型。

在终端上 (Windows 上是 Powershell) 输入 `ollama pull <model_name>` 下载模型。

model_name 格式：`<model_name>:<model_version>`。如 `deepseek-r1:8b`。

> 8b 参数量模型需要至少 16GB 显存。有关配置和参数量的详细信息，请参阅其他文档。

拉取完成后，输入 `ollama list` 查看已经拉取的模型。

然后使用 `ollama run <model_name>` 运行模型。

## 配置 AstrBot

打开 AstrBot 控制台 -> 服务提供商页面，点击新增模型提供商，找到并点击 `Ollama`。
![image](https://files.astrbot.app/docs/source/images/ollama/image.png)

保存配置即可。

::: tip

对于 Mac/Windows 使用 Docker Desktop 部署 AstrBot 部署的用户，API Base URL 请填写为 `http://host.docker.internal:11434/v1`。\
对于 Linux 使用 Docker 部署 AstrBot 部署的用户，API Base URL 请填写为 `http://172.17.0.1:11434/v1`，或者将 `172.17.0.1` 替换为你的公网 IP（确保宿主机系统放行了 11434 端口）。\
如果 Ollama 使用了 Docker 部署，请确保 11434 端口已经映射到宿主机。

:::


## FAQ

报错：
```
AstrBot 请求失败。
错误类型: NotFoundError
错误信息: Error code: 404 - {'error': {'message': 'model "llama3.1-8b" not found, try pulling it first', 'type': 'api_error', 'param': None, 'code': None}}
```

请先看上面的教程，用 `ollama pull <model_name>` 拉取模型，然后使用 `ollama run <model_name>` 运行模型。
