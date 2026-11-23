---
outline: deep
---

# AstrBot Configuration File

## data/cmd_config.json

AstrBot's configuration file is a JSON format file. AstrBot reads this file at startup and initializes based on the settings within. Its path is `data/cmd_config.json`.

> Since AstrBot v4.0.0, we introduced the concept of [multiple configuration files](https://blog.astrbot.app/posts/what-is-changed-in-4.0.0/#%E5%A4%9A%E9%85%8D%E7%BD%AE%E6%96%87%E4%BB%B6). `data/cmd_config.json` serves as the default configuration `default`. Other configuration files you create in the WebUI are stored in the `data/config/` directory, starting with `abconf_`.

In the WebUI, manage bot and session behavior profiles (including text-to-image) under `Config`. Global runtime, logging, network, and WebUI security settings are under `System Settings`. Model connections and bot connections are managed under `Providers` and `Platforms`, respectively.

## Upgrade and Manual Editing {#agent-config-migration}

The current configuration uses `config_version: 6`. Model, persona, context, and execution settings for built-in AI live under `agent.config`. When an older configuration without an `agent` section is first loaded, AstrBot migrates its settings automatically. The legacy `agent_runner` section becomes `agent`, and the built-in runtime name changes from `local` to `astrbot`. A normal upgrade does not require moving these fields manually.

After migration, the existing `agent` section is the source of these settings. Use the new paths below when editing JSON or updating configuration scripts. Writing the old `provider_settings` keys again does not override `agent.config`; configuration loading removes those old keys.

| Old path | Current path (AstrBot Built-in AI) |
| --- | --- |
| `provider_settings.default_provider_id` | `agent.config.model.provider_id` |
| `provider_settings.default_personality` | `agent.config.persona.persona_id` |
| `provider_settings.max_context_length` | `agent.config.compression.max_turns` |
| `provider_settings.dequeue_context_length` | `agent.config.compression.trim_turns` |
| `provider_settings.max_agent_step` | `agent.config.misc.max_steps` |
| `provider_settings.tool_call_timeout` | `agent.config.misc.tool_call_timeout` |

`provider_settings` still holds the AI switch and common message settings, including `enable`, `wake_prefix`, `web_search`, and `streaming_response`. These valid fields keep their existing paths.

You can also edit them under **Config → AI**: use **Model** for chat models, **Persona** for the persona, and **Advanced** for context and execution settings. Click **Save Configuration** when finished. See [Agent Execution Mode](../use/agent-runner.md) for connecting external applications.

## Default Configuration Example

The following is the complete current source default configuration, with the built-in AI's `agent.config` expanded. It does not include authentication values generated during initialization. Merge the fields you need into your existing configuration when configuring an existing instance.

```json
{
    "config_version": 6,
    "platform_settings": {
        "locale": "zh-CN",
        "unique_session": false,
        "rate_limit": {
            "time": 60,
            "count": 30,
            "strategy": "stall"
        },
        "reply_prefix": "",
        "forward_threshold": 1500,
        "enable_id_white_list": true,
        "id_whitelist": [],
        "id_blacklist": [],
        "id_whitelist_log": true,
        "wl_ignore_admin_on_group": true,
        "wl_ignore_admin_on_friend": true,
        "reply_with_mention": false,
        "reply_with_quote": false,
        "path_mapping": [],
        "segmented_reply": {
            "enable": false,
            "only_llm_result": true,
            "interval_method": "random",
            "interval": "1.5,3.5",
            "log_base": 2.6,
            "words_count_threshold": 150,
            "split_mode": "regex",
            "regex": ".*?[。？！~…]+|.+$",
            "split_words": [
                "。",
                "？",
                "！",
                "~",
                "…"
            ],
            "content_cleanup_rule": ""
        },
        "no_permission_reply": true,
        "empty_mention_waiting": true,
        "empty_mention_waiting_need_reply": true,
        "friend_message_needs_wake_prefix": false,
        "ignore_bot_self_message": false,
        "ignore_at_all": false
    },
    "provider_sources": [],
    "provider": [],
    "provider_settings": {
        "enable": true,
        "default_image_caption_provider_id": "",
        "image_caption_prompt": "Please describe the image using Chinese.",
        "provider_pool": [
            "*"
        ],
        "wake_prefix": "",
        "web_search": false,
        "websearch_provider": "tavily",
        "websearch_tavily_key": [],
        "websearch_bocha_key": [],
        "websearch_brave_key": [],
        "websearch_baidu_app_builder_key": "",
        "websearch_firecrawl_key": [],
        "websearch_exa_key": [],
        "websearch_anysearch_key": [],
        "websearch_deepseek_key": [],
        "websearch_serpapi_key": [],
        "web_search_link": false,
        "display_reasoning_text": false,
        "identifier": false,
        "group_name_display": false,
        "datetime_system_prompt": true,
        "persona_pool": [
            "*"
        ],
        "prompt_prefix": "{{prompt}}",
        "streaming_response": false,
        "show_tool_use_status": false,
        "show_tool_call_result": false,
        "buffer_intermediate_messages": false,
        "max_quoted_fallback_images": 20,
        "quoted_message_parser": {
            "max_component_chain_depth": 4,
            "max_forward_node_depth": 6,
            "max_forward_fetch": 32,
            "warn_on_action_failure": false
        },
        "unsupported_streaming_strategy": "realtime_segmenting",
        "reachability_check": false,
        "file_extract": {
            "enable": false,
            "provider": "moonshotai",
            "moonshotai_api_key": ""
        },
        "proactive_capability": {
            "add_cron_tools": true
        },
        "computer_use_runtime": "none",
        "computer_use_local_permissions": {
            "member": {
                "allow_execution": false,
                "allow_network": false,
                "filesystem_scope": "workspace"
            },
            "admin": {
                "allow_execution": true,
                "allow_network": true,
                "filesystem_scope": "host"
            }
        },
        "computer_use_require_admin": true,
        "sandbox": {
            "booter": "shipyard_neo",
            "shipyard_endpoint": "",
            "shipyard_access_token": "",
            "shipyard_ttl": 3600,
            "shipyard_max_sessions": 10,
            "shipyard_neo_endpoint": "",
            "shipyard_neo_access_token": "",
            "shipyard_neo_profile": "python-default",
            "shipyard_neo_ttl": 3600,
            "cua_image": "linux",
            "cua_os_type": "linux",
            "cua_idle_timeout": 0,
            "cua_telemetry_enabled": false,
            "cua_local": true,
            "cua_api_key": ""
        },
        "image_compress_options": {
            "max_size": 1280
        }
    },
    "agent": {
        "runtime": "astrbot",
        "config": {
            "model": {
                "provider_id": "",
                "fallback_provider_ids": [],
                "request_max_retries": 5
            },
            "persona": {
                "persona_id": "default",
                "safety_mode": true,
                "safety_mode_strategy": "system_prompt",
                "system_prompt": "",
                "tools": null,
                "skills": null
            },
            "compression": {
                "max_turns": -1,
                "trim_turns": 1,
                "overflow_strategy": "llm_compress",
                "instruction": "",
                "keep_recent_ratio": 0.15,
                "provider_id": "",
                "fallback_max_tokens": 128000
            },
            "misc": {
                "max_steps": 128,
                "tool_schema_mode": "full",
                "tool_call_timeout": 120,
                "sanitize_context_by_modalities": false
            },
            "subagents": {
                "enabled": false,
                "config_ids": [],
                "max_concurrent_agents": 3,
                "task_timeout": 600
            }
        }
    },
    "provider_stt_settings": {
        "enable": false,
        "provider_id": ""
    },
    "provider_tts_settings": {
        "enable": false,
        "provider_id": "",
        "dual_output": false,
        "use_file_service": false,
        "trigger_probability": 1.0
    },
    "provider_ltm_settings": {
        "group_icl_enable": false,
        "group_message_max_cnt": 1000,
        "image_caption": false,
        "image_caption_provider_id": "",
        "group_message_history_enable": false,
        "group_message_history_max_cnt": 700,
        "active_reply": {
            "enable": false,
            "method": "possibility_reply",
            "possibility_reply": 0.1,
            "whitelist": []
        }
    },
    "content_safety": {
        "also_use_in_response": false,
        "internal_keywords": {
            "enable": true,
            "extra_keywords": []
        },
        "baidu_aip": {
            "enable": false,
            "app_id": "",
            "api_key": "",
            "secret_key": ""
        }
    },
    "admins_id": [
        "astrbot"
    ],
    "t2i": false,
    "t2i_word_threshold": 150,
    "t2i_strategy": "remote",
    "t2i_endpoint": "",
    "t2i_use_file_service": false,
    "t2i_active_template": "base",
    "http_proxy": "",
    "no_proxy": [
        "localhost",
        "127.0.0.1",
        "::1",
        "10.*",
        "192.168.*"
    ],
    "dashboard": {
        "enable": true,
        "username": "astrbot",
        "password": "",
        "pbkdf2_password": "",
        "password_storage_upgraded": false,
        "password_change_required": false,
        "jwt_secret": "",
        "host": "0.0.0.0",
        "port": 6185,
        "disable_access_log": true,
        "trust_proxy_headers": false,
        "auth_rate_limit": {
            "enable": true,
            "average_interval": 1.0,
            "max_burst": 3
        },
        "totp": {
            "enable": false,
            "secret": "",
            "recovery_code_hash": ""
        },
        "ssl": {
            "enable": false,
            "cert_file": "",
            "key_file": "",
            "ca_certs": ""
        }
    },
    "platform": [],
    "platform_specific": {
        "lark": {
            "pre_ack_emoji": {
                "enable": false,
                "emojis": [
                    "Typing"
                ]
            }
        },
        "telegram": {
            "pre_ack_emoji": {
                "enable": false,
                "emojis": [
                    "✍️"
                ]
            }
        },
        "discord": {
            "pre_ack_emoji": {
                "enable": false,
                "emojis": [
                    "🤔"
                ]
            }
        }
    },
    "wake_prefix": [
        "/"
    ],
    "log_level": "INFO",
    "log_file_enable": false,
    "log_file_path": "logs/astrbot.log",
    "log_file_max_mb": 20,
    "temp_dir_max_size": 1024,
    "trace_enable": false,
    "trace_db_path": "logs/traces.db",
    "trace_db_max_mb": 80,
    "trace_retention_days": 7,
    "pip_install_arg": "",
    "pypi_index_url": "https://mirrors.aliyun.com/pypi/simple/",
    "persona": [],
    "timezone": "Asia/Shanghai",
    "callback_api_base": "",
    "default_kb_collection": "",
    "disabled_plugins": [],
    "plugin_set": [
        "*"
    ],
    "kb_names": [],
    "kb_fusion_top_k": 20,
    "kb_final_top_k": 5,
    "kb_agentic_mode": false,
    "disable_builtin_commands": false,
    "disable_metrics": false
}
```

## Field Details

### `config_version`

The current value is `6`. AstrBot maintains it during configuration migration; do not edit it manually.

### `platform_settings`

General settings for message platform adapters.

#### `platform_settings.unique_session`

Whether to enable **Isolate Conversation**. Defaults to `false`. On supported platforms, each group member has a separate conversation context when enabled. Unsupported platforms retain their existing context. Access to `/new` and `/reset` is controlled by [command permissions](../use/command.md), which follow conversation isolation by default.

#### `platform_settings.rate_limit`

Strategy when message rate exceeds limits. `time` is the window, `count` is the number of messages, and `strategy` is the limit strategy. `stall` means wait, `discard` means drop.

#### `platform_settings.reply_prefix`

Fixed prefix string when replying to messages. Default is empty.

#### `platform_settings.forward_threshold`

> Currently only applicable to the QQ platform adapter.

Message forwarding threshold. When the reply content exceeds a certain number of characters, the bot will fold the message into a QQ group "forwarded message" to prevent spamming.

In WebUI, select the profile used by your bot and open `Access Control → Whitelist` to manage the following whitelist settings.

#### `platform_settings.enable_id_white_list`

Whether to enable the ID whitelist. Default is `true`. When enabled, only messages from IDs in the whitelist will be processed.

#### `platform_settings.id_whitelist`

ID whitelist. If filled, only message events from the specified IDs will be processed. Empty means the whitelist filter is not enabled. You can use the `/sid` command to get the session ID on a platform.

Session IDs can also be found in AstrBot logs; when a message fails the whitelist, an INFO level log is output, e.g., `aiocqhttp:GroupMessage:547540978`.

#### `platform_settings.id_whitelist_log`

Whether to print logs for messages that fail the ID whitelist. Default is `true`.

#### `platform_settings.wl_ignore_admin_on_group` & `platform_settings.wl_ignore_admin_on_friend`

- `wl_ignore_admin_on_group`: Whether group messages from admins bypass the ID whitelist. Default is `true`.

- `wl_ignore_admin_on_friend`: Whether private messages from admins bypass the ID whitelist. Default is `true`.

#### `platform_settings.reply_with_mention`

Whether to @ mention the user when replying. Default is `false`.

#### `platform_settings.reply_with_quote`

Whether to quote the user's message when replying. Default is `false`.

#### `platform_settings.path_mapping`

*This configuration item has been deprecated since v4.0.0.*

List of path mappings. Used to replace file paths in messages. Each mapping item contains `from` and `to` fields, indicating that `from` in the message path is replaced with `to`.

#### `platform_settings.segmented_reply`

Segmented reply settings.

- `enable`: Whether to enable segmented replies. Default is `false`.
- `only_llm_result`: Whether to only segment replies generated by the LLM. Default is `true`.
- `interval_method`: Method for segmentation intervals. Options are `random` and `log`. Default is `random`.
- `interval`: Interval time for segmentation. For `random`, fill in two comma-separated numbers representing min and max intervals (seconds). For `log`, fill in one number representing the log base. Default is `"1.5,3.5"`.
- `log_base`: Log base, only applicable when `interval_method` is `log`. Default is `2.6`.
- `words_count_threshold`: Character limit for segmented replies. Only messages shorter than this value will be segmented; longer messages will be sent directly (unsegmented). Default is `150`.
- `regex`: Used to split a message. By default, it splits based on punctuation like periods and question marks. `re.findall(r'<regex>', text)`. Default is `".*?[。？！~…]+|.+$"`.
- `content_cleanup_rule`: Removes specified content from segments. Supports regex. For example, `[。？！]` will remove all periods, question marks, and exclamation points. `re.sub(r'<regex>', '', text)`.

#### `platform_settings.no_permission_reply`

Whether to reply with a "no permission" prompt when a user lacks authority. Default is `true`.

#### `platform_settings.empty_mention_waiting`

Whether to enable the empty @ waiting mechanism. Default is `true`. When enabled, if a user sends a message containing only an @ mention of the bot, the bot waits for the user to send the next message within 60 seconds and merges the two for processing. This is particularly useful on platforms that don't support sending @ and voice/images simultaneously.

#### `platform_settings.empty_mention_waiting_need_reply`

In the above item (`empty_mention_waiting`), if waiting is triggered, enabling this will make the bot immediately generate an LLM reply. Otherwise, it just waits without replying. Default is `true`.

#### `platform_settings.friend_message_needs_wake_prefix`

Whether private messages on platforms require a wake prefix. Default is `false`. When enabled, users must use a wake prefix to trigger a bot response in private chats.

#### `platform_settings.ignore_bot_self_message`

Whether to ignore messages sent by the bot itself. Default is `false`. When enabled, the bot won't process its own messages, preventing infinite loops on some platforms.

#### `platform_settings.ignore_at_all`

Whether to ignore @all messages. Default is `false`. When enabled, the bot won't respond to messages containing @all.

### `provider`

> This item only takes effect in `data/cmd_config.json`; AstrBot does not read this from configuration files in the `data/config/` directory.

List of configured model service provider settings.

### `provider_settings`

General settings for LLM providers.

#### `provider_settings.enable`

Whether to enable LLM chat. Default is `true`.

#### `provider_settings.default_image_caption_provider_id`

Default image captioning model provider ID. Must be a provider ID already configured in the `provider` list. If empty, image captioning is disabled.

This means when a user sends an image, AstrBot uses this provider to generate a text description, which is then used as part of the conversation context. This is useful when the conversation model doesn't support multimodal input.

#### `provider_settings.image_caption_prompt`

Prompt template for image captioning. Default is `"Please describe the image using Chinese."`.

#### `provider_settings.provider_pool`

*This configuration item is not yet in actual use.*

#### `provider_settings.wake_prefix`

Extra trigger condition for LLM chat. For example, if `chat` is filled, messages must start with `/chat` to trigger LLM chat, where `/` is the bot's wake prefix. This is a measure to prevent abuse.

#### `provider_settings.web_search`

Whether to enable AstrBot's built-in web search capability. Default is `false`. When enabled, the LLM may automatically search the web and answer based on the content.

#### `provider_settings.websearch_provider`

Web search provider type. Default is `tavily`. Currently supports `serpapi`, `deepseek`, `tavily`, `bocha`, `baidu_ai_search`, `brave`, `firecrawl`, `exa`, and `anysearch`.

- `serpapi`: Uses SerpApi Google Search, Google News, Google Images Light, Google Finance, and Google Scholar.
- `deepseek`: Uses the DeepSeek Search API.
- `tavily`: Uses the Tavily search engine.
- `bocha`: Uses the BoCha search engine.
- `baidu_ai_search`: Uses Baidu AI Search (MCP).
- `brave`: Uses Brave Search API.
- `firecrawl`: Uses the Firecrawl Search API.
- `exa`: Uses the Exa Search API.
- `anysearch`: Uses the AnySearch API.

#### `provider_settings.websearch_tavily_key`

API Key list for the Tavily search engine. Required when using `tavily` as the web search provider.

#### `provider_settings.websearch_bocha_key`

API Key list for the BoCha search engine. Required when using `bocha` as the web search provider.

#### `provider_settings.websearch_brave_key`

API Key list for the Brave search engine. Required when using `brave` as the web search provider.

#### `provider_settings.websearch_firecrawl_key`

API Key list for the Firecrawl search engine. Required when using `firecrawl` as the web search provider.

#### `provider_settings.websearch_deepseek_key`

API Key list for the DeepSeek search engine. Required when using `deepseek` as the web search provider. Can use the same API key as the chat model, but must be configured separately. Multiple keys under the same account share rate limits.

#### `provider_settings.websearch_serpapi_key`

API Key list shared by SerpApi Google Search, Google News, Google Images Light, Google Finance, and Google Scholar. Required when using `serpapi` as the web search provider. Obtain a key at [SerpApi](https://serpapi.com/manage-api-key). Multiple keys rotate, with failover on authentication and quota errors.

#### `provider_settings.web_search_link`

Whether to prompt the model to include links to search results in the reply. Default is `false`.

#### `provider_settings.display_reasoning_text`

Whether to display the model's reasoning process in the reply. Default is `false`.

#### `provider_settings.identifier`

Whether to prepend the group member's name to the prompt so the model better understands the group chat state. Default is `false`. Enabling this slightly increases token usage.

#### `provider_settings.group_name_display`

Whether to let the model know the name of the group it's in. Default is `false`. This currently only takes effect in the QQ platform adapter.

#### `provider_settings.datetime_system_prompt`

Whether to include the current machine date and time in the system prompt. Default is `true`.

#### `provider_settings.persona_pool`

*This configuration item is not yet in actual use.*

#### `provider_settings.prompt_prefix`

User prompt. You can use `{{prompt}}` as a placeholder for user input. If no placeholder is provided, it's prepended to the user input.

#### `provider_settings.streaming_response`

Whether to enable streaming responses. Defaults to `false`. Platforms with native streaming support display the reply progressively; other platforms use `provider_settings.unsupported_streaming_strategy`.

#### `provider_settings.show_tool_use_status`

Whether to show tool usage status. Default is `false`. When enabled, the model displays the tool name and input parameters when using a tool.

#### `provider_settings.unsupported_streaming_strategy`

Controls delivery on platforms without native streaming support. The default, `"realtime_segmenting"`, sends the streamed content in segments. `"turn_off"` disables streaming on those platforms.

### `agent`

`agent.runtime` selects the execution mode, and `agent.config` stores that mode's parameters. The fields below apply to the default `astrbot` runtime. External execution modes use their own configuration structures; see [Agent Execution Mode](../use/agent-runner.md).

#### `agent.runtime`

Defaults to `"astrbot"`. Other standard choices include `"dify"`, `"coze"`, `"dashscope"`, and `"deerflow"`. In the WebUI, open **Config → AI → More actions (…) → Change Agent Runtime**. Switching replaces `agent.config` with the selected mode's defaults. Copy the configuration profile first if you need to retain the original settings.

#### `agent.config.model.provider_id`

The default chat model ID, empty by default. Select a chat model configured in the `provider` list, or use **Config → AI → Model**. In the same group, `fallback_provider_ids` defaults to an empty list and `request_max_retries` defaults to `5`.

#### `agent.config.persona.persona_id`

The default persona ID, which defaults to `"default"`. Select it under **Config → AI → Persona**.

#### `agent.config.compression.max_turns`

The context's turn limit. Defaults to `-1`, which adds no turn-based limit. A positive value limits retained history turns. `-1` does not disable context processing triggered by token usage.

#### `agent.config.compression.trim_turns`

The number of oldest turns to remove at once when the turn limit is reached. Defaults to `1`. The group's `overflow_strategy` selects the context-processing strategy and defaults to `"llm_compress"`. See [Context Compression](../use/context-compress.md) for the other compression settings and WebUI instructions.

#### `agent.config.misc.max_steps`

The Agent's execution step limit, which defaults to `128`. Adjust it under **Config → AI → Advanced → Execution**.

#### `agent.config.misc.tool_call_timeout`

The tool-call timeout in seconds, which defaults to `120`. Configure it alongside the step limit under **Execution**.

#### `agent.config.subagents`

Subagent settings for the current profile. `enabled` defaults to `false`, `config_ids` to an empty list, `max_concurrent_agents` to `3`, and `task_timeout` to `600` seconds. Open **Config → AI → Capabilities → Subagents**; see [Subagents](../use/subagent.md).

### `provider_stt_settings`

General settings for Speech-to-Text (STT) providers.

#### `provider_stt_settings.enable`

Whether to enable STT services. Default is `false`.

#### `provider_stt_settings.provider_id`

STT provider ID. Must be an STT provider ID already configured in the `provider` list.

### `provider_tts_settings`

General settings for Text-to-Speech (TTS) providers.

#### `provider_tts_settings.enable`

Whether to enable TTS services. Default is `false`.

#### `provider_tts_settings.provider_id`

TTS provider ID. Must be a TTS provider ID already configured in the `provider` list.

#### `provider_tts_settings.dual_output`

Whether to enable dual output. Default is `false`. When enabled, the bot sends both text and voice messages.

#### `provider_tts_settings.use_file_service`

Whether to enable the file service. Default is `false`. When enabled, the bot provides the output voice file as an external HTTP link to the message platform. This depends on the `callback_api_base` configuration.

### `provider_ltm_settings`

General settings for group chat context awareness providers.

#### `provider_ltm_settings.group_icl_enable`

Whether to inject group chat records into the model context. Default is `false`. When enabled, the bot temporarily records group chat messages and injects them into the context for the next response.

The context content is placed in the conversation's system prompt.

#### `provider_ltm_settings.group_message_max_cnt`

Maximum number of group chat messages retained for context injection. Default is `1000`. Messages exceeding this count are discarded. This only applies when group chat record injection is enabled.

#### `provider_ltm_settings.image_caption`

Whether to automatically describe group chat images and inject the descriptions into context. Default is `false`. This only applies when group chat record injection is enabled. Use with caution as it can significantly increase API calls and token usage.

#### `provider_ltm_settings.active_reply`

- `enable`: Whether to enable active replies. Default is `false`.
- `method`: Method for active replies. Option is `possibility_reply`.
- `possibility_reply`: Probability of an active reply. Default is `0.1`. Only applicable when `method` is `possibility_reply`.
- `whitelist`: ID whitelist for active replies. Only IDs in this list will trigger active replies. Empty means no whitelist filter. You can use the `/sid` command to get the session ID on a platform.

### `content_safety`

Content safety settings.

#### `content_safety.also_use_in_response`

Whether to also perform content safety checks on LLM replies. Default is `false`. When enabled, bot-generated replies also undergo safety checks to prevent inappropriate content.

#### `content_safety.internal_keywords`

Internal keyword detection settings.

- `enable`: Whether to enable internal keyword detection. Default is `true`.
- `extra_keywords`: List of extra keywords, supports regex. Default is empty.

#### `content_safety.baidu_aip`

Baidu AI content moderation settings.

- `enable`: Whether to enable Baidu AI content moderation. Default is `false`.
- `app_id`: App ID for Baidu AI content moderation.
- `api_key`: API Key for Baidu AI content moderation.
- `secret_key`: Secret Key for Baidu AI content moderation.

> [!TIP]
> To enable Baidu AI content moderation, please `pip install baidu-aip` first.

### `admins_id`

List of administrator IDs. Additionally, you can use `/op` and `/deop` commands to add or remove admins.

In WebUI, select the profile used by your bot under `Config`, then open `Access Control → Administrators → Administrator IDs`. Send `/sid` to the bot to get your `UID`.

### `t2i`

Whether to enable Text-to-Image (T2I) functionality. Default is `false`. When enabled, if a user's message exceeds a certain character count, the bot renders the message as an image to improve readability and prevent spamming. Supports Markdown rendering.

### `t2i_word_threshold`

Character threshold for T2I. Default is `150`. When a message exceeds this count, the bot renders it as an image.

### `t2i_strategy`

Rendering strategy for T2I. Options are `local` and `remote`. Default is `remote`.

- `local`: Uses AstrBot's local T2I service for rendering. Lower quality but doesn't depend on external services.
- `remote`: Uses a remote T2I service for rendering. Uses the official AstrBot service by default, which offers better quality.

### `t2i_endpoint`

AstrBot API address. Used for rendering Markdown images. Effective when `t2i_strategy` is `remote`. Default is empty, meaning the official AstrBot service is used.

### `t2i_use_file_service`

Whether to enable the file service. Default is `false`. When enabled, the bot provides the rendered image as an external HTTP link to the message platform. This depends on the `callback_api_base` configuration.

### `http_proxy`

HTTP proxy. E.g., `http://localhost:7890`. When AstrBot runs in Docker, use an address reachable from the AstrBot container. See [Deploy with Docker](/en/deploy/astrbot/docker.md).

### `no_proxy`

List of addresses that bypass the proxy. E.g., `["localhost", "127.0.0.1"]`.

### `dashboard`

AstrBot WebUI configuration.

Please do not change the `password` value arbitrarily. It is an `md5` encoded password generated from the random initial password. Check the startup logs for that initial password on first run, then change it in the control panel.

- `enable`: Whether to enable the AstrBot WebUI. Default is `true`.
- `username`: Username for the AstrBot WebUI.
- `password`: Password for the AstrBot WebUI. It is initialized from a random password generated on first startup (logged at startup). Do not modify directly unless you know what you are doing.
- `jwt_secret`: JWT secret key. AstrBot generates this randomly at initialization. Do not modify unless you know what you are doing.
- `host`: Address the AstrBot WebUI listens on. Default is `0.0.0.0`.
- `port`: Port the AstrBot WebUI listens on. Default is `6185`.

### `platform`

> This item only takes effect in `data/cmd_config.json`; AstrBot does not read this from configuration files in the `data/config/` directory.

List of configured AstrBot message platform adapter settings.

### `platform_specific`

Platform-specific settings. Categorized by platform, then by feature group.

#### `platform_specific.<platform>.pre_ack_emoji`

When enabled, AstrBot sends a pre-reply emoji before requesting the LLM to inform the user that the request is being processed. This currently only takes effect in the Lark and Telegram platform adapters.

##### lark

- `enable`: Whether to enable pre-reply emojis for Lark messages. Default is `false`.
- `emojis`: List of pre-reply emojis. Default is `["Typing"]`. Refer to [Emoji Documentation](https://open.feishu.cn/document/server-docs/im-v1/message-reaction/emojis-introduce) for emoji names.

##### telegram

- `enable`: Whether to enable pre-reply emojis for Telegram messages. Default is `false`.
- `emojis`: List of pre-reply emojis. Default is `["✍️"]`. Telegram only supports a fixed set of reactions; refer to [reactions.txt](https://gist.github.com/Soulter/3f22c8e5f9c7e152e967e8bc28c97fc9).

##### discord

- `enable`: Whether to enable pre-reply emojis for Discord messages. Default is `false`.
- `emojis`: List of pre-reply emojis. Default is `["🤔"]`. Refer to [Discord Reaction FAQ](https://support.discord.com/hc/en-us/articles/12102061808663-Reactions-and-Super-Reactions-FAQ).

### `wake_prefix`

Wake prefix. Default is `/`. When a message starts with `/`, AstrBot is awakened.

> [!TIP]
> If the awakened session is not in the ID whitelist, AstrBot will not respond.

### `log_level`

Log level. Default is `INFO`. Can be set to `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`.

### `trace_enable`

Whether to enable trace recording. Default is `false`. Toggle it under `Settings → General → Logs → Enable Trace Recording`; this is the same setting as the trace page’s start/pause button. When enabled, AstrBot records execution traces, which can be viewed under `Data & Logs → Trace` in the admin panel.

Enabling recording also persists traces. Pausing preserves history and lets existing traces finish. The OpenTelemetry API and SDK manage span IDs, parent relationships, timestamps, status, events, and active context. Logs correlate with the active `trace_id` / `span_id`; plugins continue using `astrbot.api.logger`. AstrBot uses its own TracerProvider without replacing the global provider, adding exporters, or enabling automatic instrumentation. SQLite persistence and JSON API/SSE remain unchanged; existing history stays readable. No OTLP export is enabled. The standard `OTEL_SDK_DISABLED=true` environment variable also disables SDK tracing.

Framework entry points compose `log_context(...)`, `event_context(event)`, and the independent `trace_execution(event.trace)` scope. Only the outermost trace execution scope completes the trace after awaited processing, delivery, and history saving; failures and cancellations mark it errored and propagate unchanged. `event_context(event)` only binds the current event, registers active execution, and cleans up temporary files. `TraceSpan.context()` only binds the root span without completing it. Plugins do not need to wrap their handlers in these framework-owned execution scopes.

### `trace_db_path`

Dedicated SQLite path, default `logs/traces.db`, relative to `data`. Restart after changing the path. Log cleanup protects the database, WAL, and SHM. Trace content may contain messages, plugin arguments, and tool results; restrict file access accordingly.

### `trace_db_max_mb` / `trace_retention_days`

Positive integers, default 80 MB capacity target and 7-day retention; unlimited capacity is not supported. Expired or oldest traces are evicted as complete units. WAL, checkpoints, and page reclamation may temporarily add disk usage, so this is not an instantaneous hard limit. Per-trace content, span, and event limits also apply; detail shows truncation warnings.

Legacy settings migrate on load, with new settings taking precedence. Existing JSONL files remain untouched and are neither appended nor automatically imported:

| Old setting | New setting/behavior |
| --- | --- |
| `trace_enable` | Unchanged; controls recording and persistence of new traces |
| `trace_log_enable` | Removed; no separate JSONL toggle |
| `trace_log_path` | Removed; replaced by `trace_db_path: logs/traces.db` by default |
| `trace_log_max_mb` | When new capacity is absent, a positive integer is multiplied by 4 for `trace_db_max_mb`, approximating the old current file plus 3 backups; invalid values fall back to 80 MB |

The new `trace_retention_days` defaults to 7 days.

### `pip_install_arg`

Arguments for `pip install`. E.g., `-i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple`.

### `pypi_index_url`

PyPI index URL. Default is `https://mirrors.aliyun.com/pypi/simple/`.

### `persona`

*This configuration item has been deprecated since v4.0.0. Please use the WebUI to configure personalities.*

List of configured personalities. Each personality contains `id`, `name`, `description`, and `system_prompt` fields.

### `timezone`

Timezone setting. Please fill in an IANA timezone name, such as Asia/Shanghai. If empty, the system default timezone is used. See all timezones at: [IANA Time Zone Database](https://data.iana.org/time-zones/tzdb-2021a/zone1970.tab).

### `callback_api_base`

Base address for the AstrBot API. Used for file services, plugin callbacks, etc. E.g., `http://example.com:6185`. Default is empty, meaning file services and plugin callbacks are disabled.

### `default_kb_collection`

Default knowledge base name. Used for RAG. If empty, no knowledge base is used.

### `plugin_set`

List of enabled plugins. `*` means all available plugins are enabled. Default is `["*"]`.
