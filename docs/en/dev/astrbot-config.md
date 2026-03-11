---
outline: deep
---

# AstrBot Configuration File

## data/cmd_config.json

AstrBot's configuration file is a JSON format file. AstrBot reads this file at startup and initializes based on the settings within. Its path is `data/cmd_config.json`.

> Since AstrBot v4.0.0, we introduced the concept of [multiple configuration files](https://blog.astrbot.app/posts/what-is-changed-in-4.0.0/#%E5%A4%9A%E9%85%8D%E7%BD%AE%E6%96%87%E4%BB%B6). `data/cmd_config.json` serves as the default configuration `default`. Other configuration files you create in the WebUI are stored in the `data/config/` directory, starting with `abconf_`.

The default AstrBot configuration is as follows:

```jsonc
{
    "config_version": 2,
    "platform_settings": {
        "unique_session": False,
        "rate_limit": {
            "time": 60,
            "count": 30,
            "strategy": "stall",  # stall, discard
        },
        "reply_prefix": "",
        "forward_threshold": 1500,
        "enable_id_white_list": True,
        "id_whitelist": [],
        "id_whitelist_log": True,
        "wl_ignore_admin_on_group": True,
        "wl_ignore_admin_on_friend": True,
        "reply_with_mention": False,
        "reply_with_quote": False,
        "path_mapping": [],
        "segmented_reply": {
            "enable": False,
            "only_llm_result": True,
            "interval_method": "random",
            "interval": "1.5,3.5",
            "log_base": 2.6,
            "words_count_threshold": 150,
            "regex": ".*?[。？！~…]+|.+$",
            "content_cleanup_rule": "",
        },
        "no_permission_reply": True,
        "empty_mention_waiting": True,
        "empty_mention_waiting_need_reply": True,
        "friend_message_needs_wake_prefix": False,
        "ignore_bot_self_message": False,
        "ignore_at_all": False,
    },
    "provider": [],
    "provider_settings": {
        "enable": True,
        "default_provider_id": "",
        "default_image_caption_provider_id": "",
        "image_caption_prompt": "Please describe the image using Chinese.",
        "provider_pool": ["*"],  # "*" means use all available providers
        "wake_prefix": "",
        "web_search": False,
        "websearch_provider": "default",
        "websearch_tavily_key": [],
        "web_search_link": False,
        "display_reasoning_text": False,
        "identifier": False,
        "group_name_display": False,
        "datetime_system_prompt": True,
        "default_personality": "default",
        "persona_pool": ["*"],
        "prompt_prefix": "{{prompt}}",
        "max_context_length": -1,
        "dequeue_context_length": 1,
        "streaming_response": False,
        "show_tool_use_status": False,
        "streaming_segmented": False,
        "max_agent_step": 30,
        "tool_call_timeout": 60,
    },
    "provider_stt_settings": {
        "enable": False,
        "provider_id": "",
    },
    "provider_tts_settings": {
        "enable": False,
        "provider_id": "",
        "dual_output": False,
        "use_file_service": False,
    },
    "provider_ltm_settings": {
        "group_icl_enable": False,
        "group_message_max_cnt": 300,
        "image_caption": False,
        "active_reply": {
            "enable": False,
            "method": "possibility_reply",
            "possibility_reply": 0.1,
            "whitelist": [],
        },
    },
    "content_safety": {
        "also_use_in_response": False,
        "internal_keywords": {"enable": True, "extra_keywords": []},
        "baidu_aip": {"enable": False, "app_id": "", "api_key": "", "secret_key": ""},
    },
    "admins_id": ["astrbot"],
    "t2i": False,
    "t2i_word_threshold": 150,
    "t2i_strategy": "remote",
    "t2i_endpoint": "",
    "t2i_use_file_service": False,
    "t2i_active_template": "base",
    "http_proxy": "",
    "no_proxy": ["localhost", "127.0.0.1", "::1"],
    "dashboard": {
        "enable": True,
        "username": "astrbot",
        "password": "77b90590a8945a7d36c963981a307dc9",
        "jwt_secret": "",
        "host": "0.0.0.0",
        "port": 6185,
    },
    "platform": [],
    "platform_specific": {
        # Platform-specific settings: categorized by platform, then by feature group
        "lark": {
            "pre_ack_emoji": {"enable": False, "emojis": ["Typing"]},
        },
        "telegram": {
            "pre_ack_emoji": {"enable": False, "emojis": ["✍️"]},
        },
        "discord": {
            "pre_ack_emoji": {"enable": False, "emojis": ["🤔"]},
        },
    },
    "wake_prefix": ["/"],
    "log_level": "INFO",
    "trace_enable": False,
    "pip_install_arg": "",
    "pypi_index_url": "https://mirrors.aliyun.com/pypi/simple/",
    "persona": [],  # deprecated
    "timezone": "Asia/Shanghai",
    "callback_api_base": "",
    "default_kb_collection": "",  # Default knowledge base name
    "plugin_set": ["*"],  # "*" means use all available plugins, empty list means none
}
```

## Field Details

### `config_version`

Configuration version, do not modify.

### `platform_settings`

General settings for message platform adapters.

#### `platform_settings.unique_session`

Whether to enable session isolation. Default is `false`. When enabled, each person's conversation context in groups or channels is independent.

#### `platform_settings.rate_limit`

Strategy when message rate exceeds limits. `time` is the window, `count` is the number of messages, and `strategy` is the limit strategy. `stall` means wait, `discard` means drop.

#### `platform_settings.reply_prefix`

Fixed prefix string when replying to messages. Default is empty.

#### `platform_settings.forward_threshold`

> Currently only applicable to the QQ platform adapter.

Message forwarding threshold. When the reply content exceeds a certain number of characters, the bot will fold the message into a QQ group "forwarded message" to prevent spamming.

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

#### `provider_settings.default_provider_id`

Default conversation model provider ID. Must be a provider ID already configured in the `provider` list. If empty, the first provider in the list is used.

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

Web search provider type. Default is `default`. Currently supports `default` and `tavily`.

- `default`: Works best when Google is accessible. If Google fails, it tries Bing and Sogou in order.

- `tavily`: Uses the Tavily search engine.

#### `provider_settings.websearch_tavily_key`

API Key list for the Tavily search engine. Required when using `tavily` as the web search provider.

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

#### `provider_settings.default_personality`

ID of the default personality to use. Configure personalities in the WebUI.

#### `provider_settings.persona_pool`

*This configuration item is not yet in actual use.*

#### `provider_settings.prompt_prefix`

User prompt. You can use `{{prompt}}` as a placeholder for user input. If no placeholder is provided, it's prepended to the user input.

#### `provider_settings.max_context_length`

When the conversation context exceeds this number, the oldest parts are discarded. One round of chat counts as 1. -1 means no limit.

#### `provider_settings.dequeue_context_length`

The number of conversation rounds to discard each time the `max_context_length` limit is triggered.

#### `provider_settings.streaming_response`

Whether to enable streaming responses. Default is `false`. When enabled, the model's reply is sent to the user in real-time with a typewriter effect. This only takes effect on WebChat, Telegram, and Lark platforms.

#### `provider_settings.show_tool_use_status`

Whether to show tool usage status. Default is `false`. When enabled, the model displays the tool name and input parameters when using a tool.

#### `provider_settings.streaming_segmented`

Whether platforms that don't support streaming responses should fall back to segmented replies. Default is `false`. This means if streaming is enabled but the platform doesn't support it, segmented multiple replies are used instead.

#### `provider_settings.max_agent_step`

Limit on the maximum number of Agent steps. Default is `30`. Each tool call by the model counts as one step.

#### `provider_settings.tool_call_timeout`

Added in `v4.3.5`

Maximum timeout for tool calls (seconds), default is `60` seconds.

#### `provider_stt_settings`

General settings for Speech-to-Text (STT) providers.

#### `provider_stt_settings.enable`

Whether to enable STT services. Default is `false`.

#### `provider_stt_settings.provider_id`

STT provider ID. Must be an STT provider ID already configured in the `provider` list.

#### `provider_tts_settings`

General settings for Text-to-Speech (TTS) providers.

#### `provider_tts_settings.enable`

Whether to enable TTS services. Default is `false`.

#### `provider_tts_settings.provider_id`

TTS provider ID. Must be a TTS provider ID already configured in the `provider` list.

#### `provider_tts_settings.dual_output`

Whether to enable dual output. Default is `false`. When enabled, the bot sends both text and voice messages.

#### `provider_tts_settings.use_file_service`

Whether to enable the file service. Default is `false`. When enabled, the bot provides the output voice file as an external HTTP link to the message platform. This depends on the `callback_api_base` configuration.

#### `provider_ltm_settings`

General settings for group chat context awareness providers.

#### `provider_ltm_settings.group_icl_enable`

Whether to enable group chat context awareness. Default is `false`. When enabled, the bot records group chat conversations to better understand context.

The context content is placed in the conversation's system prompt.

#### `provider_ltm_settings.group_message_max_cnt`

Maximum number of group chat messages to record. Default is `100`. Messages exceeding this count are discarded.

#### `provider_ltm_settings.image_caption`

Whether to record images in group chats and automatically generate text descriptions using an image captioning model. Default is `false`. This depends on the `provider_settings.default_image_caption_provider_id` configuration. Use with caution as it can significantly increase API calls and token usage.

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

HTTP proxy. E.g., `http://localhost:7890`.

### `no_proxy`

List of addresses that bypass the proxy. E.g., `["localhost", "127.0.0.1"]`.

### `dashboard`

AstrBot WebUI configuration.

Please do not change the `password` value arbitrarily. It is an `md5` encoded password. Change the password in the control panel.

- `enable`: Whether to enable the AstrBot WebUI. Default is `true`.
- `username`: Username for the AstrBot WebUI. Default is `astrbot`.
- `password`: Password for the AstrBot WebUI. Default is the `md5` encoded value of `astrbot`. Do not modify directly unless you know what you are doing.
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

Whether to enable trace recording. Default is `false`. When enabled, AstrBot records execution traces, which can be viewed on the Trace page of the admin panel.

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
