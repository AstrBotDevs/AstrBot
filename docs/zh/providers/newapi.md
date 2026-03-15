# 接入 NewAPI

[New API](http://newapi.ai/) 是一个新一代大模型网关与 AI 资产管理系统，基于 One API 进行二次开发。该项目旨在提供一个统一的接口来管理和使用各种 AI 模型服务，包括但不限于 OpenAI、Anthropic、Gemini 和 Midjourney 等。

AstrBot 支持接入 NewAPI 作为模型提供商，用户可以通过 NewAPI 来访问和使用各种 AI 模型服务。

## 配置步骤

### 获取 NewAPI API Key 密钥

在 NewAPI 注册并登录后，点击上方导航栏的「控制台」，点击「令牌管理」，然后点击「添加令牌」按钮，创建一个新的 API Key 密钥，选择适当的权限，然后点击「创建」。

![create-api-key](https://files.astrbot.app/docs/source/images/newapi/image.png)

创建成功后，点击复制密钥按钮，复制生成的 API Key 密钥。

![copy-api-key](https://files.astrbot.app/docs/source/images/newapi/image-1.png)
### 在 AstrBot 中配置 NewAPI 服务提供商

打开 AstrBot 管理面板，进入「模型提供商」页面，然后，点击「新增模型提供商」按钮。

NewAPI 完美地支持了 OpenAI Chat Completion 和 Responses 接口，我们点击 「OpenAI」，进入 OpenAI 提供商的配置页面。

在弹出的对话框中，将 API Base URL 设置为 NewAPI 的接口地址。如果您本地部署了 NewAPI，则填写本地地址，例如 `http://localhost:3000/v1`，如果您使用第三方服务商提供的 NewAPI 服务，则填写相应的 URL 地址，例如 `https://api.example.com/v1`。

然后，将 API Key 填入「API Key」字段中，点击「保存」按钮。

![astrbot-provider-config](https://files.astrbot.app/docs/source/images/newapi/image-2.png)

然后点击保存，完成 NewAPI 提供商的配置。

### 应用服务提供商

进入「配置文件」页面，找到模型一节，将「默认聊天模型」修改为刚刚创建的 NewAPI 提供商，点击「保存」按钮。

![apply](https://files.astrbot.app/docs/source/images/newapi/image-3.png)

至此，您已经成功配置了 NewAPI 作为 AstrBot 的模型提供商。现在，您可以通过 AstrBot 来访问和使用 NewAPI 提供的各种 AI 模型服务了。
