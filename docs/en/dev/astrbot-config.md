# AstrBot Configuration Reference

AstrBot configuration evolves with Providers, platform adapters, and Agent capabilities. This page documents the current stable groups, defaults, and operational boundaries instead of maintaining a hand-copied “complete default configuration.”

The authoritative code is:

- defaults: `DEFAULT_CONFIG` in `astrbot/core/config/default.py`;
- WebUI field metadata: `CONFIG_METADATA_3` and `CONFIG_METADATA_3_SYSTEM` in the same file;
- loading, integrity checks, and password migration: `astrbot/core/config/astrbot_config.py`.

## File locations and loading behavior

The default profile is stored at `data/cmd_config.json` under the runtime root. With `ASTRBOT_ROOT` set, it becomes `$ASTRBOT_ROOT/data/cmd_config.json`.

Additional profiles created in the WebUI are stored as `data/config/abconf_<uuid>.json`. Profile-to-message-session bindings are maintained by the configuration manager; do not move a binding by renaming files.

The files are parsed with Python's standard JSON parser and must therefore be **strict JSON**:

- use `true` and `false` for booleans;
- do not add comments;
- do not use trailing commas;
- quote keys and strings with double quotes.

At startup, AstrBot recursively inserts missing current defaults, fixes key order, and removes unknown keys that are not present in the current default structure. Adding an unsupported field manually does not extend the configuration model.

> [!TIP]
> Prefer the WebUI: profile settings are under **Config**, model and Provider records under **Providers**, adapter instances under **Platforms**, and process-wide settings are grouped under **Settings**. If you edit JSON directly, keep a copy and restart AstrBot afterward.

## Top-level structure

| Key                                               | Purpose                                                                                                                                |
| ------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| `config_version`                                  | Current core configuration version, default `2`. Do not downgrade it manually.                                                         |
| `platform_settings`                               | Cross-platform receive, send, allowlist, rate-limit, and segmented-reply behavior.                                                     |
| `provider_sources`                                | Provider endpoints and credentials, maintained by the Providers page.                                                                  |
| `provider`                                        | Concrete chat, STT, TTS, embedding, rerank, and other model instances.                                                                 |
| `provider_settings`                               | Agent, default-model, Persona, retrieval, context, and tool behavior for this profile.                                                 |
| `subagent_orchestrator`                           | SubAgent handoff orchestration.                                                                                                        |
| `provider_stt_settings` / `provider_tts_settings` | Default speech-to-text and text-to-speech models and switches.                                                                         |
| `provider_ltm_settings`                           | Group-context, image-caption, and proactive-reply settings under a historical name; it is not the Alkaid long-term-memory switch.      |
| `content_safety`                                  | Built-in keyword checks and optional external content-safety checks.                                                                   |
| `dashboard`                                       | WebUI listening, authentication, rate limiting, and TLS; Dashboard account identity and authoritative TOTP state live in its database. |
| `platform` / `platform_specific`                  | Adapter instances and platform-specific behavior for Lark, Telegram, Discord, and others.                                              |
| Other top-level keys                              | Administrators, T2I, proxy, logging, timezone, plugins, knowledge base, Trace, and metrics.                                            |

Object layouts inside `provider_sources`, `provider`, and `platform` come from the currently registered type templates. Do not copy old objects from documentation. Create them in the WebUI and inspect the saved result if necessary. A model references its source through `provider_source_id`; use the WebUI when renaming or deleting a source so references are updated together.

## `platform_settings`

| Key                                         | Default                                     | Meaning                                                                                                                                                          |
| ------------------------------------------- | ------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `unique_session`                            | `false`                                     | Split separate sessions for members inside a group.                                                                                                              |
| `rate_limit`                                | `60` seconds / `30` messages / `stall`      | Wait (`stall`) or discard (`discard`) when the limit is exceeded.                                                                                                |
| `enable_id_white_list`                      | `true`                                      | Enable the ID allowlist; the two `wl_ignore_admin_*` fields control administrator bypass.                                                                        |
| `reply_prefix`                              | `""`                                        | Prefix added to replies.                                                                                                                                         |
| `reply_with_mention` / `reply_with_quote`   | `false`                                     | Mention the sender or quote the source message when supported by the adapter.                                                                                    |
| `forward_threshold`                         | `1500`                                      | Long-reply forwarding threshold on platforms that support forwarded messages.                                                                                    |
| `segmented_reply`                           | See current defaults                        | Non-streaming segmentation, timing, and cleanup rules.                                                                                                           |
| `path_mapping`                              | `[]`                                        | Map paths from a platform container into paths AstrBot can read, using `source:target`. This is still used by the receive/respond pipeline.                      |
| `group_wake_policy`                         | `{mention_bot: false, reply_to_bot: false}` | Whether mentioning the bot or replying to the bot wakes a group message. Both default to false. The wake prefix is the top-level `wake_prefix`, default `["/"]`. |
| `friend_message_needs_wake_prefix`          | `false`                                     | Require a wake prefix in direct messages.                                                                                                                        |
| `ignore_bot_self_message` / `ignore_at_all` | `false`                                     | Ignore the bot's own messages or mass mentions.                                                                                                                  |

Example path mapping:

```json
{
  "platform_settings": {
    "path_mapping": [
      "/app/.config/QQ:/var/lib/docker/volumes/napcat_data/_data"
    ]
  }
}
```

This is a partial illustration and must not replace the complete file. Because Windows drive letters contain a colon, configure mappings in the WebUI and validate them against real platform events.

## `provider_settings`

### Provider selection and retries

- `enable` enables AI Provider processing and defaults to `true`.
- `default_provider_id` selects the default chat model.
- `fallback_chat_models` lists chat-model IDs tried in order after the primary model fails.
- `request_max_retries` is the per-model maximum retry count and defaults to `5`. Fallback and retries are separate layers.
- `provider_pool` limits Providers available to this profile; `["*"]` means all.
- `default_image_caption_provider_id` and `image_caption_prompt` caption images in the current main-agent request and quoted messages. They are not affected by group-history caption limits.
- `provider_ltm_settings.image_caption_*` applies only to group-history captions. `image_caption_scope` is `all`, `allowlist`, or `denylist`; `image_caption_groups` accepts full UMOs only; `image_caption_min_interval` and `image_caption_max_concurrency` bound interval and global concurrency. `image_caption_cache_ttl` defaults to `0` (off) and is scoped by UMO plus content id. `image_caption_lazy` defaults to off.
- Group-chat JSON cards enter group context and are used as a `[Shared Card]` summary when a proactive reply or ordinary LLM request has no text prompt.

API keys are sensitive configuration. Never commit a real `cmd_config.json`, screenshots, logs, or backups. Logs and Trace data can also contain Provider IDs, request errors, and tool output.

### Persona, prompts, and sessions

- `default_personality` selects the default Persona ID.
- `persona_pool` limits selectable Personas; `["*"]` means all.
- `prompt_prefix` is the user-prompt template. Keep `{{prompt}}` if the original input must be included.
- profile-level `wake_prefix` is distinct from the top-level global command/wake-prefix list.
- `identifier`, `group_name_display`, and `datetime_system_prompt` add user identity, group name, or current time to the prompt.

See [Personas](../use/persona) for selection priority and permission semantics.

### Context management

| Key                              | Default                         | Meaning                                                                       |
| -------------------------------- | ------------------------------- | ----------------------------------------------------------------------------- |
| `context_limit_reached_strategy` | `llm_compress`                  | `llm_compress` or `truncate_by_turns`.                                        |
| `llm_compress_keep_recent_ratio` | `0.15`                          | Exact recent-context token ratio, clamped to `0`–`0.3`.                       |
| `llm_compress_provider_id`       | `""`                            | Empty means the chat model active for the current session.                    |
| `llm_compress_instruction`       | Built-in five-point instruction | Summary prompt.                                                               |
| `max_context_length`             | `-1`                            | Conversation turns kept before compression; `-1` disables this turn limit.    |
| `dequeue_context_length`         | `1`                             | Turns removed per turn-based truncation pass.                                 |
| `fallback_max_context_tokens`    | Runtime default `128000`        | Fallback window when neither model config nor built-in metadata supplies one. |

See [Automatic Context Compression](../use/context-compress) for the full behavior.

### Agent Runner and tools

- `agent_runner_type` selects the built-in `local` Agent or a configured Dify, Coze, DashScope, or DeerFlow runner.
- `*_agent_runner_provider_id` selects the Provider record for an external runner.
- `max_agent_step` defaults to `30` and also applies to current SubAgent executions.
- `tool_call_timeout` is the per-tool timeout in seconds, default `120`.
- `tool_schema_mode` uses `full` schemas or the lighter two-stage `skills_like` mode.
- `show_tool_use_status` / `show_tool_call_result` expose tool state and a result preview to users.
- `buffer_intermediate_messages` combines intermediate text during non-streaming multi-step runs.
- `sanitize_context_by_modalities` removes unsupported modalities and tool structures according to the current model, changing the history seen by that model.
- `proactive_capability.add_cron_tools` exposes proactive/Cron tools to the local Agent.
- `file_extract` is experimental document extraction currently templated for the Moonshot API.

### Streaming

- `streaming_response` enables Provider streaming.
- `unsupported_streaming_strategy` uses `realtime_segmenting` on platforms without native streaming or `turn_off` to disable streaming for that response.
- Session `/flow on|off|unset|status` can override the global value. Priority is `event.extra["enable_streaming"]` > session override > `provider_settings.streaming_response`. The effective value is pinned when a request starts.

The old `provider_settings.streaming_segmented` field has been removed. Do not add it back.

### Computer Use and sandboxing

- `computer_use_runtime` is `none`, `local`, or `sandbox` and defaults to `none`.
- `computer_use_require_admin` is no longer a runtime authorization switch. Computer capabilities use the unified `tool.computer_use`, `tool.local_exec`, `tool.file_read`, and `tool.file_write` actions, with step-up/elevation for high-risk operations.
- `sandbox.booter` selects `shipyard_neo` or `cua`; related fields store endpoint, token, profile, TTL, or CUA OS, telemetry, and local/cloud settings.

Local mode operates directly on the AstrBot host and belongs only in a trusted environment. A sandbox is not an authorization boundary by itself; continue to restrict administrators, Persona tools, and external network access.

### Search and images

`web_search`, `websearch_provider`, and provider-specific keys configure built-in web search; `web_search_link` controls link output. Enter keys through the WebUI.

`image_compress_enabled` and `image_compress_options.max_size/quality` control image compression before model requests. `max_quoted_fallback_images` and `quoted_message_parser` limit quoted and forwarded-message expansion to prevent unbounded fetching. For `quoted_message_parser`, `0` is a valid boundary: depth limits keep the root level but stop child recursion, and `max_forward_fetch=0` disables recursive `get_forward_msg` calls. Negative or invalid values fall back to defaults; this setting does not globally disable a direct quoted-message `get_msg` fallback.

## SubAgents, speech, and knowledge base

- `subagent_orchestrator.main_enable` enables handoffs.
- `remove_main_duplicate_tools` removes only tools that overlap between the main Agent and SubAgents; it defaults to `false`.
- `router_system_prompt` and `agents` define routing and SubAgents. Maintain them through the dedicated page; see [SubAgent Orchestration](../use/subagent).
- `provider_stt_settings` controls STT and its default model.
- `provider_tts_settings` controls the TTS model, dual output, file service, and a `0`–`1` trigger probability.
- `kb_names`, `kb_fusion_top_k`, and `kb_final_top_k` select default knowledge bases and retrieval counts.
- `kb_agentic_mode` exposes knowledge-base retrieval as a model-controlled tool.

Alkaid [Long-term Memory](../use/long-term-memory) currently has no enable/disable configuration. Do not treat `provider_ltm_settings` as its switch.

## WebUI and authentication

Important `dashboard` defaults:

| Key                      | Default          | Meaning                                                                                                                          |
| ------------------------ | ---------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| `enable`                 | `true`           | Enable the WebUI/API.                                                                                                            |
| `username`               | `astrbot`        | Initial username.                                                                                                                |
| `host`                   | `127.0.0.1`      | Listen on loopback only. Remote access requires an explicit `0.0.0.0` or interface binding plus firewall/reverse-proxy controls. |
| `port`                   | `6185`           | HTTP(S) listening port.                                                                                                          |
| `trust_proxy_headers`    | `false`          | Trust `X-Forwarded-For` / `X-Real-IP` only behind a controlled reverse proxy.                                                    |
| `auth_rate_limit.enable` | `true`           | Rate-limit login, TOTP, and other authentication endpoints.                                                                      |
| `totp.*`                 | Managed by WebUI | Dashboard TOTP snapshot retained for configuration export; it is not the authority for account authentication.                   |
| `ssl.enable`             | `false`          | Terminate TLS in AstrBot using the certificate, key, and optional CA path fields.                                                |

Passwords are stored as PBKDF2 hashes in `pbkdf2_password`. `password` is a migration-era hash field. Never write plaintext into either field or manually exchange hashes. To recover access, run:

```bash
uv run astrbot run --reset-password
```

The source entry point also accepts `uv run main.py --reset-password`. Startup logs print the new temporary password and require it to be changed after login.

Dashboard accounts have stable `account_id` values. Their TOTP secret, recovery-code hash, and trusted devices are stored per account. The Security page synchronizes the `dashboard.totp` snapshot for configuration export and UI use, but login and high-risk operations validate only the account record. Do not edit that snapshot manually, copy TOTP fields between accounts, or treat it as a recovery-code bypass.

## System, logging, and response decoration

- `t2i` and `t2i_word_threshold` render long **output results** as images. `t2i_active_template` is maintained by the template manager.
- `t2i_use_file_service` publishes rendered output through a file-token URL and requires a correct `callback_api_base`.
- `http_proxy` / `no_proxy` are the global outbound proxy and bypass list. They are no longer exported as process `HTTP_PROXY`.
- Providers and platforms use three-state `proxy_mode`: `inherit` follows the global config, `direct` disables environment proxies, and `custom` uses only that item's `proxy_url`. An empty string no longer means both inherit and direct.
- No GitHub mirrors are provided by default. Plugin `download_url` values and prefix mirrors must be public HTTPS origins; private and non-HTTPS targets are rejected.
- `platform_settings.segmented_reply` remains a UX feature and stays off by default. Telegram, Discord, and WeCom hard-limit splitting is handled by the send path.
- `log_level` and `log_file_*` control console and rotating file logs.
- `trace_enable` is the Trace collection switch; `trace_log_*` controls its separate rotating file.
- `temp_dir_max_size` limits `data/temp` in MiB and defaults to `1024`; a background task removes older files when the limit is exceeded.
- `timezone` is an IANA timezone and defaults to `Asia/Shanghai`.
- `callback_api_base` is the externally reachable base used to build callback and file URLs. It does not change the listening address.
- `plugin_set` limits plugins for the profile; `["*"]` means all and an empty list means none.
- `disable_metrics` disables metric collection. Enable or disable built-in commands individually from Dashboard command management.

## Process-level environment overrides

Only a small set of startup values have environment overrides. There is no general configuration-key-to-environment-variable mapping.

| Environment variable                                                                                     | Purpose                                                                                                          |
| -------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `ASTRBOT_ROOT`                                                                                           | Relocate the runtime root.                                                                                       |
| `DASHBOARD_HOST` / `ASTRBOT_DASHBOARD_HOST`                                                              | Override the WebUI bind address.                                                                                 |
| `DASHBOARD_PORT` / `ASTRBOT_DASHBOARD_PORT`                                                              | Override the WebUI port.                                                                                         |
| `DASHBOARD_SSL_ENABLE` / `ASTRBOT_DASHBOARD_SSL_ENABLE`                                                  | Override direct WebUI TLS.                                                                                       |
| `DASHBOARD_SSL_CERT`, `DASHBOARD_SSL_KEY`, `DASHBOARD_SSL_CA_CERTS`, and their `ASTRBOT_`-prefixed forms | Override TLS files.                                                                                              |
| `ASTRBOT_DASHBOARD_INITIAL_PASSWORD`                                                                     | Supply the initial password during first initialization or an explicit reset; password validation still applies. |

Publishing container port `6185` does not override loopback binding. Set the host as well; see [Docker Deployment](../deploy/astrbot/docker).

## Configuration change checklist

1. Confirm that the key exists in the current `DEFAULT_CONFIG` and WebUI metadata.
2. Change it in the WebUI, or stop AstrBot before editing strict JSON.
3. Never expose credentials, TOTP secrets, JWT secrets, or access tokens in issues, logs, or diffs.
4. After restart, inspect logs for removed fields, Provider load failures, or adapter reload failures.
5. Retest network boundaries after changing binding, proxy headers, TLS, Computer Use, MCP, or callback URLs.
6. Validate the default Provider, Persona, plugin pool, and message-session bindings for every profile; the default profile does not automatically represent all profiles.
