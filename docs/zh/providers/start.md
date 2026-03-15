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
- 打开 AstrBot 控制台 -> 服务提供商页面，点击新增提供商，找到并点击 `OpenAI`（如果其中有您想要接入的提供商的类型，请优先点击那些类型，如 DeepSeek，我们会针对部分提供商做适配优化）。将 API Key 填入对话框表单的 `API Key` 处，将 API Base URL 填入 `API Base URL` 处。
- 点击获取模型列表，找到您想要使用的模型名称，点击右侧 + 号，然后将右侧的出现的开关打开。
- 进入配置文件页面，找到对话模型，点击右侧的选择按钮，选择刚刚添加的提供商和模型，点击屏幕右下角的保存配置按钮即可。

## 使用环境变量加载 Key

> v4.13.0 之后引入

支持使用环境变量加载模型服务提供商的 API Key。在提供商配置页面，将 API Key 一栏填写为 `$环境变量名称` 的名称即可，例如填写 `$DEESEEK_API_KEY`。