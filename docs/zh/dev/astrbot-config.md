---
outline: deep
---

# AstrBot 配置文件

## data/cmd_config.json

AstrBot 的配置文件是一个 JSON 格式的文件。AstrBot 会在启动时读取这个文件，并根据文件中的配置来初始化 AstrBot，其路径位于 `data/cmd_config.json`。

> 在 AstrBot v4.0.0 版本及之后，我们引入了[多配置文件](https://blog.astrbot.app/posts/what-is-changed-in-4.0.0/#%E5%A4%9A%E9%85%8D%E7%BD%AE%E6%96%87%E4%BB%B6)的概念。`data/cmd_config.json` 作为默认配置文件 `default`。其他您在 WebUI 新建的配置文件会存储在 `data/config/` 目录下，以 `abconf_` 开头。

AstrBot 默认配置如下：

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
        "provider_pool": ["*"],  # "*" 表示使用所有可用的提供者
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
        # 平台特异配置：按平台分类，平台下按功能分组
        "lark": {
            "pre_ack_emoji": {"enable": False, "emojis": ["Typing"]},
        },
        "telegram": {
            "pre_ack_emoji": {"enable": False, "emojis": ["✍️"]},
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
    "default_kb_collection": "",  # 默认知识库名称
    "plugin_set": ["*"],  # "*" 表示使用所有可用的插件, 空列表表示不使用任何插件
}
```

## 字段详解

### `config_version`

配置文件版本，请勿修改。

### `platform_settings`

消息平台适配器的通用设置。

#### `platform_settings.unique_session`

是否启用会话隔离。默认为 `false`。启用后，在群组或者频道中，每个人的对话的上下文都是独立的。

#### `platform_settings.rate_limit`

当消息速率超过限制时的处理策略。`time` 为时间窗口，`count` 为消息数量，`strategy` 为限制策略。`stall` 为等待，`discard` 为丢弃。

#### `platform_settings.reply_prefix`

回复消息时的固定前缀字符串。默认为空。

#### `platform_settings.forward_threshold`

> 目前仅 QQ 平台适配器适用。

消息转发阈值。当回复内容超过一定字数后，机器人会将消息折叠成 QQ 群聊的 “转发消息”，以防止刷屏。

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

#### `provider_settings.default_provider_id`

默认的对话模型提供商 ID。必须是 `provider` 列表中已配置的提供商 ID。如果为空，则使用配置列表中的第一个对话模型提供商。

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

网页搜索提供商类型。默认为 `default`。目前支持 `default` 和 `tavily`。

- `default`：能访问 Google 时效果最佳。如果 Google 访问失败，程序会依次访问 Bing, Sogo 搜索引擎。

- `tavily`：使用 Tavily 搜索引擎。

#### `provider_settings.websearch_tavily_key`

Tavily 搜索引擎的 API Key 列表。使用 `tavily` 作为网页搜索提供商时需要填写。

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

#### `provider_settings.default_personality`

默认使用的人格的 ID。请在 WebUI 配置人格。

#### `provider_settings.persona_pool`

*此配置项尚未实际使用*

#### `provider_settings.prompt_prefix`

用户提示词。可使用 `{{prompt}}` 作为用户输入的占位符。如果不输入占位符则代表添加在用户输入的前面。

#### `provider_settings.max_context_length`

当对话上下文超出这个数量时丢弃最旧的部分，一轮聊天记为 1 条。-1 为不限制。

#### `provider_settings.dequeue_context_length`

当触发上面提到的 `max_context_length` 限制时，每次丢弃的对话轮数。

#### `provider_settings.streaming_response`

是否启用流式响应。默认为 `false`。启用后，模型的回复会实时类似打字机的效果发送给用户。此配置项仅在 WebChat、Telegram、飞书平台生效。

#### `provider_settings.show_tool_use_status`

是否显示工具使用状态。默认为 `false`。启用后，模型在使用工具时会显示工具的名称和输入参数。

#### `provider_settings.streaming_segmented`

不支持流式响应的消息平台是否降级为使用分段回复。默认为 `false`。意思是，如果启用了流式响应，但当前消息平台不支持流式响应，那么是否使用分段多次回复来代替。

#### `provider_settings.max_agent_step`

Agent 最大步骤数限制。默认为 `30`。模型的每次工具调用算作一步。

#### `provider_settings.tool_call_timeout`

Added in `v4.3.5`

工具调用的最大超时时间（秒），默认为 `60` 秒。

#### `provider_stt_settings`

语音转文本服务提供商的通用设置。

#### `provider_stt_settings.enable`

是否启用语音转文本服务。默认为 `false`。

#### `provider_stt_settings.provider_id`

语音转文本服务提供商 ID。必须是 `provider` 列表中已配置的 STT 提供商 ID。

#### `provider_tts_settings`

文本转语音服务提供商的通用设置。

#### `provider_tts_settings.enable`

是否启用文本转语音服务。默认为 `false`。

#### `provider_tts_settings.provider_id`

文本转语音服务提供商 ID。必须是 `provider` 列表中已配置的 TTS 提供商 ID。

#### `provider_tts_settings.dual_output`

是否启用双输出。默认为 `false`。启用后，机器人会同时发送文本和语音消息。

#### `provider_tts_settings.use_file_service`

是否启用文件服务。默认为 `false`。启用后，机器人会将输出的语音文件以 HTTP 文件外链的形式提供给消息平台。此配置项依赖于 `callback_api_base` 的配置。

#### `provider_ltm_settings`

群聊上下文感知服务提供商的通用设置。

#### `provider_ltm_settings.group_icl_enable`

是否启用群聊上下文感知。默认为 `false`。启用后，机器人会记录群聊中的对话内容，以便更好地理解群聊的上下文。

上下文的内容会被放在对话的系统提示词中。

#### `provider_ltm_settings.group_message_max_cnt`

群聊消息的最大记录数量。默认为 `100`。超过此数量的消息将被丢弃。

#### `provider_ltm_settings.image_caption`

是否记录群聊中的图片，并自动使用图像描述模型生成图片的描述文本。默认为 `false`。此配置项依赖于 `provider_settings.default_image_caption_provider_id` 的配置。请谨慎使用，因为这可能会增加大量的 API 调用和 token 开销。

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

HTTP 代理。如 `http://localhost:7890`。

### `no_proxy`

不使用代理的地址列表。如 `["localhost", "127.0.0.1"]`。

### `dashboard`

AstrBot WebUI 配置。

请不要随意修改 `password` 的值。它是一个经过 `md5` 编码的密码。请在控制面板修改密码。

- `enable`: 是否启用 AstrBot WebUI。默认为 `true`。
- `username`: AstrBot WebUI 的用户名。默认为 `astrbot`。
- `password`: AstrBot WebUI 的密码。默认为 `astrbot` 的 `md5` 编码值。请勿直接修改，除非您知道自己在做什么。
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

#### telegram

- `enable`: 是否启用 Telegram 消息预回复表情。默认为 `false`。
- `emojis`: 预回复的表情列表。默认为 `["✍️"]`。Telegram 仅支持固定反应集合，参考：[reactions.txt](https://gist.github.com/Soulter/3f22c8e5f9c7e152e967e8bc28c97fc9)

### `wake_prefix`

唤醒前缀。默认为 `/`。当消息以 `/` 开头时，AstrBot 会被唤醒。

> [!TIP]
> 如果唤醒的会话不在 ID 白名单中，AstrBot 将不会响应。

### `log_level`

日志级别。默认为 `INFO`。可以设置为 `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`。

### `trace_enable`

是否启用追踪记录。默认为 `false`。启用后，AstrBot 会记录运行追踪信息，可以在管理面板的 Trace 页面查看。

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
