# 接入 OrcaRouter

[OrcaRouter](https://www.orcarouter.ai) 是一个统一的 AI 网关，通过单个 API Key 即可访问 OpenAI、Anthropic、Google、DeepSeek、Kimi 等多种模型，且完全兼容 OpenAI API 格式。同时，它还在同一端点上为 AI 智能体提供网关级的零信任安全能力——对每一次提示词/响应进行筛查，并以默认拒绝的方式管控每一次工具调用，无需修改任何应用代码。

## 获取 API Key

1. 在 [OrcaRouter](https://www.orcarouter.ai) 注册账号
2. 进入控制台 → API Keys，创建一个新的 Key（Key 以 `sk-orca-` 开头）

## 在 AstrBot 中配置

AstrBot 内置了 OrcaRouter 提供商。打开 AstrBot 控制台，点击**服务提供商 → 新增提供商 → OrcaRouter**。

API Base URL 已为您预填。填写以下内容：

| 字段 | 值 |
|------|------|
| API Base URL | `https://api.orcarouter.ai/v1` |
| API Key | 您的 OrcaRouter Key |

保存后，点击该提供商卡片即可添加模型。

## 模型

OrcaRouter 提供对 OpenAI GPT、Anthropic Claude、Google Gemini、DeepSeek、Kimi 等多种模型的统一访问。在提供商面板中点击**获取模型列表**即可浏览您的账户可用的模型，完整模型列表请参阅 [OrcaRouter 文档](https://www.orcarouter.ai)。
