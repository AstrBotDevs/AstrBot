# Provider Configuration

Manage Provider sources and models on the **Providers** page, then select defaults for each profile on **Config**.

![Providers page](https://files.astrbot.app/docs/source/images/llm/image.png)

![Model configuration](https://files.astrbot.app/docs/source/images/llm/image-1.png)

## Provider sources

When adding a source, verify:

- **Type** selects the adapter and its specialized fields. Do not choose from the service name alone.
- **API Base** normally includes the version path required by the service, such as `/v1` for many OpenAI-compatible APIs. It is AstrBot's outbound endpoint, not a WebUI callback URL. For the native Anthropic adapter, use `https://api.anthropic.com` without `/v1`; a saved `/v1` suffix is stripped at runtime.
- **API Key** can contain multiple keys or an `$ENV_NAME` reference. Never expose it in logs or screenshots.
- **Timeout, proxy, and custom headers** are shared by models from the source. Treat credential-bearing custom headers as secrets too.

After saving a source, prefer fetching its model list. Add a model manually only when the service cannot enumerate models.

## Model instances

A model needs a unique ID, the exact remote model name, and a `provider_source_id`. Also verify:

- `max_context_tokens`: context compression and request guarding depend on it. Set it manually when a custom model name cannot be resolved from built-in metadata.
- modalities: text, image, and other capabilities must match the service.
- tool calling: expose Agent tools only when the service implements function/tool calling correctly.
- generation parameters: ensure temperature, top-p, max tokens, and similar fields are accepted by that model.

One source can back several models. Do not duplicate IDs by copying JSON; Provider Manager resolves defaults, fallback, and profile or Persona references by ID.

## OpenAI Responses

An OpenAI Responses source adds these settings:

| Field                                | Default     | Meaning                                                                                                    |
| ------------------------------------ | ----------- | ---------------------------------------------------------------------------------------------------------- |
| `responses_state_mode`               | `stateless` | `stateless` replays context locally; `previous_response_id` and `conversation` use state stored by OpenAI. |
| `store`                              | `false`     | Allows server-side Responses state. Both stateful modes and background responses require it.               |
| `responses_background`               | `false`     | Submit a background response and poll for completion. Requires a non-`stateless` mode and `store=true`.    |
| `responses_background_poll_interval` | `1`         | Poll interval in seconds.                                                                                  |
| `responses_background_timeout`       | `600`       | Background timeout; aborts and timeouts attempt to cancel the remote response.                             |
| `web_search`                         | Off         | Native OpenAI Web Search with domain, context-size, source, and raw-result controls.                       |

> [!WARNING]
> `previous_response_id`, `conversation`, `store`, and background responses keep state at the remote service. Review data residency, retention, deletion, and organizational compliance before enabling them. Use `stateless` with `store=false` when all history should be replayed by AstrBot instead.

Native `web_search` inside the source applies only to OpenAI Responses. Profile-level `provider_settings.web_search` is AstrBot's cross-Provider search tool. They can be enabled independently and have different cost and source formats.

## Default models and fallback

Configure these under **Config** in the Agent Runner section:

- `agent_runner.config.model.provider_id` for the default chat model;
- `agent_runner.config.model.fallback_provider_ids` for ordered fallback after the primary fails;
- `agent_runner.config.model.request_max_retries` for the retry limit on each model;
- default image-caption, STT, TTS, embedding, and rerank models.

Several models on the same unstable endpoint are not true failure isolation. For resilient fallback, use different sources, credentials, or vendors where possible and account for worst-case total latency.

## TTS and ElevenLabs

ElevenLabs is included in the current TTS types. An `elevenlabs_tts_api` source needs an API key, Voice ID, and output format; stability, similarity boost, style, and speaker boost are optional voice controls. The profile's `provider_tts_settings` controls the global TTS switch, default model, dual output, file service, and trigger probability.

MiMo TTS uses `mimo-v2.5-tts` as the current default because the older `mimo-v2-tts` model is no longer available. Existing Provider entries keep their configured model during upgrade; edit any MiMo TTS entry that still uses the old model.

Whether the final audio format plays correctly still depends on the messaging-platform adapter. A successful Provider test is not the end-to-end test.

## Security and troubleshooting

- Keep TLS verification enabled. Do not work around download or Provider security with `verify=false`, `ssl=false`, or an untrusted interception certificate.
- Reach private endpoints through a controlled network, VPN, or reverse proxy. Do not expose a local model port publicly just for testing.
- On failure, check the API Base, exact model ID, key permission, proxy, timeout, modalities, and tool capability in that order.
- After changing a source, retest every model that references it and the active profile's default/fallback chain.

See [AstrBot Configuration Reference](../dev/astrbot-config) for the stored structure.
