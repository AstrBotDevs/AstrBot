# 接入模型服务

AstrBot 适配了 OpenAI、Google GenAI、Anthropic 三种原生 API 格式。您可以接入任意符合这三种 API 格式之一的模型服务提供商。

> [!NOTE]
> 如果您位于中国大陆境内，我们强烈建议您使用符合当地法律法规的由**模型厂商官方提供的**或经过备案的模型服务提供商，例如：
> 
> - [MoonshotAI](https://moonshot.cn/)
> - [GLM](https://bigmodel.cn/)
> - [MiniMax](https://www.minimax.io/)
> - [Qwen](https://qwen.ai/apiplatform)
> - [DeepSeek](https://deepseek.com/)
>
> 上述提供商均支持 OpenAI API 格式，您可以通过其文档中有关 “OpenAI 格式接入” 的说明，找到 API Base URL 及 API Key，然后将其填入 AstrBot 的提供商配置中。
> 
> 请注意，使用未经备案的第三方模型服务提供商可能会导致服务不可用、信息泄露或其他法律风险，请谨慎选择。更多内容，请阅读我们的最终用户许可协议（[EULA](https://github.com/AstrBotDevs/AstrBot/blob/master/EULA.md)）。

例如，您可以选择接入如下（但不限于）模型提供商提供的模型服务：

- OpenAI 官方提供的模型服务（[OpenAI 官方网站](https://openai.com/)）
- Anthropic 官方提供的模型服务（[Anthropic 官方网站](https://www.anthropic.com/)）
- Google 提供的 Gemini 模型服务（[Google Cloud 官方网站](https://cloud.google.com/)）
- OpenRouter 提供的模型服务（[OpenRouter 官方网站](https://openrouter.ai/)）

## 以 DeepSeek 为例的接入步骤

以 DeepSeek 为例，假设您已经注册并登录了 DeepSeek 账户，接入步骤如下：

- 进入 [DeepSeek 控制台](https://platform.deepseek.com/)。
- 点击左侧导航栏的 “API Keys” 菜单，创建一个新的 API Key，并复制该 Key。
- 点击左侧导航栏下方的 “接口文档” 链接，进入 API 文档页面。
- 在 API 文档页面中，找到 “OpenAI 兼容接口” 相关的内容，记下 API Base URL，例如 `https://api.deepseek.com/v1`。（如果没有 /v1，就请加上 /v1）。
- 打开「模型提供商」→「对话」，点击「新增」，选择 `DeepSeek`。其他兼容 OpenAI API 的服务可选择 `OpenAI Compatible`。填写提供商名称、`API Key` 和 `API Base URL`。
- 点击「保存并获取模型」，找到想使用的模型，点击右侧 `+` 并确认模型已启用。如果无法获取模型列表，可先「保存配置」，再点击「自定义模型」并填写模型 ID。可通过模型旁的「测试模型」检查连通性。
- 进入「配置文件」，选择要使用的配置文件，在「AI 配置」→「模型」中将「对话模型」设为刚添加的模型，点击右下角「保存配置」。此项用于 AstrBot 内置 AI。

## 接入 StepFun 和 Step Plan

打开「模型提供商」→「对话」→「新增」，普通 API 选择 `StepFun`，Step Plan 订阅选择 `StepFun Step Plan`，填写阶跃星辰 API Key。两个预设分别使用以下 API Base URL：

![提供商选择器中的 StepFun 和 StepFun Step Plan 入口](/stepfun-provider-presets.png)

| 预设 | 默认 API Base URL |
| --- | --- |
| StepFun | `https://api.stepfun.com/v1` |
| StepFun Step Plan | `https://api.stepfun.com/step_plan/v1` |

API Base URL 仍可编辑，请使用与账号区域及计费套餐对应的地址，详见[阶跃星辰 API 文档](https://platform.stepfun.com/docs/zh/api-reference/chat/chat-completion-create)。

点击「保存并获取模型」，添加账号可用的模型。如果获取列表失败，可先「保存配置」，再通过「自定义模型」填写当前接口支持的模型 ID。最后按照上面的步骤，将其设为配置文件中「AI 配置」→「模型」的「对话模型」。

两个预设与其他 OpenAI 兼容提供商使用相同的可选配置：提供商高级配置支持超时、代理和自定义请求头，模型配置支持模型能力、上下文大小和自定义请求参数。请仅启用所选模型支持的能力和参数。例如，对支持相应参数的模型，可在 `custom_extra_body` 中填写 `{"reasoning_effort": "high", "max_tokens": 8192}`；留空则使用服务端默认值。

## 使用环境变量加载 Key

> v4.13.0 之后引入

支持使用环境变量加载模型服务提供商的 API Key。在提供商配置页面，将 API Key 一栏填写为 `$环境变量名称` 的名称即可，例如填写 `$DEEPSEEK_API_KEY`。
