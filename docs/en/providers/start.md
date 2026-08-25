# Model Providers

AstrBot separates API sources, concrete models, and Agent execution into three layers:

- A **Provider source** stores the API type, base URL, API key, proxy, and source-level capabilities.
- A **model** references a Provider source and stores the model ID, context window, modalities, and generation parameters.
- An **Agent Runner** controls multi-step execution. The built-in `local` runner uses chat models from the first two layers; Dify, Coze, Alibaba Bailian Applications, and DeerFlow are separate external runners, not ordinary chat Providers.

## Current capability range

The current WebUI exposes these Provider categories:

| Category        | Built-in types and representative integrations                                                                                                                                                               |
| --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Chat Completion | OpenAI Chat Completions and compatible APIs, OpenAI Responses, Anthropic, Google Gemini, plus dedicated Kimi Code, MiniMax Token Plan, Xiaomi, xAI, Zhipu, LongCat, Groq, OpenRouter, and AIHubMix adapters. |
| Speech to Text  | OpenAI Whisper API, self-hosted Whisper, SenseVoice, Mimo, and Xinference.                                                                                                                                   |
| Text to Speech  | OpenAI, Mimo, Genie, Edge TTS, GPT-SoVITS, FishAudio, DashScope, Azure, MiniMax, Volcengine, Gemini, and ElevenLabs.                                                                                         |
| Embedding       | OpenAI, Gemini, NVIDIA, and Ollama.                                                                                                                                                                          |
| Rerank          | vLLM, Xinference, Alibaba Bailian, and NVIDIA.                                                                                                                                                               |
| Agent Runner    | Dify, Coze, Alibaba Bailian Applications, and DeerFlow; selected by a profile rather than invoked as a local model.                                                                                          |

Templates come from the current code registry and can change in later releases. Treat the list shown under **Providers → Add Provider Source** as authoritative for the running version.

## Recommended configuration flow

1. Open **Providers** and add a source in the Provider Sources section.
2. Select the exact API type and enter its base URL, API key, proxy, and related fields.
3. Fetch models from the source or add a model with the exact model ID.
4. Verify `max_context_tokens`, modalities, and tool-calling capability for each model.
5. Open **Config**, edit the active profile, and select the default chat, STT, TTS, embedding, or rerank model under Provider settings.
6. Use the test action or a real conversation before configuring fallback and retries.

Provider data is stored in two profile arrays:

- `provider_sources` contains shared endpoints and credentials;
- `provider` contains model instances linked through `provider_source_id`.

Do not copy old `provider` objects by hand. The current WebUI coordinates model references when a source is renamed and handles dependent models when a source is removed.

## Choosing an API type

- Use **OpenAI Chat Completions** or a matching preset when the service explicitly exposes a compatible Chat Completions endpoint.
- Use **OpenAI Responses** when you need its remote state modes, background responses, or native Web Search. It is not an alias for Chat Completions.
- Prefer native Anthropic and Gemini adapters to retain thinking, native search, image output, or safety settings. For Anthropic, set API Base to `https://api.anthropic.com` without `/v1`.
- “OpenAI compatible” only means the request protocol is similar. It does not guarantee compatible tools, vision, audio, streaming usage, or reasoning fields. Test each required capability.

See [Provider Configuration](./llm) for field details. For local models, see [Ollama](./provider-ollama) and [LM Studio](./provider-lmstudio). For external orchestration, see [Agent Runners](./agent-runners).

## Loading keys from environment variables

API-key fields accept `$ENV_VARIABLE_NAME`, such as `$OPENAI_API_KEY`. The variable must exist in the AstrBot process environment. In containers, inject it through a Secret, restricted env file, or orchestration platform instead of baking it into an image or committing it.
