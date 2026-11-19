# 接入 WorldRouter

[WorldRouter](https://router.worldclaw.ai) 是兼容 OpenAI 接口的模型 API 平台，一个 API Key 即可调用 Claude、GPT、Gemini、DeepSeek、Kimi 等模型。

## 使用

前往 [WorldRouter](https://router.worldclaw.ai) 注册账户，并在控制台的「API Keys」页面创建 API Key。

可用模型及价格见 [模型列表](https://router.worldclaw.ai/models)，接入说明见 [快速开始](https://router.worldclaw.ai/docs/quickstart)。

## 接入

进入 AstrBot WebUI 的「模型提供商」→「对话」，点击「新增」，选择 `WorldRouter`。

填写提供商名称和 `API Key`，确认 `API Base URL` 为 `https://inference-api.worldrouter.ai/v1`，点击「保存并获取模型」。在模型列表中点击所需模型右侧的 `+`，确认模型已启用；也可先「保存配置」，再通过「自定义模型」填写准确的模型 ID。点击已配置模型旁的「测试模型」按钮可检查是否可用。

## 使用

进入「配置文件」，选择要使用的配置文件，在「AI」→「模型」中将「对话模型」设为刚添加的模型，点击右下角「保存配置」。此项用于 AstrBot 内置 AI。

对机器人输入 `/provider` 指令，将提供商切换到刚刚添加的 WorldRouter 提供商，即可使用。
