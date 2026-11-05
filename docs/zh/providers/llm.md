# 大语言模型提供商

在 WebUI 的「模型提供商」→「对话」中点击「新增」，选择模型服务类型。兼容 OpenAI API 的服务可选择 `OpenAI Compatible`，并填写服务商提供的 API Base URL 和 API Key。

填写提供商名称和 `API Key`，确认 `API Base URL`，点击「保存并获取模型」。在模型列表中点击所需模型右侧的 `+`，确认模型已启用；也可先「保存配置」，再通过「自定义模型」填写准确的模型 ID。点击已配置模型旁的「测试模型」按钮可检查是否可用。

进入「配置文件」，选择要使用的配置文件，在「AI」→「模型」中将「对话模型」设为刚添加的模型，点击右下角「保存配置」。此项用于 AstrBot 内置 AI。

详细步骤见 [接入模型服务](./start.md)。

> 提供商连接配置保存在 `data/cmd_config.json` 的 `provider_sources` 字段，具体模型配置保存在 `provider` 字段。

## Google Vertex AI

选择 `Google Vertex AI` 可通过 Google Cloud Vertex AI 调用 Gemini 模型，支持与 `Gemini Compatible` 相同的功能，如思考、原生搜索和安全过滤器。`API Base URL` 保持为空，接口地址会根据区域自动选择。可任选以下一种认证方式：

- **绑定服务账号的 API Key（推荐）**：无需保存密钥文件。创建仅限 Vertex AI 使用的 Key，例如 `gcloud services api-keys create --service-account=SA_EMAIL --api-target=service=aiplatform.googleapis.com`，填入 `API Key`，并填写「Vertex AI 项目 ID」和「Vertex AI 区域」。区域需支持所用模型，部分模型仅在 `global` 提供。
- **API Key（Vertex AI express 模式）**：在 `API Key` 中填写 express 模式 Key，「Vertex AI 项目 ID」留空。请求将发送到 Google 默认区域。
- **服务账号**：`API Key` 留空，在「服务账号密钥文件」中填写具有 `Vertex AI User` 角色的服务账号 JSON 密钥路径，并设置「Vertex AI 区域」（默认 `global`）。「Vertex AI 项目 ID」留空时从密钥文件读取。使用 Docker 部署时，请将密钥文件挂载到容器内并填写容器内路径。
- **应用默认凭据 (ADC)**：`API Key` 和密钥文件均留空，AstrBot 将使用 `GOOGLE_APPLICATION_CREDENTIALS` 或所在 Google Cloud 环境的凭据。

模型 ID 请使用 Vertex AI Model Garden 中显示的 ID，例如 `gemini-2.5-flash`。Google 不允许使用 API Key 获取模型列表，因此使用 API Key 认证时，请通过「自定义模型」手动添加模型。
