# 接入 Opper

[Opper](https://opper.ai/) 是由 Opper Technology AB（瑞典斯德哥尔摩）运营的欧盟托管 AI 网关。一个 API Key、一个 OpenAI 兼容端点即可访问 30 多家上游供应商的模型，包括 Anthropic、OpenAI、Google、Mistral 和 DeepSeek，按各供应商自身的 token 价格计费，不加价。请求可固定在欧盟托管的区域。

## 配置聊天模型

在 Opper [控制台](https://platform.opper.ai) 的 **API Keys** 中创建 API Key，保存备用。

在[模型目录](https://opper.ai/models)中选择所需模型并记下其 id。Opper 支持两种写法：裸池名（如 `claude-sonnet-4-6`）会在所有提供该模型的供应商之间路由；`<供应商>/<模型>`（如 `anthropic/claude-sonnet-4-6`、`aws/claude-sonnet-4-6-eu`）则固定某一供应商或区域。

在 AstrBot WebUI 中打开 **服务提供商 → 聊天补全**，点击 **新增**，选择 `Opper`。

填写提供商名称与 `API Key`，确认 `API Base URL`（`https://api.opper.ai/v3/compat`），然后点击 **保存并拉取模型列表**。在所需模型旁点击 `+` 并确保其已启用。也可以点击 **保存配置**，再通过 **自定义模型** 填入准确的模型 id。使用模型旁的 **测试模型** 检查可用性。

## 应用聊天模型

打开 **配置**，选择要使用的配置组，进入 **AI → 模型**，将 **聊天模型** 设为刚刚添加的模型，然后点击右下角 **保存配置**。该设置作用于 AstrBot 内置 AI。
