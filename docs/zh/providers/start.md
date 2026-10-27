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

## 接入判断模型

AstrBot 的「判断」提供商用于低延迟结构化判断，例如是否回复消息、选择回复目标或执行某个简单分支。它不参与聊天模型选择，插件通过 `self.context.decision` 调用。

1. 打开「模型提供商」→「判断」，点击「新增」。「判断」标签使用天平图标，位置由「对话」后移至「文字转语音」后、「嵌入」前。
2. 选择 `TypeSafe System One`、`OpenRouter System One` 或 `Vercel System One`。其他兼容 System One 的服务可选择 `Custom System One`。
3. 填写单个 `API Key`、`API Base URL` 和模型 ID。`API Key` 是字符串，不支持多 Key 轮换，可填写 `$环境变量名称` 引用环境变量。自定义服务填写基础地址后会默认补全 `/systemone`，例如 `https://api.example.com/v1` 会请求 `https://api.example.com/v1/systemone`；以 `/` 结尾则按完整接口地址使用。保存后点击「测试」检查连通性。

原「设置」中的超时时间、总超时时间、最大并发数、判定概率容差、代理地址和自定义请求头现位于「高级配置...」折叠区。点击展开后修改，最后点击「保存」。

判断提供商支持一次请求回答多个问题。主动回复、回复门控等业务阈值由调用方决定，AstrBot 只负责模型请求、响应校验和结果归一化。

## 以 DeepSeek 为例的接入步骤

以 DeepSeek 为例，假设您已经注册并登录了 DeepSeek 账户，接入步骤如下：

- 进入 [DeepSeek 控制台](https://platform.deepseek.com/)。
- 点击左侧导航栏的 “API Keys” 菜单，创建一个新的 API Key，并复制该 Key。
- 点击左侧导航栏下方的 “接口文档” 链接，进入 API 文档页面。
- 在 API 文档页面中，找到 “OpenAI 兼容接口” 相关的内容，记下 API Base URL，例如 `https://api.deepseek.com/v1`。（如果没有 /v1，就请加上 /v1）。
- 打开「模型提供商」→「对话」，点击「新增」，选择 `DeepSeek`。其他兼容 OpenAI API 的服务可选择 `OpenAI Compatible`。填写提供商名称、`API Key` 和 `API Base URL`。
- 点击「保存并获取模型」，找到想使用的模型，点击右侧 `+` 并确认模型已启用。如果无法获取模型列表，可先「保存配置」，再点击「自定义模型」并填写模型 ID。可通过模型旁的「测试模型」检查连通性。
- 进入「配置文件」，选择要使用的配置文件，在「AI」→「模型」中将「对话模型」设为刚添加的模型，点击右下角「保存配置」。此项用于 AstrBot 内置 AI。

## 使用环境变量加载 Key

> v4.13.0 之后引入

支持使用环境变量加载模型服务提供商的 API Key。在提供商配置页面，将 API Key 一栏填写为 `$环境变量名称` 的名称即可，例如填写 `$DEEPSEEK_API_KEY`。
