---
outline: deep
---

# AstrBot 配置文件

## data/cmd_config.json

AstrBot 的配置文件是一个 JSON 格式的文件。AstrBot 会在启动时读取这个文件，并根据文件中的配置来初始化 AstrBot，其路径位于 `data/cmd_config.json`。

> 在 AstrBot v4.0.0 版本及之后，我们引入了[多配置文件](https://blog.astrbot.app/posts/what-is-changed-in-4.0.0/#%E5%A4%9A%E9%85%8D%E7%BD%AE%E6%96%87%E4%BB%B6)的概念。`data/cmd_config.json` 作为默认配置文件 `default`。其他您在 WebUI 新建的配置文件会存储在 `data/config/` 目录下，以 `abconf_` 开头。

WebUI 中，按机器人或会话使用的行为配置（含文本转图像）在 `配置文件` 页面管理；全局运行、日志、网络和 WebUI 安全等配置在 `系统设置` 页面管理。模型连接和机器人连接分别在 `模型提供商` 和 `机器人` 页面管理。

## 升级与手动编辑 {#agent-config-migration}

当前配置结构使用 `config_version: 6`，内置 AI 的模型、人格、上下文和执行参数保存在 `agent.config` 中。首次加载尚未包含 `agent` 的旧配置时，AstrBot 会自动迁移旧设置；旧的 `agent_runner` 根项会转换为 `agent`，内置运行时名称由 `local` 改为 `astrbot`。正常升级无需手动搬迁这些字段。

升级后，已有的 `agent` 配置是读取这些设置的依据。手动修改 JSON 或更新配置脚本时，请使用下表的新路径；重新写入旧的 `provider_settings` 字段不会覆盖 `agent.config`，这些旧键会在配置加载时被清理。

| 旧路径 | 当前路径（AstrBot 内置 AI） |
| --- | --- |
| `provider_settings.default_provider_id` | `agent.config.model.provider_id` |
| `provider_settings.default_personality` | `agent.config.persona.persona_id` |
| `provider_settings.max_context_length` | `agent.config.compression.max_turns` |
| `provider_settings.dequeue_context_length` | `agent.config.compression.trim_turns` |
| `provider_settings.max_agent_step` | `agent.config.misc.max_steps` |
| `provider_settings.tool_call_timeout` | `agent.config.misc.tool_call_timeout` |

`provider_settings` 仍保存 AI 总开关和通用消息设置，包括 `enable`、`wake_prefix`、`web_search` 和 `streaming_response`。这些有效字段继续使用原路径。

也可在 **配置文件 → AI** 中编辑：**模型** 设置对话模型，**人格** 选择人格，**高级** 调整上下文和执行设置。完成后点击 **保存配置**。接入第三方应用时，请参见 [Agent 执行方式](../use/agent-runner.md)。

## 默认配置示例

下面是当前源码中完整的默认配置，已展开 AstrBot 内置 AI 的 `agent.config`。示例不包含初始化时生成的认证信息；配置现有实例时，将需要修改的字段合并到已有配置中。

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

## 字段详解

### `config_version`

当前值为 `6`，由 AstrBot 在迁移配置时维护，请勿手动修改。

### `platform_settings`

消息平台适配器的通用设置。

#### `platform_settings.unique_session`

是否启用「隔离对话」。默认为 `false`。启用后，支持隔离的渠道会为每位群成员使用独立上下文；不支持隔离的渠道仍使用原有上下文。`/new` 和 `/reset` 的权限由[指令管理设置](../use/command.md)决定，默认跟随对话是否隔离。

#### `platform_settings.rate_limit`

当消息速率超过限制时的处理策略。`time` 为时间窗口，`count` 为消息数量，`strategy` 为限制策略。`stall` 为等待，`discard` 为丢弃。

#### `platform_settings.reply_prefix`

回复消息时的固定前缀字符串。默认为空。

#### `platform_settings.forward_threshold`

> 目前仅 QQ 平台适配器适用。

消息转发阈值。当回复内容超过一定字数后，机器人会将消息折叠成 QQ 群聊的 “转发消息”，以防止刷屏。

在 WebUI 中，选择机器人使用的配置文件，进入 `访问控制 → 白名单` 管理以下白名单设置。

#### `platform_settings.enable_id_white_list`

是否启用 ID 白名单。默认为 `true`。启用后，只有在白名单中的 ID 发来的消息才会被处理。

#### `platform_settings.id_whitelist`

ID 白名单。填写后，将只处理所填写的 ID 发来的消息事件。为空时表示不启用白名单过滤。可以使用 `/sid` 指令获取在某个平台上的会话 ID。

也可在 AstrBot 日志内获取会话 ID，当一条消息没通过白名单时，会输出 INFO 级别的日志，格式类似 `aiocqhttp:GroupMessage:547540978`

#### `platform_settings.id_whitelist_log`

是否打印未通过 ID 白名单的消息日志。默认为 `true`。

#### `platform_settings.wl_ignore_admin_on_group` & `platform_settings.wl_ignore_admin_on_friend`

- `wl_ignore_admin_on_group`: 是否管理员发送的群组消息无视 ID 白名单。默认为 `true`。

- `wl_ignore_admin_on_friend`: 是否管理员发送的私聊消息无视 ID 白名单。默认为 `true`。

#### `platform_settings.reply_with_mention`

是否在回复消息时 @ 提到用户。默认为 `false`。

#### `platform_settings.reply_with_quote`

是否在回复消息时引用用户的消息。默认为 `false`。

#### `platform_settings.path_mapping`

*该配置项已经在 v4.0.0 版本之后被废弃。*

路径映射列表。用于将消息中的文件路径进行替换。每个映射项包含 `from` 和 `to` 两个字段，表示将消息中的 `from` 路径替换为 `to` 路径。

#### `platform_settings.segmented_reply`

分段回复设置。

- `enable`: 是否启用分段回复。默认为 `false`。
- `only_llm_result`: 是否仅对 LLM 生成的回复进行分段。默认为 `true`。
- `interval_method`: 分段间隔方法。可选值为 `random` 和 `log`。默认为 `random`。
- `interval`: 分段间隔时间。对于 `random` 方法，填写两个逗号分隔的数字，表示最小和最大间隔时间（单位：秒）。对于 `log` 方法，填写一个数字，表示对数基底。默认为 `"1.5,3.5"`。
- `log_base`: 对数基底，仅在 `interval_method` 为 `log` 时适用。默认为 `2.6`。
- `words_count_threshold`: 分段回复的字数上限。只有字数小于此值的消息才会被分段，超过此值的长消息将直接发送（不分段）。默认为 `150`。
- `regex`: 用于分隔一段消息。默认情况下会根据句号、问号等标点符号分隔。`re.findall(r'<regex>', text)`。默认值为 `".*?[。？！~…]+|.+$"`。
- `content_cleanup_rule`: 移除分段后的内容中的指定的内容。支持正则表达式。如填写 `[。？！]` 将移除所有的句号、问号、感叹号。`re.sub(r'<regex>', '', text)`。

#### `platform_settings.no_permission_reply`

是否在用户没有权限时回复无权限的提示消息。默认为 `true`。

#### `platform_settings.empty_mention_waiting`

是否启用空 @ 等待机制。默认为 `true`。启用后，当用户发送一条仅包含 @ 机器人的消息时，机器人会等待用户在 60 秒内发送下一条消息，并将两条消息合并后进行处理。这在某些平台不支持 @ 和语音/图片等消息同时发送时特别有用。

#### `platform_settings.empty_mention_waiting_need_reply`

在上面一个配置项(`empty_mention_waiting`)中，如果启用了触发等待，启用此项后，机器人会立即使用 LLM 生成一条回复。否则，将不回复而只是等待。默认为 `true`。

#### `platform_settings.friend_message_needs_wake_prefix`

是否在消息平台的私聊消息中需要唤醒前缀。默认为 `false`。启用后，在私聊消息中，用户需要使用唤醒前缀才能触发机器人的响应。

#### `platform_settings.ignore_bot_self_message`

是否忽略机器人自己发送的消息。默认为 `false`。启用后，机器人将不会处理自己发送的消息，在某些平台可以防止死循环。

#### `platform_settings.ignore_at_all`

是否忽略 @ 全体成员的消息。默认为 `false`。启用后，机器人将不会响应包含 @ 全体成员的消息。

### `provider`

> 此配置项仅在 `data/cmd_config.json` 中生效，AstrBot 不会读取 `data/config/` 目录下的配置文件中的此项。

已配置的模型服务提供商的配置列表。

### `provider_settings`

大语言模型提供商的通用设置。

#### `provider_settings.enable`

是否启用大语言模型聊天。默认为 `true`。

#### `provider_settings.default_image_caption_provider_id`

默认的图像描述模型提供商 ID。必须是 `provider` 列表中已配置的提供商 ID。如果为空，则代表不使用图像描述功能。

此配置项的意思是，当用户发送一张图片时，AstrBot 会使用此提供商来生成对图片的描述文本，并将描述文本作为对话的上下文之一。这在对话模型不支持多模态输入时特别有用。

#### `provider_settings.image_caption_prompt`

图像描述的提示词模板。默认为 `"Please describe the image using Chinese."`。

#### `provider_settings.provider_pool`

*此配置项尚未实际使用*

#### `provider_settings.wake_prefix`

使用 LLM 聊天额外的触发条件。如填写 `chat`，则需要发送消息时要以 `/chat` 才能触发 LLM 聊天。其中 `/` 是机器人的唤醒前缀。是一个防止滥用的手段。

#### `provider_settings.web_search`

是否启用 AstrBot 自带的网页搜索能力。默认为 `false`。启用后，LLM 可能会自动搜索网页并根据内容回答。

#### `provider_settings.websearch_provider`

网页搜索提供商类型。默认为 `tavily`。目前支持 `serpapi`、`deepseek`、`tavily`、`bocha`、`baidu_ai_search`、`brave`、`firecrawl`、`exa`、`anysearch`。

- `serpapi`：使用 SerpApi Google Search、Google News、Google Images Light、Google Finance 和 Google Scholar。
- `deepseek`：使用 DeepSeek Search API。
- `tavily`：使用 Tavily 搜索引擎。
- `bocha`：使用 BoCha 搜索引擎。
- `baidu_ai_search`：使用百度 AI Search（MCP）。
- `brave`：使用 Brave Search API。
- `firecrawl`：使用 Firecrawl Search API。
- `exa`：使用 Exa Search API。
- `anysearch`：使用 AnySearch API。

#### `provider_settings.websearch_tavily_key`

Tavily 搜索引擎的 API Key 列表。使用 `tavily` 作为网页搜索提供商时需要填写。

#### `provider_settings.websearch_bocha_key`

BoCha 搜索引擎的 API Key 列表。使用 `bocha` 作为网页搜索提供商时需要填写。

#### `provider_settings.websearch_brave_key`

Brave 搜索引擎的 API Key 列表。使用 `brave` 作为网页搜索提供商时需要填写。

#### `provider_settings.websearch_firecrawl_key`

Firecrawl 搜索引擎的 API Key 列表。使用 `firecrawl` 作为网页搜索提供商时需要填写。

#### `provider_settings.websearch_deepseek_key`

DeepSeek 搜索引擎的 API Key 列表。使用 `deepseek` 作为网页搜索提供商时需要填写。可使用与对话模型相同的 API Key，配置相互独立。同账号下的多个 Key 共享 QPS 限制。

#### `provider_settings.websearch_serpapi_key`

SerpApi Google Search、Google News、Google Images Light、Google Finance 和 Google Scholar 共用的 API Key 列表。使用 `serpapi` 作为网页搜索提供商时需要填写。前往 [SerpApi](https://serpapi.com/manage-api-key) 获取 Key。多个 Key 轮询使用，鉴权或额度错误时会尝试下一个 Key。

#### `provider_settings.web_search_link`

是否在回复中提示模型附上搜索结果的链接。默认为 `false`。

#### `provider_settings.display_reasoning_text`

是否在回复中显示模型的推理过程。默认为 `false`。

#### `provider_settings.identifier`

是否在 Prompt 前加上群成员的名字以让模型更好地了解群聊状态。默认为 `false`。启用将略微增加 token 开销。

#### `provider_settings.group_name_display`

是否在提示模型了解所在群的名称。默认为 `false`。此配置项目前仅在 QQ 平台适配器中生效。

#### `provider_settings.datetime_system_prompt`

是否在系统提示词中加上当前机器的日期时间。默认为 `true`。

#### `provider_settings.persona_pool`

*此配置项尚未实际使用*

#### `provider_settings.prompt_prefix`

用户提示词。可使用 `{{prompt}}` 作为用户输入的占位符。如果不输入占位符则代表添加在用户输入的前面。

#### `provider_settings.streaming_response`

是否启用流式响应，默认为 `false`。支持原生流式输出的平台会逐步显示回复；其他平台按 `provider_settings.unsupported_streaming_strategy` 处理。

#### `provider_settings.show_tool_use_status`

是否显示工具使用状态。默认为 `false`。启用后，模型在使用工具时会显示工具的名称和输入参数。

#### `provider_settings.unsupported_streaming_strategy`

平台不支持原生流式回复时的处理方式，默认为 `"realtime_segmenting"`：将流式内容分段发送。设为 `"turn_off"` 时，在这些平台上关闭流式输出。

### `agent`

`agent.runtime` 选择执行方式，`agent.config` 保存该方式的参数。以下字段说明适用于默认的 `astrbot` 运行时。第三方执行方式使用各自的配置结构，详见 [Agent 执行方式](../use/agent-runner.md)。

#### `agent.runtime`

默认为 `"astrbot"`。其他标准选项包括 `"dify"`、`"coze"`、`"dashscope"` 和 `"deerflow"`。WebUI 入口为 **配置文件 → AI → 更多操作（…）→ 切换 Agent Runtime**。切换会将 `agent.config` 替换为目标执行方式的默认配置；如需保留原设置，请先复制配置文件。

#### `agent.config.model.provider_id`

默认对话模型的 ID，默认为空字符串。选择 `provider` 列表中已配置的对话模型，也可通过 **配置文件 → AI → 模型** 设置。同组的 `fallback_provider_ids` 默认为空列表，`request_max_retries` 默认为 `5`。

#### `agent.config.persona.persona_id`

默认人格的 ID，默认为 `"default"`。可通过 **配置文件 → AI → 人格** 选择。

#### `agent.config.compression.max_turns`

上下文的轮数上限，默认为 `-1`，表示不增加按轮数计算的限制。正数会限制保留的历史轮数。`-1` 不会关闭基于 Token 用量触发的上下文整理。

#### `agent.config.compression.trim_turns`

触发轮数限制时，一次移除的最旧对话轮数，默认为 `1`。上下文整理策略由同组的 `overflow_strategy` 控制，默认值为 `"llm_compress"`。其他压缩选项和 WebUI 操作见 [上下文压缩](../use/context-compress.md)。

#### `agent.config.misc.max_steps`

Agent 的执行步数上限，默认为 `128`。可在 **配置文件 → AI → 高级 → 执行设置** 中调整。

#### `agent.config.misc.tool_call_timeout`

工具调用的超时时间，单位为秒，默认为 `120`。与步数上限一起在 **执行设置** 中配置。

#### `agent.config.subagents`

当前配置文件的子代理设置。`enabled` 默认为 `false`，`config_ids` 默认为空列表，`max_concurrent_agents` 默认为 `3`，`task_timeout` 默认为 `600` 秒。入口为 **配置文件 → AI → 能力 → 子代理**，详见 [子代理](../use/subagent.md)。

### `provider_stt_settings`

语音转文本服务提供商的通用设置。

#### `provider_stt_settings.enable`

是否启用语音转文本服务。默认为 `false`。

#### `provider_stt_settings.provider_id`

语音转文本服务提供商 ID。必须是 `provider` 列表中已配置的 STT 提供商 ID。

### `provider_tts_settings`

文本转语音服务提供商的通用设置。

#### `provider_tts_settings.enable`

是否启用文本转语音服务。默认为 `false`。

#### `provider_tts_settings.provider_id`

文本转语音服务提供商 ID。必须是 `provider` 列表中已配置的 TTS 提供商 ID。

#### `provider_tts_settings.dual_output`

是否启用双输出。默认为 `false`。启用后，机器人会同时发送文本和语音消息。

#### `provider_tts_settings.use_file_service`

是否启用文件服务。默认为 `false`。启用后，机器人会将输出的语音文件以 HTTP 文件外链的形式提供给消息平台。此配置项依赖于 `callback_api_base` 的配置。

### `provider_ltm_settings`

群聊上下文感知服务提供商的通用设置。

#### `provider_ltm_settings.group_icl_enable`

是否将群聊记录注入模型上下文。默认为 `false`。启用后，机器人会暂存群聊中的对话内容，并在下一次回复时注入模型上下文。

上下文的内容会被放在对话的系统提示词中。

#### `provider_ltm_settings.group_message_max_cnt`

注入上下文所保留的最大群聊消息数量。默认为 `1000`。超过此数量的消息将被丢弃。仅在群聊记录注入上下文开启时生效。

#### `provider_ltm_settings.image_caption`

是否自动使用群聊图片转述模型生成图片描述并注入上下文。默认为 `false`。仅在群聊记录注入上下文开启时生效。请谨慎使用，因为这可能会增加大量的 API 调用和 token 开销。

#### `provider_ltm_settings.active_reply`

- `enable`: 是否启用主动回复。默认为 `false`。
- `method`: 主动回复的方法。可选值为 `possibility_reply`。
- `possibility_reply`: 主动回复的概率。默认为 `0.1`。仅在 `method` 为 `possibility_reply` 时适用。
- `whitelist`: 主动回复的 ID 白名单。仅在此列表中的 ID 才会触发主动回复。为空时表示不启用白名单过滤。可以使用 `/sid` 指令获取在某个平台上的会话 ID。

### `content_safety`

内容安全设置。

#### `content_safety.also_use_in_response`

是否在 LLM 回复中也进行内容安全检查。默认为 `false`。启用后，机器人生成的回复也会经过内容安全检查，以防止生成不当内容。

#### `content_safety.internal_keywords`

内部关键词检测设置。

- `enable`: 是否启用内部关键词检测。默认为 `true`。
- `extra_keywords`: 额外的关键词列表，支持正则表达式。默认为空。

#### `content_safety.baidu_aip`

百度 AI 内容审核设置。

- `enable`: 是否启用百度 AI 内容审核。默认为 `false`。
- `app_id`: 百度 AI 内容审核的 App ID。
- `api_key`: 百度 AI 内容审核的 API Key。
- `secret_key`: 百度 AI 内容审核的 Secret Key。

> [!TIP]
> 如果要启用百度 AI 内容审核，请先 `pip install baidu-aip`。

### `admins_id`

管理员 ID 列表。此外，还可以使用 `/op`, `/deop` 指令来添加或删除管理员。

在 WebUI 的 `配置文件` 中选择机器人使用的配置文件，再进入 `访问控制 → 管理员 → 管理员 ID` 设置。给机器人发送 `/sid` 指令以获取 `UID`。

### `t2i`

是否启用文本转图像功能。默认为 `false`。启用后，当用户发送的消息超过一定字数时，机器人会将消息渲染成图片发送给用户，以提高可读性并防止刷屏。支持 Markdown 渲染。

### `t2i_word_threshold`

文本转图像的字数阈值。默认为 `150`。当用户发送的消息超过此字数时，机器人会将消息渲染成图片发送给用户。

### `t2i_strategy`

文本转图像的渲染策略。可选值为 `local` 和 `remote`。默认为 `remote`。

- `local`: 使用 AstrBot 本地的文本转图像服务进行渲染。效果较差，但不依赖外部服务。
- `remote`: 使用远程的文本转图像服务进行渲染。默认使用 AstrBot 官方提供的服务，效果较好。

### `t2i_endpoint`

AstrBot API 的地址。用于渲染 Markdown 图片。当 `t2i_strategy` 为 `remote` 时生效。默认为空，表示使用 AstrBot 官方提供的服务。

### `t2i_use_file_service`

是否启用文件服务。默认为 `false`。启用后，机器人会将渲染的图片以 HTTP 文件外链的形式提供给消息平台。此配置项依赖于 `callback_api_base` 的配置。

### `http_proxy`

HTTP 代理。如 `http://localhost:7890`。Docker 部署时请填写 AstrBot 容器能访问到的地址，见 [Docker 部署](/deploy/astrbot/docker.md)。

### `no_proxy`

不使用代理的地址列表。如 `["localhost", "127.0.0.1"]`。

### `dashboard`

AstrBot WebUI 配置。

请不要随意修改 `password` 的值。它是随机初始密码经过 `md5` 编码后的值。首次启动时请在日志中获取初始密码，并在控制面板中修改。

- `enable`: 是否启用 AstrBot WebUI。默认为 `true`。
- `username`: AstrBot WebUI 的用户名。
- `password`: AstrBot WebUI 的密码。首次启动会随机生成初始密码（已在日志中打印），这里保存的是该密码的 `md5` 值。请勿直接修改，除非您知道自己在做什么。
- `jwt_secret`: JWT 的密钥。AstrBot 会在初始化时随机生成。请勿修改，除非您知道自己在做什么。
- `host`: AstrBot WebUI 监听的地址。默认为 `0.0.0.0`。
- `port`: AstrBot WebUI 监听的端口。默认为 `6185`。

### `platform`

> 此配置项仅在 `data/cmd_config.json` 中生效，AstrBot 不会读取 `data/config/` 目录下的配置文件中的此项。

已配置的 AstrBot 消息平台适配器的配置列表。

### `platform_specific`

平台特异配置。按平台分类，平台下按功能分组。

#### `platform_specific.<platform>.pre_ack_emoji`

启用后，当请求 LLM 前，AstrBot 会先发送一个预回复的表情以告知用户正在处理请求。此功能目前仅在飞书平台适配器和 Telegram 中生效。

##### lark (飞书)

- `enable`: 是否启用飞书消息预回复表情。默认为 `false`。
- `emojis`: 预回复的表情列表。默认为 `["Typing"]`。表情枚举名参考：[表情文案说明](https://open.feishu.cn/document/server-docs/im-v1/message-reaction/emojis-introduce)

##### telegram

- `enable`: 是否启用 Telegram 消息预回复表情。默认为 `false`。
- `emojis`: 预回复的表情列表。默认为 `["✍️"]`。Telegram 仅支持固定反应集合，参考：[reactions.txt](https://gist.github.com/Soulter/3f22c8e5f9c7e152e967e8bc28c97fc9)

##### discord

- `enable`: 是否启用 Discord 消息预回复表情。默认为 `false`。
- `emojis`: 预回复的表情列表。默认为 `["🤔"]`。Discord反应支持参考：[Discord Reaction FAQ](https://support.discord.com/hc/en-us/articles/12102061808663-Reactions-and-Super-Reactions-FAQ)

### `wake_prefix`

唤醒前缀。默认为 `/`。当消息以 `/` 开头时，AstrBot 会被唤醒。

> [!TIP]
> 如果唤醒的会话不在 ID 白名单中，AstrBot 将不会响应。

### `log_level`

日志级别。默认为 `INFO`。可以设置为 `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`。

### `trace_enable`

是否启用追踪记录。默认为 `false`。可在 `设置 → 常规 → 日志 → 启用追踪记录` 中切换，与追踪页的启动/暂停按钮共用同一配置。启用后，AstrBot 会记录运行追踪信息，可以在管理面板的 `数据与日志 → 追踪` 页面查看。

开启后自动持久化；暂停不删除历史，已开始的追踪仍会记录完成状态。OpenTelemetry API 和 SDK 负责 Span ID、父子关系、起止时间、状态、事件和活动上下文。日志会关联当前活动的 `trace_id` / `span_id`，插件仍使用原来的 `astrbot.api.logger`。AstrBot 使用独立的 TracerProvider，不替换全局 Provider，不添加导出器或自动埋点。SQLite 持久化、JSON API/SSE 和现有历史数据格式保持不变，不启用 OTLP 导出。标准环境变量 `OTEL_SDK_DISABLED=true` 也会关闭 SDK 追踪。

框架入口组合使用 `log_context(...)`、`event_context(event)` 和独立的 `trace_execution(event.trace)`。只有最外层追踪执行作用域在消息处理、发送及历史保存结束后完成追踪；异常或取消会标记错误并原样抛出。`event_context(event)` 仅负责绑定当前事件、注册活动事件及清理临时文件；`TraceSpan.context()` 仅绑定根 Span，不负责结束追踪。插件无需在处理器中调用这些由框架入口管理的执行作用域。

### `trace_db_path`

独立 SQLite 路径，默认 `logs/traces.db`（相对 `data` 目录），更改路径后重启生效。数据库、WAL 和 SHM 不受“清理日志”影响。追踪正文可能包含消息、插件参数和工具结果，请限制数据库文件访问权限。

### `trace_db_max_mb` / `trace_retention_days`

正整数，默认容量目标 80 MB、保留 7 天，不支持无限容量。达到容量或过期后按完整 trace 淘汰旧数据；WAL、检查点和回收页面可能暂时增加磁盘占用，因此容量不是瞬时硬上限。单条追踪也有内容、Span 和事件数量限制，截断会在详情中提示。

旧配置在加载时自动迁移，新配置优先，旧 JSONL 文件保留但不再写入或自动导入：

| 旧配置 | 新配置/行为 |
| --- | --- |
| `trace_enable` | 保持不变，控制新追踪记录与持久化 |
| `trace_log_enable` | 移除，不再单独开关 JSONL |
| `trace_log_path` | 移除，默认改用 `trace_db_path: logs/traces.db` |
| `trace_log_max_mb` | 未指定新容量时，正整数乘 4 迁移为 `trace_db_max_mb`（接近原当前文件加 3 份备份预算）；无效值改用 80 MB |

新增 `trace_retention_days` 默认为 7 天。

### `pip_install_arg`

`pip install` 的参数。如 `-i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple`。

### `pypi_index_url`

PyPI 镜像源地址。默认为 `https://mirrors.aliyun.com/pypi/simple/`。

### `persona`

*此配置项已经在 v4.0.0 版本之后被废弃。请使用 WebUI 来配置人格。*

已配置的人格列表。每个人格包含 `id`, `name`, `description`, `system_prompt` 四个字段。

### `timezone`

时区设置。请填写 IANA 时区名称, 如 Asia/Shanghai, 为空时使用系统默认时区。所有时区请查看: [IANA Time Zone Database](https://data.iana.org/time-zones/tzdb-2021a/zone1970.tab)。

### `callback_api_base`

AstrBot API 的基础地址。用于文件服务和插件回调等功能。如 `http://example.com:6185`。默认为空，表示不启用文件服务和插件回调功能。

### `default_kb_collection`

默认知识库名称。用于 RAG 功能。如果为空，则不使用知识库。

### `plugin_set`

已启用的插件列表。`*` 表示启用所有可用的插件。默认为 `["*"]`。
