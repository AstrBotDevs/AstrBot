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

打开「模型提供商」→「对话」，点击「新增」，选择 `LM Studio`。

API Base URL 填写 `http://localhost:1234/v1`

API Key 填写 `lm-studio`

> 对于 Mac/Windows 使用 Docker Desktop 部署 AstrBot 的用户，API Base URL 请填写为 `http://host.docker.internal:1234/v1`。
> 对于 Linux 使用 Docker 部署 AstrBot 的用户，API Base URL 请填写为 `http://172.17.0.1:1234/v1`，或者将 `172.17.0.1` 替换为你的公网 IP（确保宿主机系统放行了 1234 端口）。

如果 LM Studio 使用了 Docker 部署，请确保 1234 端口已经映射到宿主机。

填写提供商名称并确认 `API Base URL`。模板已预填 `API Key` 为 `lmstudio`；如果服务端另有认证要求，请改为实际密钥。点击「保存并获取模型」。在模型列表中点击所需模型右侧的 `+`，确认模型已启用；也可先「保存配置」，再通过「自定义模型」填写准确的模型 ID。点击已配置模型旁的「测试模型」按钮可检查是否可用。

进入「配置文件」，选择要使用的配置文件，在「AI 配置」→「模型」中将「对话模型」设为刚添加的模型，点击右下角「保存配置」。此项用于 AstrBot 内置 AI。

> 输入 /provider 查看 AstrBot 配置的模型
