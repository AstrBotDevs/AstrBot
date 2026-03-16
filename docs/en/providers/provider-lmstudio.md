# 接入 LM Studio 使用 DeepSeek-R1 等模型

LMStudio 允许在本地电脑上部署模型（需要电脑硬件配置符合要求）

### 下载并安装 LMStudio

https://lmstudio.ai/download

### 下载并运行模型

https://lmstudio.ai/models

跟随 LMStudio 下载并运行想要的模型，如 deepseek-r1-qwen-7b:

```bash
lms get deepseek-r1-qwen-7b
```

### 配置 AstrBot

在 AstrBot 上：

点击 配置->服务提供商配置->加号->openai

API Base URL 填写 `http://localhost:1234/v1`

API Key 填写 `lm-studio`

> 对于 Mac/Windows 使用 Docker Desktop 部署 AstrBot 部署的用户，API Base URL 请填写为 `http://host.docker.internal:1234/v1`。
> 对于 Linux 使用 Docker 部署 AstrBot 部署的用户，API Base URL 请填写为 `http://172.17.0.1:1234/v1`，或者将 `172.17.0.1` 替换为你的公网 IP IP（确保宿主机系统放行了 1234 端口）。

如果 LM Studio 使用了 Docker 部署，请确保 1234 端口已经映射到宿主机。

模型名填写上一步选好的

保存配置即可。

> 输入 /provider 查看 AstrBot 配置的模型