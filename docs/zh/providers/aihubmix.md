# 接入 AIHubMix

[AIHubMix](https://aihubmix.com/?aff=4bfH) 是一个多模型 AI API 聚合平台，通过统一接口可调用 OpenAI、Claude、Gemini、DeepSeek、Kimi 等主流模型，同时支持语音、嵌入、重排序等多种能力。

API 格式完全兼容 OpenAI，只需修改 API Base 和 Key 即可接入。**部分模型免费，可直接用于开发测试。**

## 获取 API Key

1. 前往 [AIHubMix](https://aihubmix.com/?aff=4bfH) 注册账号
2. 登录后在控制台 → API Keys 页面创建一个新的 Key
![获取 API Key](https://github.com/user-attachments/assets/d717f21b-2805-4aff-ac90-f5c98f17cb79)

## 在 AstrBot 中配置

进入 AstrBot 管理面板，点击左栏 **服务提供商 → 新增提供商 → OpenAI**。

填写以下信息：

| 配置项 | 值 |
|--------|-----|
| API Base URL | `https://aihubmix.com/v1` |
| API Key | 你在 AIHubMix 获取的 Key |

保存后，点击该 provider 卡片，添加你需要的模型。
![在 AstrBot 中配置](https://github.com/user-attachments/assets/ee2fb8ba-652c-4e97-a781-42a9082ad7eb)

## 推荐模型

### 免费模型 🆓

以下模型完全免费，适合开发测试和轻量场景：

| 模型 ID | 说明 |
|---------|------|
| `gpt-4.1-free` | GPT-4.1 免费版 |
| `gemini-3-flash-preview-free` | Gemini 3 Flash 免费版 |
| `coding-glm-5-free` | GLM-5 代码模型免费版 |
| `coding-minimax-m2.5-free` | MiniMax M2.5 代码模型免费版 |

### 付费模型（常用推荐）

| 模型 ID | 提供商 | 说明 |
|---------|--------|------|
| `gpt-5.4` | OpenAI | 最新旗舰模型 |
| `claude-sonnet-4-6` | Anthropic | 擅长推理和代码 |
| `gpt-5.3-chat-latest` | OpenAI | 高性能对话模型 |
| `deepseek-v3.2` | DeepSeek | 高性价比 |
| `kimi-k2.5` | Moonshot | 长上下文 |
| `gemini-3.1-pro-preview` | Google | 多模态 |

> 完整模型列表请查看 [AIHubMix 文档](https://doc.aihubmix.com)。

## 不只是聊天模型

AIHubMix 同时支持以下能力，均可在 AstrBot 中配置：

| 能力 | AstrBot 配置位置 |
|------|-----------------|
| 语音转文字 (STT) | 服务提供商 → 语音转文字 |
| 文字转语音 (TTS) | 服务提供商 → 文字转语音 |
| 嵌入 (Embedding) | 服务提供商 → 嵌入 |
| 重排序 (Rerank) | 服务提供商 → 重排序 |

所有能力使用同一个 API Key 和 API Base，无需额外配置。

## 设为默认

前往 **配置 → 提供商设置**，将「默认聊天模型提供商」改为刚创建的 AIHubMix 提供商，保存即可。
