# 接入 LLMTR

[LLMTR](https://llmtr.com/) 是一个兼容 OpenAI 接口的 API 网关，对话补全地址为 `https://llmtr.com/v1`，AstrBot 可通过内置的 OpenAI Compatible 适配器接入。

## 配置对话模型

在 [LLMTR 密钥控制台](https://llmtr.com/dashboard/keys) 创建一个 API Key，留存备用。

模型 ID 为 LLMTR 托管的 vendor/model 路径，例如 `minimax/minimax-m3.1-flash`，请记下要使用的模型 ID。

进入 AstrBot WebUI 的「模型提供商」→「对话」，点击「新增」，选择 `LLMTR`。

填写提供商名称和 `API Key`，确认 `API Base URL` 为 `https://llmtr.com/v1`，点击「保存并获取模型」。在模型列表中点击所需模型右侧的 `+`，确认模型已启用；也可先「保存配置」，再通过「自定义模型」填写准确的模型 ID。点击已配置模型旁的「测试模型」按钮可检查是否可用。

也可以在 API Key 栏填写 `$LLMTR_API_KEY`，通过环境变量加载密钥。

## 应用对话模型

进入「配置文件」，选择要使用的配置文件，在「AI」→「模型」中将「对话模型」设为刚添加的模型，点击右下角「保存配置」。此项用于 AstrBot 内置 AI。
