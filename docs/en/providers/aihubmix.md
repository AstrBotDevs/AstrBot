# Connect AIHubMix

[AIHubMix](https://aihubmix.com/?aff=4bfH) is a multi-model AI API gateway that provides unified access to OpenAI, Claude, Gemini, DeepSeek, Kimi and more through a single API key. Beyond LLM, it also supports speech, embedding, reranking and other capabilities.

Fully compatible with the OpenAI API format — just change the API Base and Key to get started. **Some models are completely free for development and testing.**

## Get an API Key

1. Sign up at [AIHubMix](https://aihubmix.com/?aff=4bfH)
2. Go to Console → API Keys to create a new key

![Get an API Key](https://github.com/user-attachments/assets/d717f21b-2805-4aff-ac90-f5c98f17cb79)

## Configure in AstrBot

Open the AstrBot dashboard , click **Providers → Add Provider → OpenAI**.

Fill in the following:

| Field | Value |
|-------|-------|
| API Base URL | `https://aihubmix.com/v1` |
| API Key | Your AIHubMix key |

After saving, click the provider card to add models.

![Configure in AstrBot](https://github.com/user-attachments/assets/ee2fb8ba-652c-4e97-a781-42a9082ad7eb)

## Recommended Models

### Free Models 🆓

These models are completely free, great for development and testing:

| Model ID | Description |
|----------|-------------|
| `gpt-4.1-free` | GPT-4.1 free tier |
| `gemini-3-flash-preview-free` | Gemini 3 Flash free tier |
| `coding-glm-5-free` | GLM-5 coding model, free |
| `coding-minimax-m2.5-free` | MiniMax M2.5 coding model, free |

### Paid Models (Popular)

| Model ID | Provider | Description |
|----------|----------|-------------|
| `gpt-5.4` | OpenAI | Latest flagship model |
| `claude-sonnet-4-6` | Anthropic | Great for reasoning and code |
| `gpt-5.3-chat-latest` | OpenAI | High-performance chat |
| `deepseek-v3.2` | DeepSeek | Cost-effective |
| `kimi-k2.5` | Moonshot | Long context |
| `gemini-3.1-pro-preview` | Google | Multimodal |

> See the full model list at [AIHubMix Docs](https://doc.aihubmix.com).

## More Than Chat Models

AIHubMix also supports the following capabilities, all configurable in AstrBot:

| Capability | AstrBot Config Location |
|------------|------------------------|
| Speech-to-Text (STT) | Providers → Speech to Text |
| Text-to-Speech (TTS) | Providers → Text to Speech |
| Embedding | Providers → Embedding |
| Reranking | Providers → Rerank |

All capabilities use the same API Key and API Base — no extra setup needed.

## Set as Default

Go to **Settings → Provider Settings**, set "Default Chat Model Provider" to your AIHubMix provider, and save.
