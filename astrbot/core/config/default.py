"""
如需修改配置，请在 `data/cmd_config.json` 中修改或者在管理面板中可视化修改。
"""

import os

from astrbot.core.utils.astrbot_path import get_astrbot_data_path

VERSION = "4.0.0-beta.3"
DB_PATH = os.path.join(get_astrbot_data_path(), "data_v4.db")

# 默认配置
DEFAULT_CONFIG = {
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
        "websearch_tavily_key": "",
        "web_search_link": False,
        "display_reasoning_text": False,
        "identifier": False,
        "datetime_system_prompt": True,
        "default_personality": "default",
        "persona_pool": ["*"],
        "prompt_prefix": "",
        "max_context_length": -1,
        "dequeue_context_length": 1,
        "streaming_response": False,
        "show_tool_use_status": False,
        "streaming_segmented": False,
        "max_agent_step": 30,
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
    "wake_prefix": ["/"],
    "log_level": "INFO",
    "pip_install_arg": "",
    "pypi_index_url": "https://mirrors.aliyun.com/pypi/simple/",
    "persona": [],  # deprecated
    "timezone": "Asia/Shanghai",
    "callback_api_base": "",
    "default_kb_collection": "",  # 默认知识库名称
    "plugin_set": ["*"],  # "*" 表示使用所有可用的插件, 空列表表示不使用任何插件
}


# 配置项的中文描述、值类型
CONFIG_METADATA_2 = {
    "platform_group": {
        "metadata": {
            "platform": {
                "description": "消息平台适配器",
                "type": "list",
                "config_template": {
                    "QQ 官方机器人(WebSocket)": {
                        "id": "default",
                        "type": "qq_official",
                        "enable": False,
                        "appid": "",
                        "secret": "",
                        "enable_group_c2c": True,
                        "enable_guild_direct_message": True,
                    },
                    "QQ 官方机器人(Webhook)": {
                        "id": "default",
                        "type": "qq_official_webhook",
                        "enable": False,
                        "appid": "",
                        "secret": "",
                        "callback_server_host": "0.0.0.0",
                        "port": 6196,
                    },
                    "QQ 个人号(aiocqhttp)": {
                        "id": "default",
                        "type": "aiocqhttp",
                        "enable": False,
                        "ws_reverse_host": "0.0.0.0",
                        "ws_reverse_port": 6199,
                        "ws_reverse_token": "",
                    },
                    "微信个人号(WeChatPadPro)": {
                        "id": "wechatpadpro",
                        "type": "wechatpadpro",
                        "enable": False,
                        "admin_key": "stay33",
                        "host": "这里填写你的局域网IP或者公网服务器IP",
                        "port": 8059,
                        "wpp_active_message_poll": False,
                        "wpp_active_message_poll_interval": 3,
                    },
                    "微信公众平台": {
                        "id": "weixin_official_account",
                        "type": "weixin_official_account",
                        "enable": False,
                        "appid": "",
                        "secret": "",
                        "token": "",
                        "encoding_aes_key": "",
                        "api_base_url": "https://api.weixin.qq.com/cgi-bin/",
                        "callback_server_host": "0.0.0.0",
                        "port": 6194,
                        "active_send_mode": False,
                    },
                    "企业微信(含微信客服)": {
                        "id": "wecom",
                        "type": "wecom",
                        "enable": False,
                        "corpid": "",
                        "secret": "",
                        "token": "",
                        "encoding_aes_key": "",
                        "kf_name": "",
                        "api_base_url": "https://qyapi.weixin.qq.com/cgi-bin/",
                        "callback_server_host": "0.0.0.0",
                        "port": 6195,
                    },
                    "飞书(Lark)": {
                        "id": "lark",
                        "type": "lark",
                        "enable": False,
                        "lark_bot_name": "",
                        "app_id": "",
                        "app_secret": "",
                        "domain": "https://open.feishu.cn",
                    },
                    "钉钉(DingTalk)": {
                        "id": "dingtalk",
                        "type": "dingtalk",
                        "enable": False,
                        "client_id": "",
                        "client_secret": "",
                    },
                    "Telegram": {
                        "id": "telegram",
                        "type": "telegram",
                        "enable": False,
                        "telegram_token": "your_bot_token",
                        "start_message": "Hello, I'm AstrBot!",
                        "telegram_api_base_url": "https://api.telegram.org/bot",
                        "telegram_file_base_url": "https://api.telegram.org/file/bot",
                        "telegram_command_register": True,
                        "telegram_command_auto_refresh": True,
                        "telegram_command_register_interval": 300,
                    },
                    "Discord": {
                        "id": "discord",
                        "type": "discord",
                        "enable": False,
                        "discord_token": "",
                        "discord_proxy": "",
                        "discord_command_register": True,
                        "discord_guild_id_for_debug": "",
                        "discord_activity_name": "",
                    },
                    "Slack": {
                        "id": "slack",
                        "type": "slack",
                        "enable": False,
                        "bot_token": "",
                        "app_token": "",
                        "signing_secret": "",
                        "slack_connection_mode": "socket",  # webhook, socket
                        "slack_webhook_host": "0.0.0.0",
                        "slack_webhook_port": 6197,
                        "slack_webhook_path": "/astrbot-slack-webhook/callback",
                    },
                },
                "items": {
                    "slack_connection_mode": {
                        "description": "Slack Connection Mode",
                        "type": "string",
                        "options": ["webhook", "socket"],
                        "hint": "The connection mode for Slack. `webhook` uses a webhook server, `socket` uses Slack's Socket Mode.",
                    },
                    "slack_webhook_host": {
                        "description": "Slack Webhook Host",
                        "type": "string",
                        "hint": "Only valid when Slack connection mode is `webhook`.",
                    },
                    "slack_webhook_port": {
                        "description": "Slack Webhook Port",
                        "type": "int",
                        "hint": "Only valid when Slack connection mode is `webhook`.",
                    },
                    "slack_webhook_path": {
                        "description": "Slack Webhook Path",
                        "type": "string",
                        "hint": "Only valid when Slack connection mode is `webhook`.",
                    },
                    "active_send_mode": {
                        "description": "是否换用主动发送接口",
                        "type": "bool",
                        "desc": "只有企业认证的公众号才能主动发送。主动发送接口的限制会少一些。",
                    },
                    "wpp_active_message_poll": {
                        "description": "是否启用主动消息轮询",
                        "type": "bool",
                        "hint": "只有当你发现微信消息没有按时同步到 AstrBot 时，才需要启用这个功能，默认不启用。",
                    },
                    "wpp_active_message_poll_interval": {
                        "description": "主动消息轮询间隔",
                        "type": "int",
                        "hint": "主动消息轮询间隔，单位为秒，默认 3 秒，最大不要超过 60 秒，否则可能被认为是旧消息。",
                    },
                    "kf_name": {
                        "description": "微信客服账号名",
                        "type": "string",
                        "hint": "可选。微信客服账号名(不是 ID)。可在 https://kf.weixin.qq.com/kf/frame#/accounts 获取",
                    },
                    "telegram_token": {
                        "description": "Bot Token",
                        "type": "string",
                        "hint": "如果你的网络环境为中国大陆，请在 `其他配置` 处设置代理或更改 api_base。",
                    },
                    "telegram_command_register": {
                        "description": "Telegram 命令注册",
                        "type": "bool",
                        "hint": "启用后，AstrBot 将会自动注册 Telegram 命令。",
                    },
                    "telegram_command_auto_refresh": {
                        "description": "Telegram 命令自动刷新",
                        "type": "bool",
                        "hint": "启用后，AstrBot 将会在运行时自动刷新 Telegram 命令。(单独设置此项无效)",
                    },
                    "telegram_command_register_interval": {
                        "description": "Telegram 命令自动刷新间隔",
                        "type": "int",
                        "hint": "Telegram 命令自动刷新间隔，单位为秒。",
                    },
                    "id": {
                        "description": "机器人名称",
                        "type": "string",
                        "hint": "机器人名称",
                    },
                    "type": {
                        "description": "适配器类型",
                        "type": "string",
                        "invisible": True,
                    },
                    "enable": {
                        "description": "启用",
                        "type": "bool",
                        "hint": "是否启用该适配器。未启用的适配器对应的消息平台将不会接收到消息。",
                    },
                    "appid": {
                        "description": "appid",
                        "type": "string",
                        "hint": "必填项。QQ 官方机器人平台的 appid。如何获取请参考文档。",
                    },
                    "secret": {
                        "description": "secret",
                        "type": "string",
                        "hint": "必填项。",
                    },
                    "enable_group_c2c": {
                        "description": "启用消息列表单聊",
                        "type": "bool",
                        "hint": "启用后，机器人可以接收到 QQ 消息列表中的私聊消息。你可能需要在 QQ 机器人平台上通过扫描二维码的方式添加机器人为你的好友。详见文档。",
                    },
                    "enable_guild_direct_message": {
                        "description": "启用频道私聊",
                        "type": "bool",
                        "hint": "启用后，机器人可以接收到频道的私聊消息。",
                    },
                    "ws_reverse_host": {
                        "description": "反向 Websocket 主机地址(AstrBot 为服务器端)",
                        "type": "string",
                        "hint": "aiocqhttp 适配器的反向 Websocket 服务器 IP 地址，不包含端口号。",
                    },
                    "ws_reverse_port": {
                        "description": "反向 Websocket 端口",
                        "type": "int",
                        "hint": "aiocqhttp 适配器的反向 Websocket 端口。",
                    },
                    "ws_reverse_token": {
                        "description": "反向 Websocket Token",
                        "type": "string",
                        "hint": "aiocqhttp 适配器的反向 Websocket Token。未设置则不启用 Token 验证。",
                    },
                    "lark_bot_name": {
                        "description": "飞书机器人的名字",
                        "type": "string",
                        "hint": "请务必填对，否则 @ 机器人将无法唤醒，只能通过前缀唤醒。",
                    },
                    "discord_token": {
                        "description": "Discord Bot Token",
                        "type": "string",
                        "hint": "在此处填入你的Discord Bot Token",
                    },
                    "discord_proxy": {
                        "description": "Discord 代理地址",
                        "type": "string",
                        "hint": "可选的代理地址：http://ip:port",
                    },
                    "discord_command_register": {
                        "description": "是否自动将插件指令注册为 Discord 斜杠指令",
                        "type": "bool",
                    },
                    "discord_activity_name": {
                        "description": "Discord 活动名称",
                        "type": "string",
                        "hint": "可选的 Discord 活动名称。留空则不设置活动。",
                    },
                },
            },
            "platform_settings": {
                "type": "object",
                "items": {
                    "unique_session": {
                        "type": "bool",
                    },
                    "rate_limit": {
                        "type": "object",
                        "items": {
                            "time": {"type": "int"},
                            "count": {"type": "int"},
                            "strategy": {
                                "type": "string",
                                "options": ["stall", "discard"],
                            },
                        },
                    },
                    "no_permission_reply": {
                        "type": "bool",
                        "hint": "启用后，当用户没有权限执行某个操作时，机器人会回复一条消息。",
                    },
                    "empty_mention_waiting": {
                        "type": "bool",
                        "hint": "启用后，当消息内容只有 @ 机器人时，会触发等待，在 60 秒内的该用户的任意一条消息均会唤醒机器人。这在某些平台不支持 @ 和语音/图片等消息同时发送时特别有用。",
                    },
                    "empty_mention_waiting_need_reply": {
                        "type": "bool",
                        "hint": "在上面一个配置项中，如果启用了触发等待，启用此项后，机器人会使用 LLM 生成一条回复。否则，将不回复而只是等待。",
                    },
                    "friend_message_needs_wake_prefix": {
                        "type": "bool",
                        "hint": "启用后，私聊消息需要唤醒前缀才会被处理，同群聊一样。",
                    },
                    "ignore_bot_self_message": {
                        "type": "bool",
                        "hint": "某些平台会将自身账号在其他 APP 端发送的消息也当做消息事件下发导致给自己发消息时唤醒机器人",
                    },
                    "ignore_at_all": {
                        "type": "bool",
                        "hint": "启用后，机器人会忽略 @ 全体成员 的消息事件。",
                    },
                    "segmented_reply": {
                        "type": "object",
                        "items": {
                            "enable": {
                                "type": "bool",
                            },
                            "only_llm_result": {
                                "type": "bool",
                            },
                            "interval_method": {
                                "type": "string",
                                "options": ["random", "log"],
                                "hint": "分段回复的间隔时间计算方法。random 为随机时间，log 为根据消息长度计算，$y=log_<log_base>(x)$，x为字数，y的单位为秒。",
                            },
                            "interval": {
                                "type": "string",
                                "hint": "`random` 方法用。每一段回复的间隔时间，格式为 `最小时间,最大时间`。如 `0.75,2.5`",
                            },
                            "log_base": {
                                "type": "float",
                                "hint": "`log` 方法用。对数函数的底数。默认为 2.6",
                            },
                            "words_count_threshold": {
                                "type": "int",
                                "hint": "超过这个字数的消息不会被分段回复。默认为 150",
                            },
                            "regex": {
                                "type": "string",
                                "hint": "用于分隔一段消息。默认情况下会根据句号、问号等标点符号分隔。re.findall(r'<regex>', text)",
                            },
                            "content_cleanup_rule": {
                                "type": "string",
                                "hint": "移除分段后的内容中的指定的内容。支持正则表达式。如填写 `[。？！]` 将移除所有的句号、问号、感叹号。re.sub(r'<regex>', '', text)",
                            },
                        },
                    },
                    "reply_prefix": {
                        "type": "string",
                        "hint": "机器人回复消息时带有的前缀。",
                    },
                    "forward_threshold": {
                        "type": "int",
                        "hint": "超过一定字数后，机器人会将消息折叠成 QQ 群聊的 “转发消息”，以防止刷屏。目前仅 QQ 平台适配器适用。",
                    },
                    "enable_id_white_list": {
                        "type": "bool",
                    },
                    "id_whitelist": {
                        "type": "list",
                        "items": {"type": "string"},
                        "hint": "只处理填写的 ID 发来的消息事件，为空时不启用。可使用 /sid 指令获取在平台上的会话 ID(类似 abc:GroupMessage:123)。管理员可使用 /wl 添加白名单",
                    },
                    "id_whitelist_log": {
                        "type": "bool",
                        "hint": "启用后，当一条消息没通过白名单时，会输出 INFO 级别的日志。",
                    },
                    "wl_ignore_admin_on_group": {
                        "type": "bool",
                    },
                    "wl_ignore_admin_on_friend": {
                        "type": "bool",
                    },
                    "reply_with_mention": {
                        "type": "bool",
                        "hint": "启用后，机器人回复消息时会 @ 发送者。实际效果以具体的平台适配器为准。",
                    },
                    "reply_with_quote": {
                        "type": "bool",
                        "hint": "启用后，机器人回复消息时会引用原消息。实际效果以具体的平台适配器为准。",
                    },
                    "path_mapping": {
                        "type": "list",
                        "items": {"type": "string"},
                        "hint": "此功能解决由于文件系统不一致导致路径不存在的问题。格式为 <原路径>:<映射路径>。如 `/app/.config/QQ:/var/lib/docker/volumes/xxxx/_data`。这样，当消息平台下发的事件中图片和语音路径以 `/app/.config/QQ` 开头时，开头被替换为 `/var/lib/docker/volumes/xxxx/_data`。这在 AstrBot 或者平台协议端使用 Docker 部署时特别有用。",
                    },
                },
            },
            "content_safety": {
                "type": "object",
                "items": {
                    "also_use_in_response": {
                        "type": "bool",
                        "hint": "启用后，大模型的响应也会通过内容安全审核。",
                    },
                    "baidu_aip": {
                        "type": "object",
                        "items": {
                            "enable": {
                                "type": "bool",
                                "hint": "启用此功能前，您需要手动在设备中安装 baidu-aip 库。一般来说，安装指令如下: `pip3 install baidu-aip`",
                            },
                            "app_id": {"description": "APP ID", "type": "string"},
                            "api_key": {"description": "API Key", "type": "string"},
                            "secret_key": {
                                "type": "string",
                            },
                        },
                    },
                    "internal_keywords": {
                        "type": "object",
                        "items": {
                            "enable": {
                                "type": "bool",
                            },
                            "extra_keywords": {
                                "type": "list",
                                "items": {"type": "string"},
                                "hint": "额外的屏蔽关键词列表，支持正则表达式。",
                            },
                        },
                    },
                },
            },
        },
    },
    "provider_group": {
        "name": "服务提供商",
        "metadata": {
            "provider": {
                "type": "list",
                "config_template": {
                    "OpenAI": {
                        "id": "openai",
                        "provider": "openai",
                        "type": "openai_chat_completion",
                        "provider_type": "chat_completion",
                        "enable": True,
                        "key": [],
                        "api_base": "https://api.openai.com/v1",
                        "timeout": 120,
                        "model_config": {"model": "gpt-4o-mini", "temperature": 0.4},
                        "modalities": ["text", "image", "tool_use"],
                        "hint": "也兼容所有与 OpenAI API 兼容的服务。",
                    },
                    "Azure OpenAI": {
                        "id": "azure",
                        "provider": "azure",
                        "type": "openai_chat_completion",
                        "provider_type": "chat_completion",
                        "enable": True,
                        "api_version": "2024-05-01-preview",
                        "key": [],
                        "api_base": "",
                        "timeout": 120,
                        "model_config": {"model": "gpt-4o-mini", "temperature": 0.4},
                        "modalities": ["text", "image", "tool_use"],
                    },
                    "xAI": {
                        "id": "xai",
                        "provider": "xai",
                        "type": "openai_chat_completion",
                        "provider_type": "chat_completion",
                        "enable": True,
                        "key": [],
                        "api_base": "https://api.x.ai/v1",
                        "timeout": 120,
                        "model_config": {"model": "grok-2-latest", "temperature": 0.4},
                        "modalities": ["text", "image", "tool_use"],
                    },
                    "Anthropic": {
                        "hint": "注意Claude系列模型的温度调节范围为0到1.0，超出可能导致报错",
                        "id": "claude",
                        "provider": "anthropic",
                        "type": "anthropic_chat_completion",
                        "provider_type": "chat_completion",
                        "enable": True,
                        "key": [],
                        "api_base": "https://api.anthropic.com/v1",
                        "timeout": 120,
                        "model_config": {
                            "model": "claude-3-5-sonnet-latest",
                            "max_tokens": 4096,
                            "temperature": 0.2,
                        },
                        "modalities": ["text", "image", "tool_use"],
                    },
                    "Ollama": {
                        "hint": "启用前请确保已正确安装并运行 Ollama 服务端，Ollama默认不带鉴权，无需修改key",
                        "id": "ollama_default",
                        "provider": "ollama",
                        "type": "openai_chat_completion",
                        "provider_type": "chat_completion",
                        "enable": True,
                        "key": ["ollama"],  # ollama 的 key 默认是 ollama
                        "api_base": "http://localhost:11434/v1",
                        "model_config": {"model": "llama3.1-8b", "temperature": 0.4},
                        "modalities": ["text", "image", "tool_use"],
                    },
                    "LM Studio": {
                        "id": "lm_studio",
                        "provider": "lm_studio",
                        "type": "openai_chat_completion",
                        "provider_type": "chat_completion",
                        "enable": True,
                        "key": ["lmstudio"],
                        "api_base": "http://localhost:1234/v1",
                        "model_config": {
                            "model": "llama-3.1-8b",
                        },
                        "modalities": ["text", "image", "tool_use"],
                    },
                    "Gemini(OpenAI兼容)": {
                        "id": "gemini_default",
                        "provider": "google",
                        "type": "openai_chat_completion",
                        "provider_type": "chat_completion",
                        "enable": True,
                        "key": [],
                        "api_base": "https://generativelanguage.googleapis.com/v1beta/openai/",
                        "timeout": 120,
                        "model_config": {
                            "model": "gemini-1.5-flash",
                            "temperature": 0.4,
                        },
                        "modalities": ["text", "image", "tool_use"],
                    },
                    "Gemini": {
                        "id": "gemini_default",
                        "provider": "google",
                        "type": "googlegenai_chat_completion",
                        "provider_type": "chat_completion",
                        "enable": True,
                        "key": [],
                        "api_base": "https://generativelanguage.googleapis.com/",
                        "timeout": 120,
                        "model_config": {
                            "model": "gemini-2.0-flash-exp",
                            "temperature": 0.4,
                        },
                        "gm_resp_image_modal": False,
                        "gm_native_search": False,
                        "gm_native_coderunner": False,
                        "gm_url_context": False,
                        "gm_safety_settings": {
                            "harassment": "BLOCK_MEDIUM_AND_ABOVE",
                            "hate_speech": "BLOCK_MEDIUM_AND_ABOVE",
                            "sexually_explicit": "BLOCK_MEDIUM_AND_ABOVE",
                            "dangerous_content": "BLOCK_MEDIUM_AND_ABOVE",
                        },
                        "gm_thinking_config": {
                            "budget": 0,
                        },
                        "modalities": ["text", "image", "tool_use"],
                    },
                    "DeepSeek": {
                        "id": "deepseek_default",
                        "provider": "deepseek",
                        "type": "openai_chat_completion",
                        "provider_type": "chat_completion",
                        "enable": True,
                        "key": [],
                        "api_base": "https://api.deepseek.com/v1",
                        "timeout": 120,
                        "model_config": {"model": "deepseek-chat", "temperature": 0.4},
                        "modalities": ["text", "image", "tool_use"],
                    },
                    "302.AI": {
                        "id": "302ai",
                        "provider": "302ai",
                        "type": "openai_chat_completion",
                        "provider_type": "chat_completion",
                        "enable": True,
                        "key": [],
                        "api_base": "https://api.302.ai/v1",
                        "timeout": 120,
                        "model_config": {"model": "gpt-4.1-mini", "temperature": 0.4},
                        "modalities": ["text", "image", "tool_use"],
                    },
                    "硅基流动": {
                        "id": "siliconflow",
                        "provider": "siliconflow",
                        "type": "openai_chat_completion",
                        "provider_type": "chat_completion",
                        "enable": True,
                        "key": [],
                        "timeout": 120,
                        "api_base": "https://api.siliconflow.cn/v1",
                        "model_config": {
                            "model": "deepseek-ai/DeepSeek-V3",
                            "temperature": 0.4,
                        },
                        "modalities": ["text", "image", "tool_use"],
                    },
                    "PPIO派欧云": {
                        "id": "ppio",
                        "provider": "ppio",
                        "type": "openai_chat_completion",
                        "provider_type": "chat_completion",
                        "enable": True,
                        "key": [],
                        "api_base": "https://api.ppinfra.com/v3/openai",
                        "timeout": 120,
                        "model_config": {
                            "model": "deepseek/deepseek-r1",
                            "temperature": 0.4,
                        },
                    },
                    "优云智算": {
                        "id": "compshare",
                        "provider": "compshare",
                        "type": "openai_chat_completion",
                        "provider_type": "chat_completion",
                        "enable": True,
                        "key": [],
                        "api_base": "https://api.modelverse.cn/v1",
                        "timeout": 120,
                        "model_config": {
                            "model": "moonshotai/Kimi-K2-Instruct",
                        },
                        "modalities": ["text", "image", "tool_use"],
                    },
                    "Kimi": {
                        "id": "moonshot",
                        "provider": "moonshot",
                        "type": "openai_chat_completion",
                        "provider_type": "chat_completion",
                        "enable": True,
                        "key": [],
                        "timeout": 120,
                        "api_base": "https://api.moonshot.cn/v1",
                        "model_config": {"model": "moonshot-v1-8k", "temperature": 0.4},
                        "modalities": ["text", "image", "tool_use"],
                    },
                    "智谱 AI": {
                        "id": "zhipu_default",
                        "provider": "zhipu",
                        "type": "zhipu_chat_completion",
                        "provider_type": "chat_completion",
                        "enable": True,
                        "key": [],
                        "timeout": 120,
                        "api_base": "https://open.bigmodel.cn/api/paas/v4/",
                        "model_config": {
                            "model": "glm-4-flash",
                        },
                        "modalities": ["text", "image", "tool_use"],
                    },
                    "Dify": {
                        "id": "dify_app_default",
                        "provider": "dify",
                        "type": "dify",
                        "provider_type": "chat_completion",
                        "enable": True,
                        "dify_api_type": "chat",
                        "dify_api_key": "",
                        "dify_api_base": "https://api.dify.ai/v1",
                        "dify_workflow_output_key": "astrbot_wf_output",
                        "dify_query_input_key": "astrbot_text_query",
                        "variables": {},
                        "timeout": 60,
                        "hint": "请确保你在 AstrBot 里设置的 APP 类型和 Dify 里面创建的应用的类型一致！",
                    },
                    "阿里云百炼应用": {
                        "id": "dashscope",
                        "provider": "dashscope",
                        "type": "dashscope",
                        "provider_type": "chat_completion",
                        "enable": True,
                        "dashscope_app_type": "agent",
                        "dashscope_api_key": "",
                        "dashscope_app_id": "",
                        "rag_options": {
                            "pipeline_ids": [],
                            "file_ids": [],
                            "output_reference": False,
                        },
                        "variables": {},
                        "timeout": 60,
                    },
                    "ModelScope": {
                        "id": "modelscope",
                        "provider": "modelscope",
                        "type": "openai_chat_completion",
                        "provider_type": "chat_completion",
                        "enable": True,
                        "key": [],
                        "timeout": 120,
                        "api_base": "https://api-inference.modelscope.cn/v1",
                        "model_config": {"model": "Qwen/Qwen3-32B", "temperature": 0.4},
                        "modalities": ["text", "image", "tool_use"],
                    },
                    "FastGPT": {
                        "id": "fastgpt",
                        "provider": "fastgpt",
                        "type": "openai_chat_completion",
                        "provider_type": "chat_completion",
                        "enable": True,
                        "key": [],
                        "api_base": "https://api.fastgpt.in/api/v1",
                        "timeout": 60,
                    },
                    "Whisper(API)": {
                        "id": "whisper",
                        "provider": "openai",
                        "type": "openai_whisper_api",
                        "provider_type": "speech_to_text",
                        "enable": False,
                        "api_key": "",
                        "api_base": "",
                        "model": "whisper-1",
                    },
                    "Whisper(本地加载)": {
                        "hint": "启用前请 pip 安装 openai-whisper 库（N卡用户大约下载 2GB，主要是 torch 和 cuda，CPU 用户大约下载 1 GB），并且安装 ffmpeg。否则将无法正常转文字。",
                        "provider": "openai",
                        "type": "openai_whisper_selfhost",
                        "provider_type": "speech_to_text",
                        "enable": False,
                        "id": "whisper_selfhost",
                        "model": "tiny",
                    },
                    "SenseVoice(本地加载)": {
                        "hint": "启用前请 pip 安装 funasr、funasr_onnx、torchaudio、torch、modelscope、jieba 库（默认使用CPU，大约下载 1 GB），并且安装 ffmpeg。否则将无法正常转文字。",
                        "type": "sensevoice_stt_selfhost",
                        "provider": "sensevoice",
                        "provider_type": "speech_to_text",
                        "enable": False,
                        "id": "sensevoice",
                        "stt_model": "iic/SenseVoiceSmall",
                        "is_emotion": False,
                    },
                    "OpenAI TTS(API)": {
                        "id": "openai_tts",
                        "type": "openai_tts_api",
                        "provider": "openai",
                        "provider_type": "text_to_speech",
                        "enable": False,
                        "api_key": "",
                        "api_base": "",
                        "model": "tts-1",
                        "openai-tts-voice": "alloy",
                        "timeout": "20",
                    },
                    "Edge TTS": {
                        "hint": "提示：使用这个服务前需要安装有 ffmpeg，并且可以直接在终端调用 ffmpeg 指令。",
                        "id": "edge_tts",
                        "provider": "microsoft",
                        "type": "edge_tts",
                        "provider_type": "text_to_speech",
                        "enable": False,
                        "edge-tts-voice": "zh-CN-XiaoxiaoNeural",
                        "timeout": 20,
                    },
                    "GSV TTS(本地加载)": {
                        "id": "gsv_tts",
                        "enable": False,
                        "provider": "gpt_sovits",
                        "type": "gsv_tts_selfhost",
                        "provider_type": "text_to_speech",
                        "api_base": "http://127.0.0.1:9880",
                        "gpt_weights_path": "",
                        "sovits_weights_path": "",
                        "timeout": 60,
                        "gsv_default_parms": {
                            "gsv_ref_audio_path": "",
                            "gsv_prompt_text": "",
                            "gsv_prompt_lang": "zh",
                            "gsv_aux_ref_audio_paths": "",
                            "gsv_text_lang": "zh",
                            "gsv_top_k": 5,
                            "gsv_top_p": 1.0,
                            "gsv_temperature": 1.0,
                            "gsv_text_split_method": "cut3",
                            "gsv_batch_size": 1,
                            "gsv_batch_threshold": 0.75,
                            "gsv_split_bucket": True,
                            "gsv_speed_factor": 1,
                            "gsv_fragment_interval": 0.3,
                            "gsv_streaming_mode": False,
                            "gsv_seed": -1,
                            "gsv_parallel_infer": True,
                            "gsv_repetition_penalty": 1.35,
                            "gsv_media_type": "wav",
                        },
                    },
                    "GSVI TTS(API)": {
                        "id": "gsvi_tts",
                        "type": "gsvi_tts_api",
                        "provider": "gpt_sovits_inference",
                        "provider_type": "text_to_speech",
                        "api_base": "http://127.0.0.1:5000",
                        "character": "",
                        "emotion": "default",
                        "enable": False,
                        "timeout": 20,
                    },
                    "FishAudio TTS(API)": {
                        "id": "fishaudio_tts",
                        "provider": "fishaudio",
                        "type": "fishaudio_tts_api",
                        "provider_type": "text_to_speech",
                        "enable": False,
                        "api_key": "",
                        "api_base": "https://api.fish.audio/v1",
                        "fishaudio-tts-character": "可莉",
                        "fishaudio-tts-reference-id": "",
                        "timeout": "20",
                    },
                    "阿里云百炼 TTS(API)": {
                        "id": "dashscope_tts",
                        "provider": "dashscope",
                        "type": "dashscope_tts",
                        "provider_type": "text_to_speech",
                        "enable": False,
                        "api_key": "",
                        "model": "cosyvoice-v1",
                        "dashscope_tts_voice": "loongstella",
                        "timeout": "20",
                    },
                    "Azure TTS": {
                        "id": "azure_tts",
                        "type": "azure_tts",
                        "provider": "azure",
                        "provider_type": "text_to_speech",
                        "enable": True,
                        "azure_tts_voice": "zh-CN-YunxiaNeural",
                        "azure_tts_style": "cheerful",
                        "azure_tts_role": "Boy",
                        "azure_tts_rate": "1",
                        "azure_tts_volume": "100",
                        "azure_tts_subscription_key": "",
                        "azure_tts_region": "eastus",
                    },
                    "MiniMax TTS(API)": {
                        "id": "minimax_tts",
                        "type": "minimax_tts_api",
                        "provider": "minimax",
                        "provider_type": "text_to_speech",
                        "enable": False,
                        "api_key": "",
                        "api_base": "https://api.minimax.chat/v1/t2a_v2",
                        "minimax-group-id": "",
                        "model": "speech-02-turbo",
                        "minimax-langboost": "auto",
                        "minimax-voice-speed": 1.0,
                        "minimax-voice-vol": 1.0,
                        "minimax-voice-pitch": 0,
                        "minimax-is-timber-weight": False,
                        "minimax-voice-id": "female-shaonv",
                        "minimax-timber-weight": '[\n    {\n        "voice_id": "Chinese (Mandarin)_Warm_Girl",\n        "weight": 25\n    },\n    {\n        "voice_id": "Chinese (Mandarin)_BashfulGirl",\n        "weight": 50\n    }\n]',
                        "minimax-voice-emotion": "neutral",
                        "minimax-voice-latex": False,
                        "minimax-voice-english-normalization": False,
                        "timeout": 20,
                    },
                    "火山引擎_TTS(API)": {
                        "id": "volcengine_tts",
                        "type": "volcengine_tts",
                        "provider": "volcengine",
                        "provider_type": "text_to_speech",
                        "enable": False,
                        "api_key": "",
                        "appid": "",
                        "volcengine_cluster": "volcano_tts",
                        "volcengine_voice_type": "",
                        "volcengine_speed_ratio": 1.0,
                        "api_base": "https://openspeech.bytedance.com/api/v1/tts",
                        "timeout": 20,
                    },
                    "Gemini TTS": {
                        "id": "gemini_tts",
                        "type": "gemini_tts",
                        "provider": "google",
                        "provider_type": "text_to_speech",
                        "enable": False,
                        "gemini_tts_api_key": "",
                        "gemini_tts_api_base": "",
                        "gemini_tts_timeout": 20,
                        "gemini_tts_model": "gemini-2.5-flash-preview-tts",
                        "gemini_tts_prefix": "",
                        "gemini_tts_voice_name": "Leda",
                    },
                    "OpenAI Embedding": {
                        "id": "openai_embedding",
                        "type": "openai_embedding",
                        "provider": "openai",
                        "provider_type": "embedding",
                        "enable": True,
                        "embedding_api_key": "",
                        "embedding_api_base": "",
                        "embedding_model": "",
                        "embedding_dimensions": 1024,
                        "timeout": 20,
                    },
                    "Gemini Embedding": {
                        "id": "gemini_embedding",
                        "type": "gemini_embedding",
                        "provider": "google",
                        "provider_type": "embedding",
                        "enable": True,
                        "embedding_api_key": "",
                        "embedding_api_base": "",
                        "embedding_model": "gemini-embedding-exp-03-07",
                        "embedding_dimensions": 768,
                        "timeout": 20,
                    },
                    "vLLM Rerank": {
                        "id": "vllm_rerank",
                        "type": "vllm_rerank",
                        "provider": "vllm",
                        "provider_type": "rerank",
                        "enable": True,
                        "rerank_api_key": "",
                        "rerank_api_base": "http://127.0.0.1:8000",
                        "rerank_model": "BAAI/bge-reranker-base",
                        "timeout": 20,
                    },
                },
                "items": {
                    "rerank_api_base": {
                        "description": "重排序模型 API Base URL",
                        "type": "string",
                        "hint": "AstrBot 会在请求时在末尾加上 /v1/rerank。",
                    },
                    "rerank_api_key": {
                        "description": "API Key",
                        "type": "string",
                        "hint": "如果不需要 API Key, 请留空。",
                    },
                    "rerank_model": {
                        "description": "重排序模型名称",
                        "type": "string",
                    },
                    "modalities": {
                        "description": "模型能力",
                        "type": "list",
                        "items": {"type": "string"},
                        "options": ["text", "image", "tool_use"],
                        "labels": ["文本", "图像", "工具使用"],
                        "render_type": "checkbox",
                        "hint": "模型支持的模态。如所填写的模型不支持图像，请取消勾选图像。",
                    },
                    "provider": {
                        "type": "string",
                        "invisible": True,
                    },
                    "gpt_weights_path": {
                        "description": "GPT模型文件路径",
                        "type": "string",
                        "hint": "即“.ckpt”后缀的文件，请使用绝对路径，路径两端不要带双引号，不填则默认用GPT_SoVITS内置的SoVITS模型(建议直接在GPT_SoVITS中改默认模型)",
                    },
                    "sovits_weights_path": {
                        "description": "SoVITS模型文件路径",
                        "type": "string",
                        "hint": "即“.pth”后缀的文件，请使用绝对路径，路径两端不要带双引号，不填则默认用GPT_SoVITS内置的SoVITS模型(建议直接在GPT_SoVITS中改默认模型)",
                    },
                    "gsv_default_parms": {
                        "description": "GPT_SoVITS默认参数",
                        "hint": "参考音频文件路径、参考音频文本必填，其他参数根据个人爱好自行填写",
                        "type": "object",
                        "items": {
                            "gsv_ref_audio_path": {
                                "description": "参考音频文件路径",
                                "type": "string",
                                "hint": "必填！请使用绝对路径！路径两端不要带双引号！",
                            },
                            "gsv_prompt_text": {
                                "description": "参考音频文本",
                                "type": "string",
                                "hint": "必填！请填写参考音频讲述的文本",
                            },
                            "gsv_prompt_lang": {
                                "description": "参考音频文本语言",
                                "type": "string",
                                "hint": "请填写参考音频讲述的文本的语言，默认为中文",
                            },
                            "gsv_aux_ref_audio_paths": {
                                "description": "辅助参考音频文件路径",
                                "type": "string",
                                "hint": "辅助参考音频文件，可不填",
                            },
                            "gsv_text_lang": {
                                "description": "文本语言",
                                "type": "string",
                                "hint": "默认为中文",
                            },
                            "gsv_top_k": {
                                "description": "生成语音的多样性",
                                "type": "int",
                                "hint": "",
                            },
                            "gsv_top_p": {
                                "description": "核采样的阈值",
                                "type": "float",
                                "hint": "",
                            },
                            "gsv_temperature": {
                                "description": "生成语音的随机性",
                                "type": "float",
                                "hint": "",
                            },
                            "gsv_text_split_method": {
                                "description": "切分文本的方法",
                                "type": "string",
                                "hint": "可选值：  `cut0`：不切分    `cut1`：四句一切   `cut2`：50字一切    `cut3`：按中文句号切    `cut4`：按英文句号切    `cut5`：按标点符号切",
                                "options": [
                                    "cut0",
                                    "cut1",
                                    "cut2",
                                    "cut3",
                                    "cut4",
                                    "cut5",
                                ],
                            },
                            "gsv_batch_size": {
                                "description": "批处理大小",
                                "type": "int",
                                "hint": "",
                            },
                            "gsv_batch_threshold": {
                                "description": "批处理阈值",
                                "type": "float",
                                "hint": "",
                            },
                            "gsv_split_bucket": {
                                "description": "将文本分割成桶以便并行处理",
                                "type": "bool",
                                "hint": "",
                            },
                            "gsv_speed_factor": {
                                "description": "语音播放速度",
                                "type": "float",
                                "hint": "1为原始语速",
                            },
                            "gsv_fragment_interval": {
                                "description": "语音片段之间的间隔时间",
                                "type": "float",
                                "hint": "",
                            },
                            "gsv_streaming_mode": {
                                "description": "启用流模式",
                                "type": "bool",
                                "hint": "",
                            },
                            "gsv_seed": {
                                "description": "随机种子",
                                "type": "int",
                                "hint": "用于结果的可重复性",
                            },
                            "gsv_parallel_infer": {
                                "description": "并行执行推理",
                                "type": "bool",
                                "hint": "",
                            },
                            "gsv_repetition_penalty": {
                                "description": "重复惩罚因子",
                                "type": "float",
                                "hint": "",
                            },
                            "gsv_media_type": {
                                "description": "输出媒体的类型",
                                "type": "string",
                                "hint": "建议用wav",
                            },
                        },
                    },
                    "embedding_dimensions": {
                        "description": "嵌入维度",
                        "type": "int",
                        "hint": "嵌入向量的维度。根据模型不同，可能需要调整，请参考具体模型的文档。此配置项请务必填写正确，否则将导致向量数据库无法正常工作。",
                    },
                    "embedding_model": {
                        "description": "嵌入模型",
                        "type": "string",
                        "hint": "嵌入模型名称。",
                    },
                    "embedding_api_key": {
                        "description": "API Key",
                        "type": "string",
                    },
                    "embedding_api_base": {
                        "description": "API Base URL",
                        "type": "string",
                    },
                    "volcengine_cluster": {
                        "type": "string",
                        "description": "火山引擎集群",
                        "hint": "若使用语音复刻大模型，可选volcano_icl或volcano_icl_concurr，默认使用volcano_tts",
                    },
                    "volcengine_voice_type": {
                        "type": "string",
                        "description": "火山引擎音色",
                        "hint": "输入声音id(Voice_type)",
                    },
                    "volcengine_speed_ratio": {
                        "type": "float",
                        "description": "语速设置",
                        "hint": "语速设置，范围为 0.2 到 3.0,默认值为 1.0",
                    },
                    "volcengine_volume_ratio": {
                        "type": "float",
                        "description": "音量设置",
                        "hint": "音量设置，范围为 0.0 到 2.0,默认值为 1.0",
                    },
                    "azure_tts_voice": {
                        "type": "string",
                        "description": "音色设置",
                        "hint": "API 音色",
                    },
                    "azure_tts_style": {
                        "type": "string",
                        "description": "风格设置",
                        "hint": "声音特定的讲话风格。 可以表达快乐、同情和平静等情绪。",
                    },
                    "azure_tts_role": {
                        "type": "string",
                        "description": "模仿设置（可选）",
                        "hint": "讲话角色扮演。 声音可以模仿不同的年龄和性别，但声音名称不会更改。 例如，男性语音可以提高音调和改变语调来模拟女性语音，但语音名称不会更改。 如果角色缺失或不受声音的支持，则会忽略此属性。",
                        "options": [
                            "Boy",
                            "Girl",
                            "YoungAdultFemale",
                            "YoungAdultMale",
                            "OlderAdultFemale",
                            "OlderAdultMale",
                            "SeniorFemale",
                            "SeniorMale",
                            "禁用",
                        ],
                    },
                    "azure_tts_rate": {
                        "type": "string",
                        "description": "语速设置",
                        "hint": "指示文本的讲出速率。可在字词或句子层面应用语速。 速率变化应为原始音频的 0.5 到 2 倍。",
                    },
                    "azure_tts_volume": {
                        "type": "string",
                        "description": "语音音量设置",
                        "hint": "指示语音的音量级别。 可在句子层面应用音量的变化。以从 0.0 到 100.0（从最安静到最大声，例如 75）的数字表示。 默认值为 100.0。",
                    },
                    "azure_tts_region": {
                        "type": "string",
                        "description": "API 地区",
                        "hint": "Azure_TTS 处理数据所在区域，具体参考 https://learn.microsoft.com/zh-cn/azure/ai-services/speech-service/regions",
                        "options": [
                            "southafricanorth",
                            "eastasia",
                            "southeastasia",
                            "australiaeast",
                            "centralindia",
                            "japaneast",
                            "japanwest",
                            "koreacentral",
                            "canadacentral",
                            "northeurope",
                            "westeurope",
                            "francecentral",
                            "germanywestcentral",
                            "norwayeast",
                            "swedencentral",
                            "switzerlandnorth",
                            "switzerlandwest",
                            "uksouth",
                            "uaenorth",
                            "brazilsouth",
                            "qatarcentral",
                            "centralus",
                            "eastus",
                            "eastus2",
                            "northcentralus",
                            "southcentralus",
                            "westcentralus",
                            "westus",
                            "westus2",
                            "westus3",
                        ],
                    },
                    "azure_tts_subscription_key": {
                        "type": "string",
                        "description": "服务订阅密钥",
                        "hint": "Azure_TTS 服务的订阅密钥（注意不是令牌）",
                    },
                    "dashscope_tts_voice": {
                        "description": "语音合成模型",
                        "type": "string",
                        "hint": "阿里云百炼语音合成模型名称。具体可参考 https://help.aliyun.com/zh/model-studio/developer-reference/cosyvoice-python-api 等内容",
                    },
                    "gm_resp_image_modal": {
                        "description": "启用图片模态",
                        "type": "bool",
                        "hint": "启用后，将支持返回图片内容。需要模型支持，否则会报错。具体支持模型请查看 Google Gemini 官方网站。温馨提示，如果您需要生成图片，请关闭 `启用群员识别` 配置获得更好的效果。",
                    },
                    "gm_native_search": {
                        "description": "启用原生搜索功能",
                        "type": "bool",
                        "hint": "启用后所有函数工具将全部失效，免费次数限制请查阅官方文档",
                    },
                    "gm_native_coderunner": {
                        "description": "启用原生代码执行器",
                        "type": "bool",
                        "hint": "启用后所有函数工具将全部失效",
                    },
                    "gm_url_context": {
                        "description": "启用URL上下文功能",
                        "type": "bool",
                        "hint": "启用后所有函数工具将全部失效",
                    },
                    "gm_safety_settings": {
                        "description": "安全过滤器",
                        "type": "object",
                        "hint": "设置模型输入的内容安全过滤级别。过滤级别分类为NONE(不屏蔽)、HIGH(高风险时屏蔽)、MEDIUM_AND_ABOVE(中等风险及以上屏蔽)、LOW_AND_ABOVE(低风险及以上时屏蔽)，具体参见Gemini API文档。",
                        "items": {
                            "harassment": {
                                "description": "骚扰内容",
                                "type": "string",
                                "hint": "负面或有害评论",
                                "options": [
                                    "BLOCK_NONE",
                                    "BLOCK_ONLY_HIGH",
                                    "BLOCK_MEDIUM_AND_ABOVE",
                                    "BLOCK_LOW_AND_ABOVE",
                                ],
                            },
                            "hate_speech": {
                                "description": "仇恨言论",
                                "type": "string",
                                "hint": "粗鲁、无礼或亵渎性质内容",
                                "options": [
                                    "BLOCK_NONE",
                                    "BLOCK_ONLY_HIGH",
                                    "BLOCK_MEDIUM_AND_ABOVE",
                                    "BLOCK_LOW_AND_ABOVE",
                                ],
                            },
                            "sexually_explicit": {
                                "description": "露骨色情内容",
                                "type": "string",
                                "hint": "包含性行为或其他淫秽内容的引用",
                                "options": [
                                    "BLOCK_NONE",
                                    "BLOCK_ONLY_HIGH",
                                    "BLOCK_MEDIUM_AND_ABOVE",
                                    "BLOCK_LOW_AND_ABOVE",
                                ],
                            },
                            "dangerous_content": {
                                "description": "危险内容",
                                "type": "string",
                                "hint": "宣扬、助长或鼓励有害行为的信息",
                                "options": [
                                    "BLOCK_NONE",
                                    "BLOCK_ONLY_HIGH",
                                    "BLOCK_MEDIUM_AND_ABOVE",
                                    "BLOCK_LOW_AND_ABOVE",
                                ],
                            },
                        },
                    },
                    "gm_thinking_config": {
                        "description": "Gemini思考设置",
                        "type": "object",
                        "items": {
                            "budget": {
                                "description": "思考预算",
                                "type": "int",
                                "hint": "模型应该生成的思考Token的数量，设为0关闭思考。除gemini-2.5-flash外的模型会静默忽略此参数。",
                            },
                        },
                    },
                    "minimax-group-id": {
                        "type": "string",
                        "description": "用户组",
                        "hint": "于账户管理->基本信息中可见",
                    },
                    "minimax-langboost": {
                        "type": "string",
                        "description": "指定语言/方言",
                        "hint": "增强对指定的小语种和方言的识别能力，设置后可以提升在指定小语种/方言场景下的语音表现",
                        "options": [
                            "Chinese",
                            "Chinese,Yue",
                            "English",
                            "Arabic",
                            "Russian",
                            "Spanish",
                            "French",
                            "Portuguese",
                            "German",
                            "Turkish",
                            "Dutch",
                            "Ukrainian",
                            "Vietnamese",
                            "Indonesian",
                            "Japanese",
                            "Italian",
                            "Korean",
                            "Thai",
                            "Polish",
                            "Romanian",
                            "Greek",
                            "Czech",
                            "Finnish",
                            "Hindi",
                            "auto",
                        ],
                    },
                    "minimax-voice-speed": {
                        "type": "float",
                        "description": "语速",
                        "hint": "生成声音的语速, 取值[0.5, 2], 默认为1.0, 取值越大，语速越快",
                    },
                    "minimax-voice-vol": {
                        "type": "float",
                        "description": "音量",
                        "hint": "生成声音的音量, 取值(0, 10], 默认为1.0, 取值越大，音量越高",
                    },
                    "minimax-voice-pitch": {
                        "type": "int",
                        "description": "语调",
                        "hint": "生成声音的语调, 取值[-12, 12], 默认为0",
                    },
                    "minimax-is-timber-weight": {
                        "type": "bool",
                        "description": "启用混合音色",
                        "hint": "启用混合音色, 支持以自定义权重混合最多四种音色, 启用后自动忽略单一音色设置",
                    },
                    "minimax-timber-weight": {
                        "type": "string",
                        "description": "混合音色",
                        "editor_mode": True,
                        "hint": "混合音色及其权重, 最多支持四种音色, 权重为整数, 取值[1, 100]. 可在官网API语音调试台预览代码获得预设以及编写模板, 需要严格按照json字符串格式编写, 可以查看控制台判断是否解析成功. 具体结构可参照默认值以及官网代码预览.",
                    },
                    "minimax-voice-id": {
                        "type": "string",
                        "description": "单一音色",
                        "hint": "单一音色编号, 详见官网文档",
                    },
                    "minimax-voice-emotion": {
                        "type": "string",
                        "description": "情绪",
                        "hint": "控制合成语音的情绪",
                        "options": [
                            "happy",
                            "sad",
                            "angry",
                            "fearful",
                            "disgusted",
                            "surprised",
                            "neutral",
                        ],
                    },
                    "minimax-voice-latex": {
                        "type": "bool",
                        "description": "支持朗读latex公式",
                        "hint": "朗读latex公式, 但是需要确保输入文本按官网要求格式化",
                    },
                    "minimax-voice-english-normalization": {
                        "type": "bool",
                        "description": "支持英语文本规范化",
                        "hint": "可提升数字阅读场景的性能，但会略微增加延迟",
                    },
                    "rag_options": {
                        "description": "RAG 选项",
                        "type": "object",
                        "hint": "检索知识库设置, 非必填。仅 Agent 应用类型支持(智能体应用, 包括 RAG 应用)。阿里云百炼应用开启此功能后将无法多轮对话。",
                        "items": {
                            "pipeline_ids": {
                                "description": "知识库 ID 列表",
                                "type": "list",
                                "items": {"type": "string"},
                                "hint": "对指定知识库内所有文档进行检索, 前往 https://bailian.console.aliyun.com/ 数据应用->知识索引创建和获取 ID。",
                            },
                            "file_ids": {
                                "description": "非结构化文档 ID, 传入该参数将对指定非结构化文档进行检索。",
                                "type": "list",
                                "items": {"type": "string"},
                                "hint": "对指定非结构化文档进行检索。前往 https://bailian.console.aliyun.com/ 数据管理创建和获取 ID。",
                            },
                            "output_reference": {
                                "description": "是否输出知识库/文档的引用",
                                "type": "bool",
                                "hint": "在每次回答尾部加上引用源。默认为 False。",
                            },
                        },
                    },
                    "sensevoice_hint": {
                        "description": "部署SenseVoice",
                        "type": "string",
                        "hint": "启用前请 pip 安装 funasr、funasr_onnx、torchaudio、torch、modelscope、jieba 库（默认使用CPU，大约下载 1 GB），并且安装 ffmpeg。否则将无法正常转文字。",
                    },
                    "is_emotion": {
                        "description": "情绪识别",
                        "type": "bool",
                        "hint": "是否开启情绪识别。happy｜sad｜angry｜neutral｜fearful｜disgusted｜surprised｜unknown",
                    },
                    "stt_model": {
                        "description": "模型名称",
                        "type": "string",
                        "hint": "modelscope 上的模型名称。默认：iic/SenseVoiceSmall。",
                    },
                    "variables": {
                        "description": "工作流固定输入变量",
                        "type": "object",
                        "items": {},
                        "hint": "可选。工作流固定输入变量，将会作为工作流的输入。也可以在对话时使用 /set 指令动态设置变量。如果变量名冲突，优先使用动态设置的变量。",
                        "invisible": True,
                    },
                    "dashscope_app_type": {
                        "description": "应用类型",
                        "type": "string",
                        "hint": "百炼应用的应用类型。",
                        "options": [
                            "agent",
                            "agent-arrange",
                            "dialog-workflow",
                            "task-workflow",
                        ],
                    },
                    "timeout": {
                        "description": "超时时间",
                        "type": "int",
                        "hint": "超时时间，单位为秒。",
                    },
                    "openai-tts-voice": {
                        "description": "voice",
                        "type": "string",
                        "hint": "OpenAI TTS 的声音。OpenAI 默认支持：'alloy', 'echo', 'fable', 'onyx', 'nova', 'shimmer'",
                    },
                    "fishaudio-tts-character": {
                        "description": "character",
                        "type": "string",
                        "hint": "fishaudio TTS 的角色。默认为可莉。更多角色请访问：https://fish.audio/zh-CN/discovery",
                    },
                    "fishaudio-tts-reference-id": {
                        "description": "reference_id",
                        "type": "string",
                        "hint": "fishaudio TTS 的参考模型ID（可选）。如果填入此字段，将直接使用模型ID而不通过角色名称查询。例如：626bb6d3f3364c9cbc3aa6a67300a664。更多模型请访问：https://fish.audio/zh-CN/discovery，进入模型详情界面后可复制模型ID",
                    },
                    "whisper_hint": {
                        "description": "本地部署 Whisper 模型须知",
                        "type": "string",
                        "hint": "启用前请 pip 安装 openai-whisper 库（N卡用户大约下载 2GB，主要是 torch 和 cuda，CPU 用户大约下载 1 GB），并且安装 ffmpeg。否则将无法正常转文字。",
                    },
                    "id": {
                        "description": "ID",
                        "type": "string",
                        "hint": "模型提供商名字。",
                    },
                    "type": {
                        "description": "模型提供商种类",
                        "type": "string",
                        "invisible": True,
                    },
                    "provider_type": {
                        "description": "模型提供商能力种类",
                        "type": "string",
                        "invisible": True,
                    },
                    "enable": {
                        "description": "启用",
                        "type": "bool",
                        "hint": "是否启用。",
                    },
                    "key": {
                        "description": "API Key",
                        "type": "list",
                        "items": {"type": "string"},
                        "hint": "提供商 API Key。",
                    },
                    "api_base": {
                        "description": "API Base URL",
                        "type": "string",
                        "hint": "API Base URL 请在模型提供商处获得。如出现 404 报错，尝试在地址末尾加上 /v1",
                    },
                    "model_config": {
                        "description": "模型配置",
                        "type": "object",
                        "items": {
                            "model": {
                                "description": "模型名称",
                                "type": "string",
                                "hint": "模型名称，如 gpt-4o-mini, deepseek-chat。",
                            },
                            "max_tokens": {
                                "description": "模型最大输出长度（tokens）",
                                "type": "int",
                            },
                            "temperature": {"description": "温度", "type": "float"},
                            "top_p": {"description": "Top P值", "type": "float"},
                        },
                    },
                    "dify_api_key": {
                        "description": "API Key",
                        "type": "string",
                        "hint": "Dify API Key。此项必填。",
                    },
                    "dify_api_base": {
                        "description": "API Base URL",
                        "type": "string",
                        "hint": "Dify API Base URL。默认为 https://api.dify.ai/v1",
                    },
                    "dify_api_type": {
                        "description": "Dify 应用类型",
                        "type": "string",
                        "hint": "Dify API 类型。根据 Dify 官网，目前支持 chat, chatflow, agent, workflow 三种应用类型。",
                        "options": ["chat", "chatflow", "agent", "workflow"],
                    },
                    "dify_workflow_output_key": {
                        "description": "Dify Workflow 输出变量名",
                        "type": "string",
                        "hint": "Dify Workflow 输出变量名。当应用类型为 workflow 时才使用。默认为 astrbot_wf_output。",
                    },
                    "dify_query_input_key": {
                        "description": "Prompt 输入变量名",
                        "type": "string",
                        "hint": "发送的消息文本内容对应的输入变量名。默认为 astrbot_text_query。",
                        "obvious": True,
                    },
                },
            },
            "provider_settings": {
                "type": "object",
                "items": {
                    "enable": {
                        "type": "bool",
                    },
                    "default_provider_id": {
                        "type": "string",
                    },
                    "wake_prefix": {
                        "type": "string",
                    },
                    "web_search": {
                        "type": "bool",
                    },
                    "web_search_link": {
                        "type": "bool",
                    },
                    "display_reasoning_text": {
                        "type": "bool",
                    },
                    "identifier": {
                        "type": "bool",
                    },
                    "datetime_system_prompt": {
                        "type": "bool",
                    },
                    "default_personality": {
                        "type": "string",
                    },
                    "prompt_prefix": {
                        "type": "string",
                    },
                    "max_context_length": {
                        "type": "int",
                    },
                    "dequeue_context_length": {
                        "type": "int",
                    },
                    "streaming_response": {
                        "type": "bool",
                    },
                    "show_tool_use_status": {
                        "type": "bool",
                    },
                    "streaming_segmented": {
                        "type": "bool",
                    },
                    "max_agent_step": {
                        "description": "工具调用轮数上限",
                        "type": "int",
                    },
                },
            },
            "provider_stt_settings": {
                "type": "object",
                "items": {
                    "enable": {
                        "type": "bool",
                    },
                    "provider_id": {
                        "type": "string",
                    },
                },
            },
            "provider_tts_settings": {
                "type": "object",
                "items": {
                    "enable": {
                        "type": "bool",
                    },
                    "provider_id": {
                        "type": "string",
                    },
                    "dual_output": {
                        "type": "bool",
                    },
                    "use_file_service": {
                        "type": "bool",
                    },
                },
            },
            "provider_ltm_settings": {
                "type": "object",
                "items": {
                    "group_icl_enable": {
                        "type": "bool",
                    },
                    "group_message_max_cnt": {
                        "type": "int",
                    },
                    "image_caption": {
                        "type": "bool",
                    },
                    "image_caption_prompt": {
                        "type": "string",
                    },
                    "active_reply": {
                        "type": "object",
                        "items": {
                            "enable": {
                                "type": "bool",
                            },
                            "whitelist": {
                                "type": "list",
                                "items": {"type": "string"},
                            },
                            "method": {
                                "type": "string",
                                "options": ["possibility_reply"],
                            },
                            "possibility_reply": {
                                "type": "float",
                            },
                        },
                    },
                },
            },
        },
    },
    "misc_config_group": {
        "metadata": {
            "wake_prefix": {
                "type": "list",
                "items": {"type": "string"},
            },
            "t2i": {
                "type": "bool",
            },
            "t2i_word_threshold": {
                "type": "int",
            },
            "admins_id": {
                "type": "list",
                "items": {"type": "string"},
            },
            "http_proxy": {
                "type": "string",
            },
            "no_proxy": {
                "description": "直连地址列表",
                "type": "list",
                "items": {"type": "string"},
                "hint": "在此处添加不希望通过代理访问的地址，例如内部服务地址。回车添加，可添加多个，如未设置代理请忽略此配置",
            },
            "timezone": {
                "type": "string",
            },
            "callback_api_base": {
                "type": "string",
            },
            "log_level": {
                "type": "string",
                "options": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
            },
            "t2i_strategy": {
                "type": "string",
                "options": ["remote", "local"],
            },
            "t2i_endpoint": {
                "type": "string",
            },
            "t2i_use_file_service": {
                "type": "bool",
            },
            "pip_install_arg": {
                "type": "string",
            },
            "pypi_index_url": {
                "type": "string",
            },
            "default_kb_collection": {
                "type": "string",
            },
        },
    },
}


CONFIG_METADATA_3 = {
    "ai_group": {
        "name": "AI 配置",
        "metadata": {
            "ai": {
                "description": "模型",
                "type": "object",
                "items": {
                    "provider_settings.enable": {
                        "description": "启用大语言模型聊天",
                        "type": "bool",
                    },
                    "provider_settings.default_provider_id": {
                        "description": "默认聊天模型",
                        "type": "string",
                        "_special": "select_provider",
                        "hint": "留空时使用第一个模型。",
                    },
                    "provider_settings.default_image_caption_provider_id": {
                        "description": "默认图片转述模型",
                        "type": "string",
                        "_special": "select_provider",
                        "hint": "留空代表不使用。可用于不支持视觉模态的聊天模型。",
                    },
                    "provider_stt_settings.provider_id": {
                        "description": "语音转文本模型",
                        "type": "string",
                        "hint": "留空代表不使用。",
                        "_special": "select_provider_stt",
                    },
                    "provider_tts_settings.provider_id": {
                        "description": "文本转语音模型",
                        "type": "string",
                        "hint": "留空代表不使用。",
                        "_special": "select_provider_tts",
                    },
                    "provider_settings.image_caption_prompt": {
                        "description": "图片转述提示词",
                        "type": "text",
                    },
                },
            },
            "persona": {
                "description": "人格",
                "type": "object",
                "items": {
                    "provider_settings.default_personality": {
                        "description": "默认采用的人格",
                        "type": "string",
                        "_special": "select_persona",
                    },
                },
            },
            "knowledgebase": {
                "description": "知识库",
                "type": "object",
                "items": {
                    "default_kb_collection": {
                        "description": "默认使用的知识库",
                        "type": "string",
                        "_special": "select_knowledgebase",
                    },
                },
            },
            "websearch": {
                "description": "网页搜索",
                "type": "object",
                "items": {
                    "provider_settings.web_search": {
                        "description": "启用网页搜索",
                        "type": "bool",
                    },
                    "provider_settings.websearch_provider": {
                        "description": "网页搜索提供商",
                        "type": "string",
                        "options": ["default", "tavily"],
                    },
                    "provider_settings.websearch_tavily_key": {
                        "description": "Tavily API Key",
                        "type": "string",
                        "condition": {
                            "provider_settings.websearch_provider": "tavily",
                        },
                    },
                    "provider_settings.web_search_link": {
                        "description": "显示来源引用",
                        "type": "bool",
                    },
                },
            },
            "others": {
                "description": "其他配置",
                "type": "object",
                "items": {
                    "provider_settings.display_reasoning_text": {
                        "description": "显示思考内容",
                        "type": "bool",
                    },
                    "provider_settings.identifier": {
                        "description": "用户感知",
                        "type": "bool",
                    },
                    "provider_settings.datetime_system_prompt": {
                        "description": "现实世界时间感知",
                        "type": "bool",
                    },
                    "provider_settings.show_tool_use_status": {
                        "description": "输出函数调用状态",
                        "type": "bool",
                    },
                    "provider_settings.max_agent_step": {
                        "description": "工具调用轮数上限",
                        "type": "bool",
                    },
                    "provider_settings.streaming_response": {
                        "description": "流式回复",
                        "type": "bool",
                    },
                    "provider_settings.streaming_segmented": {
                        "description": "不支持流式回复的平台采取分段输出",
                        "type": "bool",
                    },
                    "provider_settings.max_context_length": {
                        "description": "最多携带对话轮数",
                        "type": "int",
                        "hint": "超出这个数量时丢弃最旧的部分，一轮聊天记为 1 条。-1 为不限制。",
                    },
                    "provider_settings.dequeue_context_length": {
                        "description": "丢弃对话轮数",
                        "type": "int",
                        "hint": "超出最多携带对话轮数时, 一次丢弃的聊天轮数。",
                    },
                    "provider_settings.wake_prefix": {
                        "description": "LLM 聊天额外唤醒前缀 ",
                        "type": "string",
                    },
                    "provider_settings.prompt_prefix": {
                        "description": "额外前缀提示词",
                        "type": "string",
                    },
                    "provider_settings.dual_output": {
                        "description": "开启 TTS 时同时输出语音和文字内容",
                        "type": "bool",
                    },
                },
            },
        },
    },
    "platform_group": {
        "name": "平台配置",
        "metadata": {
            "general": {
                "description": "基本",
                "type": "object",
                "items": {
                    "admins_id": {
                        "description": "管理员 ID",
                        "type": "list",
                        "items": {"type": "string"},
                    },
                    "platform_settings.unique_session": {
                        "description": "隔离会话",
                        "type": "bool",
                        "hint": "启用后，群成员的上下文独立。",
                    },
                    "wake_prefix": {
                        "description": "唤醒词",
                        "type": "list",
                        "items": {"type": "string"},
                    },
                    "platform_settings.friend_message_needs_wake_prefix": {
                        "description": "私聊消息需要唤醒词",
                        "type": "bool",
                    },
                    "platform_settings.reply_prefix": {
                        "description": "回复时的文本前缀",
                        "type": "string",
                    },
                    "platform_settings.reply_with_mention": {
                        "description": "回复时 @ 发送人",
                        "type": "bool",
                    },
                    "platform_settings.reply_with_quote": {
                        "description": "回复时引用发送人消息",
                        "type": "bool",
                    },
                    "platform_settings.forward_threshold": {
                        "description": "转发消息的字数阈值",
                        "type": "int",
                    },
                    "platform_settings.empty_mention_waiting": {
                        "description": "只 @ 机器人是否触发等待",
                        "type": "bool",
                    },
                },
            },
            "whitelist": {
                "description": "白名单",
                "type": "object",
                "items": {
                    "platform_settings.enable_id_white_list": {
                        "description": "启用白名单",
                        "type": "bool",
                        "hint": "启用后，只有在白名单内的会话会被响应。",
                    },
                    "platform_settings.id_whitelist": {
                        "description": "白名单 ID 列表",
                        "type": "list",
                        "items": {"type": "string"},
                        "hint": "使用 /sid 获取 ID。",
                    },
                    "platform_settings.id_whitelist_log": {
                        "description": "输出日志",
                        "type": "bool",
                        "hint": "启用后，当一条消息没通过白名单时，会输出 INFO 级别的日志。",
                    },
                    "platform_settings.wl_ignore_admin_on_group": {
                        "description": "管理员群组消息无视 ID 白名单",
                        "type": "bool",
                    },
                    "platform_settings.wl_ignore_admin_on_friend": {
                        "description": "管理员私聊消息无视 ID 白名单",
                        "type": "bool",
                    },
                },
            },
            "rate_limit": {
                "description": "速率限制",
                "type": "object",
                "items": {
                    "platform_settings.rate_limit.time": {
                        "description": "消息速率限制时间(秒)",
                        "type": "int",
                    },
                    "platform_settings.rate_limit.count": {
                        "description": "消息速率限制计数",
                        "type": "int",
                    },
                    "platform_settings.rate_limit.strategy": {
                        "description": "速率限制策略",
                        "type": "string",
                        "options": ["stall", "discard"],
                    },
                },
            },
            "content_safety": {
                "description": "内容安全",
                "type": "object",
                "items": {
                    "platform_settings.content_safety.also_use_in_response": {
                        "description": "同时检查模型的响应内容",
                        "type": "bool",
                    },
                    "platform_settings.content_safety.baidu_aip.enable": {
                        "description": "使用百度内容安全审核",
                        "type": "bool",
                        "hint": "您需要手动安装 baidu-aip 库。",
                    },
                    "platform_settings.content_safety.baidu_aip.app_id": {
                        "description": "App ID",
                        "type": "string",
                        "condition": {
                            "platform_settings.content_safety.baidu_aip.enable": True,
                        },
                    },
                    "platform_settings.content_safety.baidu_aip.api_key": {
                        "description": "API Key",
                        "type": "string",
                        "condition": {
                            "platform_settings.content_safety.baidu_aip.enable": True,
                        },
                    },
                    "platform_settings.content_safety.baidu_aip.secret_key": {
                        "description": "Secret Key",
                        "type": "string",
                        "condition": {
                            "platform_settings.content_safety.baidu_aip.enable": True,
                        },
                    },
                    "platform_settings.content_safety.internal_keywords.enable": {
                        "description": "关键词检查",
                        "type": "bool",
                    },
                    "platform_settings.content_safety.internal_keywords.extra_keywords": {
                        "description": "额外关键词",
                        "type": "list",
                        "items": {"type": "string"},
                        "hint": "额外的屏蔽关键词列表，支持正则表达式。",
                    },
                },
            },
            "t2i": {
                "description": "文本转图像",
                "type": "object",
                "items": {
                    "t2i": {
                        "description": "文本转图像输出",
                        "type": "bool",
                    },
                    "t2i_word_threshold": {
                        "description": "文本转图像字数阈值",
                        "type": "int",
                    },
                },
            },
            "others": {
                "description": "其他配置",
                "type": "object",
                "items": {
                    "platform_settings.ignore_bot_self_message": {
                        "description": "是否忽略机器人自身的消息",
                        "type": "bool",
                    },
                    "platform_settings.ignore_at_all": {
                        "description": "是否忽略 @ 全体成员事件",
                        "type": "bool",
                    },
                    "platform_settings.no_permission_reply": {
                        "description": "用户权限不足时是否回复",
                        "type": "bool",
                    },
                },
            },
        },
    },
    "plugin_group": {
        "name": "插件配置",
        "metadata": {
            "plugin": {
                "description": "插件",
                "type": "object",
                "items": {
                    "plugin_set": {
                        "description": "可用插件",
                        "type": "bool",
                        "hint": "默认启用全部未被禁用的插件。若插件在插件页面被禁用，则此处的选择不会生效。",
                        "_special": "select_plugin_set",
                    },
                },
            },
        },
    },
    "ext_group": {
        "name": "扩展功能",
        "metadata": {
            "segmented_reply": {
                "description": "分段回复",
                "type": "object",
                "items": {
                    "platform_settings.segmented_reply.enable": {
                        "description": "启用分段回复",
                        "type": "bool",
                    },
                    "platform_settings.segmented_reply.only_llm_result": {
                        "description": "仅对 LLM 结果分段",
                        "type": "bool",
                    },
                    "platform_settings.segmented_reply.interval_method": {
                        "description": "间隔方法",
                        "type": "string",
                        "options": ["random", "log"],
                    },
                    "platform_settings.segmented_reply.interval": {
                        "description": "随机间隔时间",
                        "type": "string",
                        "hint": "格式：最小值,最大值（如：1.5,3.5）",
                        "condition": {
                            "platform_settings.segmented_reply.interval_method": "random",
                        },
                    },
                    "platform_settings.segmented_reply.log_base": {
                        "description": "对数底数",
                        "type": "float",
                        "hint": "对数间隔的底数，默认为 2.0。取值范围为 1.0-10.0。",
                        "condition": {
                            "platform_settings.segmented_reply.interval_method": "log",
                        },
                    },
                    "platform_settings.segmented_reply.words_count_threshold": {
                        "description": "分段回复字数阈值",
                        "type": "int",
                    },
                    "platform_settings.segmented_reply.regex": {
                        "description": "分段正则表达式",
                        "type": "string",
                    },
                    "platform_settings.segmented_reply.content_cleanup_rule": {
                        "description": "内容过滤正则表达式",
                        "type": "string",
                        "hint": "移除分段后内容中的指定内容。如填写 `[。？！]` 将移除所有的句号、问号、感叹号。",
                    },
                },
            },
            "ltm": {
                "description": "群聊上下文感知（原聊天记忆增强）",
                "type": "object",
                "items": {
                    "provider_ltm_settings.group_icl_enable": {
                        "description": "启用群聊上下文感知",
                        "type": "bool",
                    },
                    "provider_ltm_settings.group_message_max_cnt": {
                        "description": "最大消息数量",
                        "type": "int",
                    },
                    "provider_ltm_settings.image_caption": {
                        "description": "自动理解图片",
                        "type": "bool",
                        "hint": "需要设置默认图片转述模型。",
                    },
                    "provider_ltm_settings.active_reply.enable": {
                        "description": "主动回复",
                        "type": "bool",
                    },
                    "provider_ltm_settings.active_reply.method": {
                        "description": "主动回复方法",
                        "type": "string",
                        "options": ["possibility_reply"],
                        "condition": {
                            "provider_ltm_settings.active_reply.enable": True,
                        },
                    },
                    "provider_ltm_settings.active_reply.possibility_reply": {
                        "description": "回复概率",
                        "type": "float",
                        "hint": "0.0-1.0 之间的数值",
                        "condition": {
                            "provider_ltm_settings.active_reply.enable": True,
                        },
                    },
                    "provider_ltm_settings.active_reply.whitelist": {
                        "description": "主动回复白名单",
                        "type": "list",
                        "items": {"type": "string"},
                        "hint": "为空时不启用白名单过滤。使用 /sid 获取 ID。",
                        "condition": {
                            "provider_ltm_settings.active_reply.enable": True,
                        },
                    },
                },
            },
        },
    },
}

CONFIG_METADATA_3_SYSTEM = {
    "system_group": {
        "name": "系统配置",
        "metadata": {
            "system": {
                "description": "系统配置",
                "type": "object",
                "items": {
                    "t2i_strategy": {
                        "description": "文本转图像策略",
                        "type": "string",
                        "hint": "文本转图像策略。`remote` 为使用远程基于 HTML 的渲染服务，`local` 为使用 PIL 本地渲染。当使用 local 时，将 ttf 字体命名为 'font.ttf' 放在 data/ 目录下可自定义字体。",
                        "options": ["remote", "local"],
                    },
                    "t2i_endpoint": {
                        "description": "文本转图像服务 API 地址",
                        "type": "string",
                        "hint": "为空时使用 AstrBot API 服务",
                        "condition": {
                            "t2i_strategy": "remote",
                        },
                    },
                    "t2i_template": {
                        "description": "文本转图像自定义模版",
                        "type": "bool",
                        "hint": "启用后可自定义 HTML 模板用于文转图渲染。",
                        "condition": {
                            "t2i_strategy": "remote",
                        },
                        "_special": "t2i_template"
                    },
                    "log_level": {
                        "description": "控制台日志级别",
                        "type": "string",
                        "hint": "控制台输出日志的级别。",
                        "options": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                    },
                    "pip_install_arg": {
                        "description": "pip 安装额外参数",
                        "type": "string",
                        "hint": "安装插件依赖时，会使用 Python 的 pip 工具。这里可以填写额外的参数，如 `--break-system-package` 等。",
                    },
                    "pypi_index_url": {
                        "description": "PyPI 软件仓库地址",
                        "type": "string",
                        "hint": "安装 Python 依赖时请求的 PyPI 软件仓库地址。默认为 https://mirrors.aliyun.com/pypi/simple/",
                    },
                    "callback_api_base": {
                        "description": "对外可达的回调接口地址",
                        "type": "string",
                        "hint": "外部服务可能会通过 AstrBot 生成的回调链接（如文件下载链接）访问 AstrBot 后端。由于 AstrBot 无法自动判断部署环境中对外可达的主机地址（host），因此需要通过此配置项显式指定 “外部服务如何访问 AstrBot” 的地址。如 http://localhost:6185，https://example.com 等。",
                    },
                    "timezone": {
                        "description": "时区",
                        "type": "string",
                        "hint": "时区设置。请填写 IANA 时区名称, 如 Asia/Shanghai, 为空时使用系统默认时区。所有时区请查看: https://data.iana.org/time-zones/tzdb-2021a/zone1970.tab",
                    },
                    "http_proxy": {
                        "description": "HTTP 代理",
                        "type": "string",
                        "hint": "启用后，会以添加环境变量的方式设置代理。格式为 `http://ip:port`",
                    },
                },
            }
        },
    }
}


DEFAULT_VALUE_MAP = {
    "int": 0,
    "float": 0.0,
    "bool": False,
    "string": "",
    "text": "",
    "list": [],
    "object": {},
}
