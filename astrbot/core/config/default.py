"""如需修改配置，请在 `data/cmd_config.json` 中修改或者在管理面板中可视化修改。"""

import os
from typing import Any, TypedDict

from astrbot.core.utils.astrbot_path import get_astrbot_data_path

VERSION = "4.18.2"
DB_PATH = os.path.join(get_astrbot_data_path(), "data_v4.db")

WEBHOOK_SUPPORTED_PLATFORMS = [
    "qq_official_webhook",
    "weixin_official_account",
    "wecom",
    "wecom_ai_bot",
    "slack",
    "lark",
    "line",
]

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
            "split_mode": "regex",  # regex 或 words
            "regex": ".*?[。？！~…]+|.+$",
            "split_words": [
                "。",
                "？",
                "！",
                "~",
                "…",
            ],  # 当 split_mode 为 words 时使用
            "content_cleanup_rule": "",
        },
        "no_permission_reply": True,
        "empty_mention_waiting": True,
        "empty_mention_waiting_need_reply": True,
        "friend_message_needs_wake_prefix": False,
        "ignore_bot_self_message": False,
        "ignore_at_all": False,
    },
    "provider_sources": [],  # provider sources
    "provider": [],  # models from provider_sources
    "provider_settings": {
        "enable": True,
        "default_provider_id": "",
        "fallback_chat_models": [],
        "default_image_caption_provider_id": "",
        "image_caption_prompt": "Please describe the image using Chinese.",
        "provider_pool": ["*"],  # "*" 表示使用所有可用的提供者
        "wake_prefix": "",
        "web_search": False,
        "websearch_provider": "default",
        "websearch_tavily_key": [],
        "websearch_bocha_key": [],
        "websearch_baidu_app_builder_key": "",
        "web_search_link": False,
        "display_reasoning_text": False,
        "identifier": False,
        "group_name_display": False,
        "datetime_system_prompt": True,
        "default_personality": "default",
        "persona_pool": ["*"],
        "prompt_prefix": "{{prompt}}",
        "context_limit_reached_strategy": "truncate_by_turns",  # or llm_compress
        "llm_compress_instruction": (
            "Based on our full conversation history, produce a concise summary of key takeaways and/or project progress.\n"
            "1. Systematically cover all core topics discussed and the final conclusion/outcome for each; clearly highlight the latest primary focus.\n"
            "2. If any tools were used, summarize tool usage (total call count) and extract the most valuable insights from tool outputs.\n"
            "3. If there was an initial user goal, state it first and describe the current progress/status.\n"
            "4. Write the summary in the user's language.\n"
        ),
        "llm_compress_keep_recent": 6,
        "llm_compress_provider_id": "",
        "max_context_length": -1,
        "dequeue_context_length": 1,
        "streaming_response": False,
        "show_tool_use_status": False,
        "show_tool_call_result": False,
        "sanitize_context_by_modalities": False,
        "max_quoted_fallback_images": 20,
        "quoted_message_parser": {
            "max_component_chain_depth": 4,
            "max_forward_node_depth": 6,
            "max_forward_fetch": 32,
            "warn_on_action_failure": False,
        },
        "agent_runner_type": "local",
        "dify_agent_runner_provider_id": "",
        "coze_agent_runner_provider_id": "",
        "dashscope_agent_runner_provider_id": "",
        "unsupported_streaming_strategy": "realtime_segmenting",
        "reachability_check": False,
        "max_agent_step": 30,
        "tool_call_timeout": 60,
        "tool_schema_mode": "full",
        "llm_safety_mode": True,
        "safety_mode_strategy": "system_prompt",  # TODO: llm judge
        "file_extract": {
            "enable": False,
            "provider": "moonshotai",
            "moonshotai_api_key": "",
        },
        "proactive_capability": {
            "add_cron_tools": True,
        },
        "computer_use_runtime": "local",
        "computer_use_require_admin": True,
        "sandbox": {
            "booter": "shipyard",
            "shipyard_endpoint": "",
            "shipyard_access_token": "",
            "shipyard_ttl": 3600,
            "shipyard_max_sessions": 10,
        },
    },
    # SubAgent orchestrator mode:
    # - main_enable = False: disabled; main LLM mounts tools normally (persona selection).
    # - main_enable = True: enabled; main LLM keeps its own tools and includes handoff
    #   tools (transfer_to_*). remove_main_duplicate_tools can remove tools that are
    #   duplicated on subagents from the main LLM toolset.
    "subagent_orchestrator": {
        "main_enable": False,
        "remove_main_duplicate_tools": False,
        "router_system_prompt": (
            "You are a task router. Your job is to chat naturally, recognize user intent, "
            "and delegate work to the most suitable subagent using transfer_to_* tools. "
            "Do not try to use domain tools yourself. If no subagent fits, respond directly."
        ),
        "agents": [],
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
        "trigger_probability": 1.0,
    },
    "provider_ltm_settings": {
        "group_icl_enable": False,
        "group_message_max_cnt": 300,
        "image_caption": False,
        "image_caption_provider_id": "",
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
    "no_proxy": ["localhost", "127.0.0.1", "::1", "10.*", "192.168.*"],
    "dashboard": {
        "enable": True,
        "username": "astrbot",
        "password": "77b90590a8945a7d36c963981a307dc9",
        "jwt_secret": "",
        "host": "0.0.0.0",
        "port": 6185,
        "disable_access_log": True,
        "ssl": {
            "enable": False,
            "cert_file": "",
            "key_file": "",
            "ca_certs": "",
        },
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
    "log_file_enable": False,
    "log_file_path": "logs/astrbot.log",
    "log_file_max_mb": 20,
    "temp_dir_max_size": 1024,
    "trace_enable": False,
    "trace_log_enable": False,
    "trace_log_path": "logs/astrbot.trace.log",
    "trace_log_max_mb": 20,
    "pip_install_arg": "",
    "pypi_index_url": "https://mirrors.aliyun.com/pypi/simple/",
    "persona": [],  # deprecated
    "timezone": "Asia/Shanghai",
    "callback_api_base": "",
    "default_kb_collection": "",  # 默认知识库名称, 已经过时
    "plugin_set": ["*"],  # "*" 表示使用所有可用的插件, 空列表表示不使用任何插件
    "kb_names": [],  # 默认知识库名称列表
    "kb_fusion_top_k": 20,  # 知识库检索融合阶段返回结果数量
    "kb_final_top_k": 5,  # 知识库检索最终返回结果数量
    "kb_agentic_mode": False,
    "disable_builtin_commands": False,
}


class ChatProviderTemplate(TypedDict):
    id: str
    provider_source_id: str
    model: str
    modalities: list
    custom_extra_body: dict[str, Any]
    max_context_tokens: int


CHAT_PROVIDER_TEMPLATE = {
    "id": "",
    "provide_source_id": "",
    "model": "",
    "modalities": [],
    "custom_extra_body": {},
    "max_context_tokens": 0,
}

"""
AstrBot v3 时代的配置元数据，目前仅承担以下功能：

1. 保存配置时，配置项的类型验证
2. WebUI 展示提供商和平台适配器模版

WebUI 的配置文件在 `CONFIG_METADATA_3` 中。

未来将会逐步淘汰此配置元数据。
"""
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
                        "is_sandbox": False,
                        "unified_webhook_mode": True,
                        "webhook_uuid": "",
                        "callback_server_host": "0.0.0.0",
                        "port": 6196,
                    },
                    "OneBot v11": {
                        "id": "default",
                        "type": "aiocqhttp",
                        "enable": False,
                        "ws_reverse_host": "0.0.0.0",
                        "ws_reverse_port": 6199,
                        "ws_reverse_token": "",
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
                        "unified_webhook_mode": True,
                        "webhook_uuid": "",
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
                        "unified_webhook_mode": True,
                        "webhook_uuid": "",
                        "callback_server_host": "0.0.0.0",
                        "port": 6195,
                    },
                    "企业微信智能机器人": {
                        "id": "wecom_ai_bot",
                        "type": "wecom_ai_bot",
                        "enable": True,
                        "wecomaibot_init_respond_text": "",
                        "wecomaibot_friend_message_welcome_text": "",
                        "wecom_ai_bot_name": "",
                        "msg_push_webhook_url": "",
                        "only_use_webhook_url_to_send": False,
                        "token": "",
                        "encoding_aes_key": "",
                        "unified_webhook_mode": True,
                        "webhook_uuid": "",
                        "callback_server_host": "0.0.0.0",
                        "port": 6198,
                    },
                    "飞书(Lark)": {
                        "id": "lark",
                        "type": "lark",
                        "enable": False,
                        "lark_bot_name": "",
                        "app_id": "",
                        "app_secret": "",
                        "domain": "https://open.feishu.cn",
                        "lark_connection_mode": "socket",  # webhook, socket
                        "webhook_uuid": "",
                        "lark_encrypt_key": "",
                        "lark_verification_token": "",
                    },
                    "钉钉(DingTalk)": {
                        "id": "dingtalk",
                        "type": "dingtalk",
                        "enable": False,
                        "client_id": "",
                        "client_secret": "",
                        "card_template_id": "",
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
                    "Misskey": {
                        "id": "misskey",
                        "type": "misskey",
                        "enable": False,
                        "misskey_instance_url": "https://misskey.example",
                        "misskey_token": "",
                        "misskey_default_visibility": "public",
                        "misskey_local_only": False,
                        "misskey_enable_chat": True,
                        # download / security options
                        "misskey_allow_insecure_downloads": False,
                        "misskey_download_timeout": 15,
                        "misskey_download_chunk_size": 65536,
                        "misskey_max_download_bytes": None,
                        "misskey_enable_file_upload": True,
                        "misskey_upload_concurrency": 3,
                        "misskey_upload_folder": "",
                    },
                    "Slack": {
                        "id": "slack",
                        "type": "slack",
                        "enable": False,
                        "bot_token": "",
                        "app_token": "",
                        "signing_secret": "",
                        "slack_connection_mode": "socket",  # webhook, socket
                        "unified_webhook_mode": True,
                        "webhook_uuid": "",
                        "slack_webhook_host": "0.0.0.0",
                        "slack_webhook_port": 6197,
                        "slack_webhook_path": "/astrbot-slack-webhook/callback",
                    },
                    # LINE's config is located in line_adapter.py
                    "Satori": {
                        "id": "satori",
                        "type": "satori",
                        "enable": False,
                        "satori_api_base_url": "http://localhost:5140/satori/v1",
                        "satori_endpoint": "ws://localhost:5140/satori/v1/events",
                        "satori_token": "",
                        "satori_auto_reconnect": True,
                        "satori_heartbeat_interval": 10,
                        "satori_reconnect_delay": 5,
                    },
                    # "WebChat": {
                    #     "id": "webchat",
                    #     "type": "webchat",
                    #     "enable": False,
                    #     "webchat_link_path": "",
                    #     "webchat_present_type": "fullscreen",
                    # },
                },
                "items": {
                    # "webchat_link_path": {
                    #     "description": "链接路径",
                    #     "_special": "webchat_link_path",
                    #     "type": "string",
                    # },
                    # "webchat_present_type": {
                    #     "_special": "webchat_present_type",
                    #     "description": "展现形式",
                    #     "type": "string",
                    #     "options": ["fullscreen", "embedded"],
                    # },
                    "lark_connection_mode": {
                        "description": "订阅方式",
                        "type": "string",
                        "options": ["socket", "webhook"],
                        "labels": ["长连接模式", "推送至服务器模式"],
                    },
                    "lark_encrypt_key": {
                        "description": "Encrypt Key",
                        "type": "string",
                        "hint": "用于解密飞书回调数据的加密密钥",
                        "condition": {
                            "lark_connection_mode": "webhook",
                        },
                    },
                    "lark_verification_token": {
                        "description": "Verification Token",
                        "type": "string",
                        "hint": "用于验证飞书回调请求的令牌",
                        "condition": {
                            "lark_connection_mode": "webhook",
                        },
                    },
                    "is_sandbox": {
                        "description": "沙箱模式",
                        "type": "bool",
                    },
                    "satori_api_base_url": {
                        "description": "Satori API 终结点",
                        "type": "string",
                        "hint": "Satori API 的基础地址。",
                    },
                    "satori_endpoint": {
                        "description": "Satori WebSocket 终结点",
                        "type": "string",
                        "hint": "Satori 事件的 WebSocket 端点。",
                    },
                    "satori_token": {
                        "description": "Satori 令牌",
                        "type": "string",
                        "hint": "用于 Satori API 身份验证的令牌。",
                    },
                    "satori_auto_reconnect": {
                        "description": "启用自动重连",
                        "type": "bool",
                        "hint": "断开连接时是否自动重新连接 WebSocket。",
                    },
                    "satori_heartbeat_interval": {
                        "description": "Satori 心跳间隔",
                        "type": "int",
                        "hint": "发送心跳消息的间隔（秒）。",
                    },
                    "satori_reconnect_delay": {
                        "description": "Satori 重连延迟",
                        "type": "int",
                        "hint": "尝试重新连接前的延迟时间（秒）。",
                    },
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
                        "condition": {
                            "slack_connection_mode": "webhook",
                            "unified_webhook_mode": False,
                        },
                    },
                    "slack_webhook_port": {
                        "description": "Slack Webhook Port",
                        "type": "int",
                        "hint": "Only valid when Slack connection mode is `webhook`.",
                        "condition": {
                            "slack_connection_mode": "webhook",
                            "unified_webhook_mode": False,
                        },
                    },
                    "slack_webhook_path": {
                        "description": "Slack Webhook Path",
                        "type": "string",
                        "hint": "Only valid when Slack connection mode is `webhook`.",
                        "condition": {
                            "slack_connection_mode": "webhook",
                            "unified_webhook_mode": False,
                        },
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
                    "misskey_instance_url": {
                        "description": "Misskey 实例 URL",
                        "type": "string",
                        "hint": "例如 https://misskey.example，填写 Bot 账号所在的 Misskey 实例地址",
                    },
                    "misskey_token": {
                        "description": "Misskey Access Token",
                        "type": "string",
                        "hint": "连接服务设置生成的 API 鉴权访问令牌（Access token）",
                    },
                    "misskey_default_visibility": {
                        "description": "默认帖子可见性",
                        "type": "string",
                        "options": ["public", "home", "followers"],
                        "hint": "机器人发帖时的默认可见性设置。public：公开，home：主页时间线，followers：仅关注者。",
                    },
                    "misskey_local_only": {
                        "description": "仅限本站（不参与联合）",
                        "type": "bool",
                        "hint": "启用后，机器人发出的帖子将仅在本实例可见，不会联合到其他实例",
                    },
                    "misskey_enable_chat": {
                        "description": "启用聊天消息响应",
                        "type": "bool",
                        "hint": "启用后，机器人将会监听和响应私信聊天消息",
                    },
                    "misskey_enable_file_upload": {
                        "description": "启用文件上传到 Misskey",
                        "type": "bool",
                        "hint": "启用后，适配器会尝试将消息链中的文件上传到 Misskey。URL 文件会先尝试服务器端上传，异步上传失败时会回退到下载后本地上传。",
                    },
                    "misskey_allow_insecure_downloads": {
                        "description": "允许不安全下载（禁用 SSL 验证）",
                        "type": "bool",
                        "hint": "当远端服务器存在证书问题导致无法正常下载时，自动禁用 SSL 验证作为回退方案。适用于某些图床的证书配置问题。启用有安全风险，仅在必要时使用。",
                    },
                    "misskey_download_timeout": {
                        "description": "远端下载超时时间（秒）",
                        "type": "int",
                        "hint": "下载远程文件时的超时时间（秒），用于异步上传回退到本地上传的场景。",
                    },
                    "misskey_download_chunk_size": {
                        "description": "流式下载分块大小（字节）",
                        "type": "int",
                        "hint": "流式下载和计算 MD5 时使用的每次读取字节数，过小会增加开销，过大会占用内存。",
                    },
                    "misskey_max_download_bytes": {
                        "description": "最大允许下载字节数（超出则中止）",
                        "type": "int",
                        "hint": "如果希望限制下载文件的最大大小以防止 OOM，请填写最大字节数；留空或 null 表示不限制。",
                    },
                    "misskey_upload_concurrency": {
                        "description": "并发上传限制",
                        "type": "int",
                        "hint": "同时进行的文件上传任务上限（整数，默认 3）。",
                    },
                    "misskey_upload_folder": {
                        "description": "上传到网盘的目标文件夹 ID",
                        "type": "string",
                        "hint": "可选：填写 Misskey 网盘中目标文件夹的 ID，上传的文件将放置到该文件夹内。留空则使用账号网盘根目录。",
                    },
                    "card_template_id": {
                        "description": "卡片模板 ID",
                        "type": "string",
                        "hint": "可选。钉钉互动卡片模板 ID。启用后将使用互动卡片进行流式回复。",
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
                        "description": "反向 Websocket 主机",
                        "type": "string",
                        "hint": "AstrBot 将作为服务器端。",
                    },
                    "ws_reverse_port": {
                        "description": "反向 Websocket 端口",
                        "type": "int",
                    },
                    "ws_reverse_token": {
                        "description": "反向 Websocket Token",
                        "type": "string",
                        "hint": "反向 Websocket Token。未设置则不启用 Token 验证。",
                    },
                    "wecom_ai_bot_name": {
                        "description": "企业微信智能机器人的名字",
                        "type": "string",
                        "hint": "请务必填写正确，否则无法使用一些指令。",
                    },
                    "wecomaibot_init_respond_text": {
                        "description": "企业微信智能机器人初始响应文本",
                        "type": "string",
                        "hint": "当机器人收到消息时，首先回复的文本内容。留空则不设置。",
                    },
                    "wecomaibot_friend_message_welcome_text": {
                        "description": "企业微信智能机器人私聊欢迎语",
                        "type": "string",
                        "hint": "当用户当天进入智能机器人单聊会话，回复欢迎语，留空则不回复。",
                    },
                    "msg_push_webhook_url": {
                        "description": "企业微信消息推送 Webhook URL",
                        "type": "string",
                        "hint": "用于 send_by_session 主动消息推送。格式示例: https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx",
                    },
                    "only_use_webhook_url_to_send": {
                        "description": "仅使用 Webhook 发送消息",
                        "type": "bool",
                        "hint": "启用后，企业微信智能机器人的所有回复都改为通过消息推送 Webhook 发送。消息推送 Webhook 支持更多的消息类型（如图片、文件等）。",
                    },
                    "lark_bot_name": {
                        "description": "飞书机器人的名字",
                        "type": "string",
                        "hint": "请务必填写正确，否则 @ 机器人将无法唤醒，只能通过前缀唤醒。",
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
                    "port": {
                        "description": "回调服务器端口",
                        "type": "int",
                        "hint": "回调服务器端口。留空则不启用回调服务器。",
                        "condition": {
                            "unified_webhook_mode": False,
                        },
                    },
                    "callback_server_host": {
                        "description": "回调服务器主机",
                        "type": "string",
                        "hint": "回调服务器主机。留空则不启用回调服务器。",
                        "condition": {
                            "unified_webhook_mode": False,
                        },
                    },
                    "unified_webhook_mode": {
                        "description": "统一 Webhook 模式",
                        "type": "bool",
                        "hint": "启用后，将使用 AstrBot 统一 Webhook 入口，无需单独开启端口。回调地址为 /api/platform/webhook/{webhook_uuid}。",
                    },
                    "webhook_uuid": {
                        "invisible": True,
                        "description": "Webhook UUID",
                        "type": "string",
                        "hint": "统一 Webhook 模式下的唯一标识符，创建平台时自动生成。",
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
                            },
                            "interval": {
                                "type": "string",
                            },
                            "log_base": {
                                "type": "float",
                            },
                            "words_count_threshold": {
                                "type": "int",
                            },
                            "regex": {
                                "type": "string",
                            },
                            "content_cleanup_rule": {
                                "type": "string",
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
                # provider sources templates
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
                        "proxy": "",
                        "custom_headers": {},
                    },
                    "Google Gemini": {
                        "id": "google_gemini",
                        "provider": "google",
                        "type": "googlegenai_chat_completion",
                        "provider_type": "chat_completion",
                        "enable": True,
                        "key": [],
                        "api_base": "https://generativelanguage.googleapis.com/",
                        "timeout": 120,
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
                        "gm_thinking_config": {"budget": 0, "level": "HIGH"},
                        "proxy": "",
                    },
                    "Anthropic": {
                        "id": "anthropic",
                        "provider": "anthropic",
                        "type": "anthropic_chat_completion",
                        "provider_type": "chat_completion",
                        "enable": True,
                        "key": [],
                        "api_base": "https://api.anthropic.com/v1",
                        "timeout": 120,
                        "proxy": "",
                        "anth_thinking_config": {"type": "", "budget": 0, "effort": ""},
                    },
                    "Moonshot": {
                        "id": "moonshot",
                        "provider": "moonshot",
                        "type": "openai_chat_completion",
                        "provider_type": "chat_completion",
                        "enable": True,
                        "key": [],
                        "timeout": 120,
                        "api_base": "https://api.moonshot.cn/v1",
                        "proxy": "",
                        "custom_headers": {},
                    },
                    "xAI": {
                        "id": "xai",
                        "provider": "xai",
                        "type": "xai_chat_completion",
                        "provider_type": "chat_completion",
                        "enable": True,
                        "key": [],
                        "api_base": "https://api.x.ai/v1",
                        "timeout": 120,
                        "proxy": "",
                        "custom_headers": {},
                        "xai_native_search": False,
                    },
                    "DeepSeek": {
                        "id": "deepseek",
                        "provider": "deepseek",
                        "type": "openai_chat_completion",
                        "provider_type": "chat_completion",
                        "enable": True,
                        "key": [],
                        "api_base": "https://api.deepseek.com/v1",
                        "timeout": 120,
                        "proxy": "",
                        "custom_headers": {},
                    },
                    "Zhipu": {
                        "id": "zhipu",
                        "provider": "zhipu",
                        "type": "zhipu_chat_completion",
                        "provider_type": "chat_completion",
                        "enable": True,
                        "key": [],
                        "timeout": 120,
                        "api_base": "https://open.bigmodel.cn/api/paas/v4/",
                        "proxy": "",
                        "custom_headers": {},
                    },
                    "AIHubMix": {
                        "id": "aihubmix",
                        "provider": "aihubmix",
                        "type": "aihubmix_chat_completion",
                        "provider_type": "chat_completion",
                        "enable": True,
                        "key": [],
                        "timeout": 120,
                        "api_base": "https://aihubmix.com/v1",
                        "proxy": "",
                        "custom_headers": {},
                    },
                    "OpenRouter": {
                        "id": "openrouter",
                        "provider": "openrouter",
                        "type": "openrouter_chat_completion",
                        "provider_type": "chat_completion",
                        "enable": True,
                        "key": [],
                        "timeout": 120,
                        "api_base": "https://openrouter.ai/v1",
                        "proxy": "",
                        "custom_headers": {},
                    },
                    "NVIDIA": {
                        "id": "nvidia",
                        "provider": "nvidia",
                        "type": "openai_chat_completion",
                        "provider_type": "chat_completion",
                        "enable": True,
                        "key": [],
                        "api_base": "https://integrate.api.nvidia.com/v1",
                        "timeout": 120,
                        "proxy": "",
                        "custom_headers": {},
                    },
                    "Azure OpenAI": {
                        "id": "azure_openai",
                        "provider": "azure",
                        "type": "openai_chat_completion",
                        "provider_type": "chat_completion",
                        "enable": True,
                        "api_version": "2024-05-01-preview",
                        "key": [],
                        "api_base": "",
                        "timeout": 120,
                        "proxy": "",
                        "custom_headers": {},
                    },
                    "Ollama": {
                        "id": "ollama",
                        "provider": "ollama",
                        "type": "openai_chat_completion",
                        "provider_type": "chat_completion",
                        "enable": True,
                        "key": ["ollama"],  # ollama 的 key 默认是 ollama
                        "api_base": "http://127.0.0.1:11434/v1",
                        "proxy": "",
                        "custom_headers": {},
                    },
                    "LM Studio": {
                        "id": "lm_studio",
                        "provider": "lm_studio",
                        "type": "openai_chat_completion",
                        "provider_type": "chat_completion",
                        "enable": True,
                        "key": ["lmstudio"],
                        "api_base": "http://127.0.0.1:1234/v1",
                        "proxy": "",
                        "custom_headers": {},
                    },
                    "Gemini_OpenAI_API": {
                        "id": "google_gemini_openai",
                        "provider": "google",
                        "type": "openai_chat_completion",
                        "provider_type": "chat_completion",
                        "enable": True,
                        "key": [],
                        "api_base": "https://generativelanguage.googleapis.com/v1beta/openai/",
                        "timeout": 120,
                        "proxy": "",
                        "custom_headers": {},
                    },
                    "Groq": {
                        "id": "groq",
                        "provider": "groq",
                        "type": "groq_chat_completion",
                        "provider_type": "chat_completion",
                        "enable": True,
                        "key": [],
                        "api_base": "https://api.groq.com/openai/v1",
                        "timeout": 120,
                        "proxy": "",
                        "custom_headers": {},
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
                        "proxy": "",
                        "custom_headers": {},
                    },
                    "SiliconFlow": {
                        "id": "siliconflow",
                        "provider": "siliconflow",
                        "type": "openai_chat_completion",
                        "provider_type": "chat_completion",
                        "enable": True,
                        "key": [],
                        "timeout": 120,
                        "api_base": "https://api.siliconflow.cn/v1",
                        "proxy": "",
                        "custom_headers": {},
                    },
                    "PPIO": {
                        "id": "ppio",
                        "provider": "ppio",
                        "type": "openai_chat_completion",
                        "provider_type": "chat_completion",
                        "enable": True,
                        "key": [],
                        "api_base": "https://api.ppinfra.com/v3/openai",
                        "timeout": 120,
                        "proxy": "",
                        "custom_headers": {},
                    },
                    "TokenPony": {
                        "id": "tokenpony",
                        "provider": "tokenpony",
                        "type": "openai_chat_completion",
                        "provider_type": "chat_completion",
                        "enable": True,
                        "key": [],
                        "api_base": "https://api.tokenpony.cn/v1",
                        "timeout": 120,
                        "proxy": "",
                        "custom_headers": {},
                    },
                    "Compshare": {
                        "id": "compshare",
                        "provider": "compshare",
                        "type": "openai_chat_completion",
                        "provider_type": "chat_completion",
                        "enable": True,
                        "key": [],
                        "api_base": "https://api.modelverse.cn/v1",
                        "timeout": 120,
                        "proxy": "",
                        "custom_headers": {},
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
                        "proxy": "",
                        "custom_headers": {},
                    },
                    "Dify": {
                        "id": "dify_app_default",
                        "provider": "dify",
                        "type": "dify",
                        "provider_type": "agent_runner",
                        "enable": True,
                        "dify_api_type": "chat",
                        "dify_api_key": "",
                        "dify_api_base": "https://api.dify.ai/v1",
                        "dify_workflow_output_key": "astrbot_wf_output",
                        "dify_query_input_key": "astrbot_text_query",
                        "variables": {},
                        "timeout": 60,
                        "proxy": "",
                    },
                    "Coze": {
                        "id": "coze",
                        "provider": "coze",
                        "provider_type": "agent_runner",
                        "type": "coze",
                        "enable": True,
                        "coze_api_key": "",
                        "bot_id": "",
                        "coze_api_base": "https://api.coze.cn",
                        "timeout": 60,
                        "proxy": "",
                        # "auto_save_history": True,
                    },
                    "阿里云百炼应用": {
                        "id": "dashscope",
                        "provider": "dashscope",
                        "type": "dashscope",
                        "provider_type": "agent_runner",
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
                        "proxy": "",
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
                        "proxy": "",
                        "custom_headers": {},
                        "custom_extra_body": {},
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
                        "proxy": "",
                    },
                    "Whisper(Local)": {
                        "provider": "openai",
                        "type": "openai_whisper_selfhost",
                        "provider_type": "speech_to_text",
                        "enable": False,
                        "id": "whisper_selfhost",
                        "model": "tiny",
                    },
                    "SenseVoice(Local)": {
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
                        "proxy": "",
                    },
                    "Genie TTS": {
                        "id": "genie_tts",
                        "provider": "genie_tts",
                        "type": "genie_tts",
                        "provider_type": "text_to_speech",
                        "enable": False,
                        "genie_character_name": "mika",
                        "genie_onnx_model_dir": "CharacterModels/v2ProPlus/mika/tts_models",
                        "genie_language": "Japanese",
                        "genie_refer_audio_path": "",
                        "genie_refer_text": "",
                        "timeout": 20,
                    },
                    "Edge TTS": {
                        "id": "edge_tts",
                        "provider": "microsoft",
                        "type": "edge_tts",
                        "provider_type": "text_to_speech",
                        "enable": False,
                        "edge-tts-voice": "zh-CN-XiaoxiaoNeural",
                        "rate": "+0%",
                        "volume": "+0%",
                        "pitch": "+0Hz",
                        "timeout": 20,
                    },
                    "GSV TTS(Local)": {
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
                        "proxy": "",
                    },
                    "阿里云百炼 TTS(API)": {
                        "hint": "API Key 从 https://bailian.console.aliyun.com/?tab=model#/api-key 获取。模型和音色的选择文档请参考: 阿里云百炼语音合成音色名称。具体可参考 https://help.aliyun.com/zh/model-studio/speech-synthesis-and-speech-recognition",
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
                        "proxy": "",
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
                        "minimax-voice-emotion": "auto",
                        "minimax-voice-latex": False,
                        "minimax-voice-english-normalization": False,
                        "timeout": 20,
                        "proxy": "",
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
                        "proxy": "",
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
                        "proxy": "",
                    },
                    "OpenAI Embedding": {
                        "id": "openai_embedding",
                        "type": "openai_embedding",
                        "provider": "openai",
                        "provider_type": "embedding",
                        "hint": "provider_group.provider.openai_embedding.hint",
                        "enable": True,
                        "embedding_api_key": "",
                        "embedding_api_base": "",
                        "embedding_model": "",
                        "embedding_dimensions": 1024,
                        "timeout": 20,
                        "proxy": "",
                    },
                    "Gemini Embedding": {
                        "id": "gemini_embedding",
                        "type": "gemini_embedding",
                        "provider": "google",
                        "provider_type": "embedding",
                        "hint": "provider_group.provider.gemini_embedding.hint",
                        "enable": True,
                        "embedding_api_key": "",
                        "embedding_api_base": "",
                        "embedding_model": "gemini-embedding-exp-03-07",
                        "embedding_dimensions": 768,
                        "timeout": 20,
                        "proxy": "",
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
                    "Xinference Rerank": {
                        "id": "xinference_rerank",
                        "type": "xinference_rerank",
                        "provider": "xinference",
                        "provider_type": "rerank",
                        "enable": True,
                        "rerank_api_key": "",
                        "rerank_api_base": "http://127.0.0.1:9997",
                        "rerank_model": "BAAI/bge-reranker-base",
                        "timeout": 20,
                        "launch_model_if_not_running": False,
                    },
                    "阿里云百炼重排序": {
                        "id": "bailian_rerank",
                        "type": "bailian_rerank",
                        "provider": "bailian",
                        "provider_type": "rerank",
                        "enable": True,
                        "rerank_api_key": "",
                        "rerank_api_base": "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank",
                        "rerank_model": "qwen3-rerank",
                        "timeout": 30,
                        "return_documents": False,
                        "instruct": "",
                    },
                    "Xinference STT": {
                        "id": "xinference_stt",
                        "type": "xinference_stt",
                        "provider": "xinference",
                        "provider_type": "speech_to_text",
                        "enable": False,
                        "api_key": "",
                        "api_base": "http://127.0.0.1:9997",
                        "model": "whisper-large-v3",
                        "timeout": 180,
                        "launch_model_if_not_running": False,
                    },
                },
                "items": {
                    "genie_onnx_model_dir": {
                        "description": "ONNX Model Directory",
                        "type": "string",
                        "hint": "The directory path containing the ONNX model files",
                    },
                    "genie_language": {
                        "description": "Language",
                        "type": "string",
                        "options": ["Japanese", "English", "Chinese"],
                    },
                    "provider_source_id": {
                        "invisible": True,
                        "type": "string",
                    },
                    "xai_native_search": {
                        "description": "启用原生搜索功能",
                        "type": "bool",
                        "hint": "启用后，将通过 xAI 的 Chat Completions 原生 Live Search 进行联网检索（按需计费）。仅对 xAI 提供商生效。",
                        "condition": {"provider": "xai"},
                    },
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
                    "return_documents": {
                        "description": "是否在排序结果中返回文档原文",
                        "type": "bool",
                        "hint": "默认值false，以减少网络传输开销。",
                    },
                    "instruct": {
                        "description": "自定义排序任务类型说明",
                        "type": "string",
                        "hint": "仅在使用 qwen3-rerank 模型时生效。建议使用英文撰写。",
                    },
                    "launch_model_if_not_running": {
                        "description": "模型未运行时自动启动",
                        "type": "bool",
                        "hint": "如果模型当前未在 Xinference 服务中运行，是否尝试自动启动它。在生产环境中建议关闭。",
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
                    "custom_headers": {
                        "description": "自定义添加请求头",
                        "type": "dict",
                        "items": {},
                        "hint": "此处添加的键值对将被合并到 OpenAI SDK 的 default_headers 中，用于自定义 HTTP 请求头。值必须为字符串。",
                    },
                    "custom_extra_body": {
                        "description": "自定义请求体参数",
                        "type": "dict",
                        "items": {},
                        "hint": "用于在请求时添加额外的参数，如 temperature、top_p、max_tokens 等。",
                        "template_schema": {
                            "temperature": {
                                "name": "Temperature",
                                "description": "温度参数",
                                "hint": "控制输出的随机性，范围通常为 0-2。值越高越随机。",
                                "type": "float",
                                "default": 0.6,
                                "slider": {"min": 0, "max": 2, "step": 0.1},
                            },
                            "top_p": {
                                "name": "Top-p",
                                "description": "Top-p 采样",
                                "hint": "核采样参数，范围通常为 0-1。控制模型考虑的概率质量。",
                                "type": "float",
                                "default": 1.0,
                                "slider": {"min": 0, "max": 1, "step": 0.01},
                            },
                            "max_tokens": {
                                "name": "Max Tokens",
                                "description": "最大令牌数",
                                "hint": "生成的最大令牌数。",
                                "type": "int",
                                "default": 8192,
                            },
                        },
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
                        "_special": "get_embedding_dim",
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
                    "dashscope_tts_voice": {"description": "音色", "type": "string"},
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
                        "description": "Thinking Config",
                        "type": "object",
                        "items": {
                            "budget": {
                                "description": "Thinking Budget",
                                "type": "int",
                                "hint": "Guides the model on the specific number of thinking tokens to use for reasoning. See: https://ai.google.dev/gemini-api/docs/thinking#set-budget",
                            },
                            "level": {
                                "description": "Thinking Level",
                                "type": "string",
                                "hint": "Recommended for Gemini 3 models and onwards, lets you control reasoning behavior.See: https://ai.google.dev/gemini-api/docs/thinking#thinking-levels",
                                "options": [
                                    "MINIMAL",
                                    "LOW",
                                    "MEDIUM",
                                    "HIGH",
                                ],
                            },
                        },
                    },
                    "anth_thinking_config": {
                        "description": "思考配置",
                        "type": "object",
                        "items": {
                            "type": {
                                "description": "思考类型",
                                "type": "string",
                                "options": ["", "adaptive"],
                                "hint": "Opus 4.6+ / Sonnet 4.6+ 推荐设为 'adaptive'。留空则使用手动 budget 模式。参见: https://platform.claude.com/docs/en/build-with-claude/adaptive-thinking",
                            },
                            "budget": {
                                "description": "思考预算",
                                "type": "int",
                                "hint": "手动 budget_tokens，需 >= 1024。仅在 type 为空时生效。Opus 4.6 / Sonnet 4.6 上已弃用。参见: https://platform.claude.com/docs/en/build-with-claude/extended-thinking",
                            },
                            "effort": {
                                "description": "思考深度",
                                "type": "string",
                                "options": ["", "low", "medium", "high", "max"],
                                "hint": "type 为 'adaptive' 时控制思考深度。默认 'high'。'max' 仅限 Opus 4.6。参见: https://platform.claude.com/docs/en/build-with-claude/effort",
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
                        "hint": "控制合成语音的情绪。当为 auto 时，将根据文本内容自动选择情绪。",
                        "options": [
                            "auto",
                            "happy",
                            "sad",
                            "angry",
                            "fearful",
                            "disgusted",
                            "surprised",
                            "calm",
                            "fluent",
                            "whisper",
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
                    },
                    "key": {
                        "description": "API Key",
                        "type": "list",
                        "items": {"type": "string"},
                    },
                    "api_base": {
                        "description": "API Base URL",
                        "type": "string",
                    },
                    "proxy": {
                        "description": "provider_group.provider.proxy.description",
                        "type": "string",
                        "hint": "provider_group.provider.proxy.hint",
                    },
                    "model": {
                        "description": "模型 ID",
                        "type": "string",
                        "hint": "模型名称，如 gpt-4o-mini, deepseek-chat。",
                    },
                    "max_context_tokens": {
                        "description": "模型上下文窗口大小",
                        "type": "int",
                        "hint": "模型最大上下文 Token 大小。如果为 0，则会自动从模型元数据填充（如有），也可手动修改。",
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
                    "coze_api_key": {
                        "description": "Coze API Key",
                        "type": "string",
                        "hint": "Coze API 密钥，用于访问 Coze 服务。",
                    },
                    "bot_id": {
                        "description": "Bot ID",
                        "type": "string",
                        "hint": "Coze 机器人的 ID，在 Coze 平台上创建机器人后获得。",
                    },
                    "coze_api_base": {
                        "description": "API Base URL",
                        "type": "string",
                        "hint": "Coze API 的基础 URL 地址，默认为 https://api.coze.cn",
                    },
                    "auto_save_history": {
                        "description": "由 Coze 管理对话记录",
                        "type": "bool",
                        "hint": "启用后，将由 Coze 进行对话历史记录管理, 此时 AstrBot 本地保存的上下文不会生效(仅供浏览), 对 AstrBot 的上下文进行的操作也不会生效。如果为禁用, 则使用 AstrBot 管理上下文。",
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
                    "fallback_chat_models": {
                        "type": "list",
                        "items": {"type": "string"},
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
                    "group_name_display": {
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
                    "show_tool_call_result": {
                        "type": "bool",
                    },
                    "unsupported_streaming_strategy": {
                        "type": "string",
                    },
                    "agent_runner_type": {
                        "type": "string",
                    },
                    "dify_agent_runner_provider_id": {
                        "type": "string",
                    },
                    "coze_agent_runner_provider_id": {
                        "type": "string",
                    },
                    "dashscope_agent_runner_provider_id": {
                        "type": "string",
                    },
                    "max_agent_step": {
                        "type": "int",
                    },
                    "tool_call_timeout": {
                        "type": "int",
                    },
                    "tool_schema_mode": {
                        "type": "string",
                    },
                    "file_extract": {
                        "type": "object",
                        "items": {
                            "enable": {
                                "type": "bool",
                            },
                            "provider": {
                                "type": "string",
                            },
                            "moonshotai_api_key": {
                                "type": "string",
                            },
                        },
                    },
                    "proactive_capability": {
                        "type": "object",
                        "items": {
                            "add_cron_tools": {
                                "type": "bool",
                            },
                        },
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
                    "trigger_probability": {
                        "type": "float",
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
                    "image_caption_provider_id": {
                        "type": "string",
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
            "dashboard.ssl.enable": {"type": "bool"},
            "dashboard.ssl.cert_file": {
                "type": "string",
                "condition": {"dashboard.ssl.enable": True},
            },
            "dashboard.ssl.key_file": {
                "type": "string",
                "condition": {"dashboard.ssl.enable": True},
            },
            "dashboard.ssl.ca_certs": {
                "type": "string",
                "condition": {"dashboard.ssl.enable": True},
            },
            "log_file_enable": {"type": "bool"},
            "log_file_path": {"type": "string", "condition": {"log_file_enable": True}},
            "log_file_max_mb": {"type": "int", "condition": {"log_file_enable": True}},
            "temp_dir_max_size": {"type": "int"},
            "trace_log_enable": {"type": "bool"},
            "trace_log_path": {
                "type": "string",
                "condition": {"trace_log_enable": True},
            },
            "trace_log_max_mb": {
                "type": "int",
                "condition": {"trace_log_enable": True},
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
            "kb_names": {"type": "list", "items": {"type": "string"}},
            "kb_fusion_top_k": {"type": "int", "default": 20},
            "kb_final_top_k": {"type": "int", "default": 5},
            "kb_agentic_mode": {"type": "bool"},
        },
    },
}


"""
v4.7.0 之后，name, description, hint 等字段已经实现 i18n 国际化。国际化资源文件位于：

- dashboard/src/i18n/locales/en-US/features/config-metadata.json
- dashboard/src/i18n/locales/zh-CN/features/config-metadata.json

如果在此文件中添加了新的配置字段，请务必同步更新上述两个国际化资源文件。
"""
CONFIG_METADATA_3 = {
    "ai_group": {
        "name": "AI 配置",
        "metadata": {
            "agent_runner": {
                "description": "Agent 执行方式",
                "hint": "选择 AI 对话的执行器，默认为 AstrBot 内置 Agent 执行器，可使用 AstrBot 内的知识库、人格、工具调用功能。如果不打算接入 Dify 或 Coze 等第三方 Agent 执行器，不需要修改此节。",
                "type": "object",
                "items": {
                    "provider_settings.enable": {
                        "description": "启用",
                        "type": "bool",
                        "hint": "AI 对话总开关",
                    },
                    "provider_settings.agent_runner_type": {
                        "description": "执行器",
                        "type": "string",
                        "options": ["local", "dify", "coze", "dashscope"],
                        "labels": ["内置 Agent", "Dify", "Coze", "阿里云百炼应用"],
                        "condition": {
                            "provider_settings.enable": True,
                        },
                    },
                    "provider_settings.coze_agent_runner_provider_id": {
                        "description": "Coze Agent 执行器提供商 ID",
                        "type": "string",
                        "_special": "select_agent_runner_provider:coze",
                        "condition": {
                            "provider_settings.agent_runner_type": "coze",
                            "provider_settings.enable": True,
                        },
                    },
                    "provider_settings.dify_agent_runner_provider_id": {
                        "description": "Dify Agent 执行器提供商 ID",
                        "type": "string",
                        "_special": "select_agent_runner_provider:dify",
                        "condition": {
                            "provider_settings.agent_runner_type": "dify",
                            "provider_settings.enable": True,
                        },
                    },
                    "provider_settings.dashscope_agent_runner_provider_id": {
                        "description": "阿里云百炼应用 Agent 执行器提供商 ID",
                        "type": "string",
                        "_special": "select_agent_runner_provider:dashscope",
                        "condition": {
                            "provider_settings.agent_runner_type": "dashscope",
                            "provider_settings.enable": True,
                        },
                    },
                },
            },
            "ai": {
                "description": "模型",
                "hint": "当使用非内置 Agent 执行器时，默认对话模型和默认图片转述模型可能会无效，但某些插件会依赖此配置项来调用 AI 能力。",
                "type": "object",
                "items": {
                    "provider_settings.default_provider_id": {
                        "description": "默认对话模型",
                        "type": "string",
                        "_special": "select_provider",
                        "hint": "留空时使用第一个模型",
                    },
                    "provider_settings.fallback_chat_models": {
                        "description": "回退对话模型列表",
                        "type": "list",
                        "items": {"type": "string"},
                        "_special": "select_providers",
                        "hint": "主聊天模型请求失败时，按顺序切换到这些模型。",
                    },
                    "provider_settings.default_image_caption_provider_id": {
                        "description": "默认图片转述模型",
                        "type": "string",
                        "_special": "select_provider",
                        "hint": "留空代表不使用，可用于非多模态模型",
                    },
                    "provider_stt_settings.enable": {
                        "description": "启用语音转文本",
                        "type": "bool",
                        "hint": "STT 总开关",
                    },
                    "provider_stt_settings.provider_id": {
                        "description": "默认语音转文本模型",
                        "type": "string",
                        "hint": "用户也可使用 /provider 指令单独选择会话的 STT 模型。",
                        "_special": "select_provider_stt",
                        "condition": {
                            "provider_stt_settings.enable": True,
                        },
                    },
                    "provider_tts_settings.enable": {
                        "description": "启用文本转语音",
                        "type": "bool",
                        "hint": "TTS 总开关",
                    },
                    "provider_tts_settings.provider_id": {
                        "description": "默认文本转语音模型",
                        "type": "string",
                        "_special": "select_provider_tts",
                        "condition": {
                            "provider_tts_settings.enable": True,
                        },
                    },
                    "provider_tts_settings.trigger_probability": {
                        "description": "TTS 触发概率",
                        "type": "float",
                        "slider": {"min": 0, "max": 1, "step": 0.05},
                        "condition": {
                            "provider_tts_settings.enable": True,
                        },
                    },
                    "provider_settings.image_caption_prompt": {
                        "description": "图片转述提示词",
                        "type": "text",
                    },
                },
                "condition": {
                    "provider_settings.enable": True,
                },
            },
            "persona": {
                "description": "人格",
                "hint": "",
                "type": "object",
                "items": {
                    "provider_settings.default_personality": {
                        "description": "默认采用的人格",
                        "type": "string",
                        "_special": "select_persona",
                    },
                },
                "condition": {
                    "provider_settings.agent_runner_type": "local",
                    "provider_settings.enable": True,
                },
            },
            "knowledgebase": {
                "description": "知识库",
                "hint": "",
                "type": "object",
                "items": {
                    "kb_names": {
                        "description": "知识库列表",
                        "type": "list",
                        "items": {"type": "string"},
                        "_special": "select_knowledgebase",
                        "hint": "支持多选",
                    },
                    "kb_fusion_top_k": {
                        "description": "融合检索结果数",
                        "type": "int",
                        "hint": "多个知识库检索结果融合后的返回结果数量",
                    },
                    "kb_final_top_k": {
                        "description": "最终返回结果数",
                        "type": "int",
                        "hint": "从知识库中检索到的结果数量，越大可能获得越多相关信息，但也可能引入噪音。建议根据实际需求调整",
                    },
                    "kb_agentic_mode": {
                        "description": "Agentic 知识库检索",
                        "type": "bool",
                        "hint": "启用后，知识库检索将作为 LLM Tool，由模型自主决定何时调用知识库进行查询。需要模型支持函数调用能力。",
                    },
                },
                "condition": {
                    "provider_settings.agent_runner_type": "local",
                    "provider_settings.enable": True,
                },
            },
            "websearch": {
                "description": "网页搜索",
                "hint": "",
                "type": "object",
                "items": {
                    "provider_settings.web_search": {
                        "description": "启用网页搜索",
                        "type": "bool",
                    },
                    "provider_settings.websearch_provider": {
                        "description": "网页搜索提供商",
                        "type": "string",
                        "options": ["default", "tavily", "baidu_ai_search", "bocha"],
                        "condition": {
                            "provider_settings.web_search": True,
                        },
                    },
                    "provider_settings.websearch_tavily_key": {
                        "description": "Tavily API Key",
                        "type": "list",
                        "items": {"type": "string"},
                        "hint": "可添加多个 Key 进行轮询。",
                        "condition": {
                            "provider_settings.websearch_provider": "tavily",
                            "provider_settings.web_search": True,
                        },
                    },
                    "provider_settings.websearch_bocha_key": {
                        "description": "BoCha API Key",
                        "type": "list",
                        "items": {"type": "string"},
                        "hint": "可添加多个 Key 进行轮询。",
                        "condition": {
                            "provider_settings.websearch_provider": "bocha",
                            "provider_settings.web_search": True,
                        },
                    },
                    "provider_settings.websearch_baidu_app_builder_key": {
                        "description": "百度千帆智能云 APP Builder API Key",
                        "type": "string",
                        "hint": "参考：https://console.bce.baidu.com/iam/#/iam/apikey/list",
                        "condition": {
                            "provider_settings.websearch_provider": "baidu_ai_search",
                        },
                    },
                    "provider_settings.web_search_link": {
                        "description": "显示来源引用",
                        "type": "bool",
                        "condition": {
                            "provider_settings.web_search": True,
                        },
                    },
                },
                "condition": {
                    "provider_settings.agent_runner_type": "local",
                    "provider_settings.enable": True,
                },
            },
            "agent_computer_use": {
                "description": "Agent Computer Use",
                "hint": "",
                "type": "object",
                "items": {
                    "provider_settings.computer_use_runtime": {
                        "description": "Computer Use Runtime",
                        "type": "string",
                        "options": ["none", "local", "sandbox"],
                        "labels": ["无", "本地", "沙箱"],
                        "hint": "选择 Computer Use 运行环境。",
                    },
                    "provider_settings.computer_use_require_admin": {
                        "description": "需要 AstrBot 管理员权限",
                        "type": "bool",
                        "hint": "开启后，需要 AstrBot 管理员权限才能调用使用电脑能力。在平台配置->管理员中可添加管理员。使用 /sid 指令查看管理员 ID。",
                    },
                    "provider_settings.sandbox.booter": {
                        "description": "沙箱环境驱动器",
                        "type": "string",
                        "options": ["shipyard"],
                        "labels": ["Shipyard"],
                        "condition": {
                            "provider_settings.computer_use_runtime": "sandbox",
                        },
                    },
                    "provider_settings.sandbox.shipyard_endpoint": {
                        "description": "Shipyard API Endpoint",
                        "type": "string",
                        "hint": "Shipyard 服务的 API 访问地址。",
                        "condition": {
                            "provider_settings.computer_use_runtime": "sandbox",
                            "provider_settings.sandbox.booter": "shipyard",
                        },
                        "_special": "check_shipyard_connection",
                    },
                    "provider_settings.sandbox.shipyard_access_token": {
                        "description": "Shipyard Access Token",
                        "type": "string",
                        "hint": "用于访问 Shipyard 服务的访问令牌。",
                        "condition": {
                            "provider_settings.computer_use_runtime": "sandbox",
                            "provider_settings.sandbox.booter": "shipyard",
                        },
                    },
                    "provider_settings.sandbox.shipyard_ttl": {
                        "description": "Shipyard Session TTL",
                        "type": "int",
                        "hint": "Shipyard 会话的生存时间（秒）。",
                        "condition": {
                            "provider_settings.computer_use_runtime": "sandbox",
                            "provider_settings.sandbox.booter": "shipyard",
                        },
                    },
                    "provider_settings.sandbox.shipyard_max_sessions": {
                        "description": "Shipyard Max Sessions",
                        "type": "int",
                        "hint": "Shipyard 最大会话数量。",
                        "condition": {
                            "provider_settings.computer_use_runtime": "sandbox",
                            "provider_settings.sandbox.booter": "shipyard",
                        },
                    },
                },
                "condition": {
                    "provider_settings.agent_runner_type": "local",
                    "provider_settings.enable": True,
                },
            },
            # "file_extract": {
            #     "description": "文档解析能力 [beta]",
            #     "type": "object",
            #     "items": {
            #         "provider_settings.file_extract.enable": {
            #             "description": "启用文档解析能力",
            #             "type": "bool",
            #         },
            #         "provider_settings.file_extract.provider": {
            #             "description": "文档解析提供商",
            #             "type": "string",
            #             "options": ["moonshotai"],
            #             "condition": {
            #                 "provider_settings.file_extract.enable": True,
            #             },
            #         },
            #         "provider_settings.file_extract.moonshotai_api_key": {
            #             "description": "Moonshot AI API Key",
            #             "type": "string",
            #             "condition": {
            #                 "provider_settings.file_extract.provider": "moonshotai",
            #                 "provider_settings.file_extract.enable": True,
            #             },
            #         },
            #     },
            #     "condition": {
            #         "provider_settings.agent_runner_type": "local",
            #         "provider_settings.enable": True,
            #     },
            # },
            "proactive_capability": {
                "description": "主动型 Agent",
                "hint": "https://docs.astrbot.app/use/proactive-agent.html",
                "type": "object",
                "items": {
                    "provider_settings.proactive_capability.add_cron_tools": {
                        "description": "启用",
                        "type": "bool",
                        "hint": "启用后，将会传递给 Agent 相关工具来实现主动型 Agent。你可以告诉 AstrBot 未来某个时间要做的事情，它将被定时触发然后执行任务。",
                    },
                },
                "condition": {
                    "provider_settings.agent_runner_type": "local",
                    "provider_settings.enable": True,
                },
            },
            "truncate_and_compress": {
                "hint": "",
                "description": "上下文管理策略",
                "type": "object",
                "items": {
                    "provider_settings.max_context_length": {
                        "description": "最多携带对话轮数",
                        "type": "int",
                        "hint": "超出这个数量时丢弃最旧的部分，一轮聊天记为 1 条，-1 为不限制",
                        "condition": {
                            "provider_settings.agent_runner_type": "local",
                        },
                    },
                    "provider_settings.dequeue_context_length": {
                        "description": "丢弃对话轮数",
                        "type": "int",
                        "hint": "超出最多携带对话轮数时, 一次丢弃的聊天轮数",
                        "condition": {
                            "provider_settings.agent_runner_type": "local",
                        },
                    },
                    "provider_settings.context_limit_reached_strategy": {
                        "description": "超出模型上下文窗口时的处理方式",
                        "type": "string",
                        "options": ["truncate_by_turns", "llm_compress"],
                        "labels": ["按对话轮数截断", "由 LLM 压缩上下文"],
                        "condition": {
                            "provider_settings.agent_runner_type": "local",
                        },
                        "hint": "",
                    },
                    "provider_settings.llm_compress_instruction": {
                        "description": "上下文压缩提示词",
                        "type": "text",
                        "hint": "如果为空则使用默认提示词。",
                        "condition": {
                            "provider_settings.context_limit_reached_strategy": "llm_compress",
                            "provider_settings.agent_runner_type": "local",
                        },
                    },
                    "provider_settings.llm_compress_keep_recent": {
                        "description": "压缩时保留最近对话轮数",
                        "type": "int",
                        "hint": "始终保留的最近 N 轮对话。",
                        "condition": {
                            "provider_settings.context_limit_reached_strategy": "llm_compress",
                            "provider_settings.agent_runner_type": "local",
                        },
                    },
                    "provider_settings.llm_compress_provider_id": {
                        "description": "用于上下文压缩的模型提供商 ID",
                        "type": "string",
                        "_special": "select_provider",
                        "hint": "留空时将降级为“按对话轮数截断”的策略。",
                        "condition": {
                            "provider_settings.context_limit_reached_strategy": "llm_compress",
                            "provider_settings.agent_runner_type": "local",
                        },
                    },
                },
                "condition": {
                    "provider_settings.agent_runner_type": "local",
                    "provider_settings.enable": True,
                },
            },
            "others": {
                "description": "其他配置",
                "type": "object",
                "items": {
                    "provider_settings.display_reasoning_text": {
                        "description": "显示思考内容",
                        "type": "bool",
                        "condition": {
                            "provider_settings.agent_runner_type": "local",
                        },
                    },
                    "provider_settings.streaming_response": {
                        "description": "流式输出",
                        "type": "bool",
                    },
                    "provider_settings.unsupported_streaming_strategy": {
                        "description": "不支持流式回复的平台",
                        "type": "string",
                        "options": ["realtime_segmenting", "turn_off"],
                        "hint": "选择在不支持流式回复的平台上的处理方式。实时分段回复会在系统接收流式响应检测到诸如标点符号等分段点时，立即发送当前已接收的内容",
                        "labels": ["实时分段回复", "关闭流式回复"],
                        "condition": {
                            "provider_settings.streaming_response": True,
                        },
                    },
                    "provider_settings.llm_safety_mode": {
                        "description": "健康模式",
                        "type": "bool",
                        "hint": "引导模型输出健康、安全的内容，避免有害或敏感话题。",
                    },
                    "provider_settings.safety_mode_strategy": {
                        "description": "健康模式策略",
                        "type": "string",
                        "options": ["system_prompt"],
                        "hint": "选择健康模式的实现策略。",
                        "condition": {
                            "provider_settings.llm_safety_mode": True,
                        },
                    },
                    "provider_settings.identifier": {
                        "description": "用户识别",
                        "type": "bool",
                        "hint": "启用后，会在提示词前包含用户 ID 信息。",
                    },
                    "provider_settings.group_name_display": {
                        "description": "显示群名称",
                        "type": "bool",
                        "hint": "启用后，在支持的平台(OneBot v11)上会在提示词前包含群名称信息。",
                    },
                    "provider_settings.datetime_system_prompt": {
                        "description": "现实世界时间感知",
                        "type": "bool",
                        "hint": "启用后，会在系统提示词中附带当前时间信息。",
                        "condition": {
                            "provider_settings.agent_runner_type": "local",
                        },
                    },
                    "provider_settings.show_tool_use_status": {
                        "description": "输出函数调用状态",
                        "type": "bool",
                        "condition": {
                            "provider_settings.agent_runner_type": "local",
                        },
                    },
                    "provider_settings.show_tool_call_result": {
                        "description": "输出函数调用返回结果",
                        "type": "bool",
                        "hint": "仅在输出函数调用状态启用时生效，展示结果前 70 个字符。",
                        "condition": {
                            "provider_settings.agent_runner_type": "local",
                            "provider_settings.show_tool_use_status": True,
                        },
                    },
                    "provider_settings.sanitize_context_by_modalities": {
                        "description": "按模型能力清理历史上下文",
                        "type": "bool",
                        "hint": "开启后，在每次请求 LLM 前会按当前模型提供商中所选择的模型能力删除对话中不支持的图片/工具调用结构（会改变模型看到的历史）",
                        "condition": {
                            "provider_settings.agent_runner_type": "local",
                        },
                    },
                    "provider_settings.max_quoted_fallback_images": {
                        "description": "引用图片回退解析上限",
                        "type": "int",
                        "hint": "引用/转发消息回退解析图片时的最大注入数量，超出会截断。",
                        "condition": {
                            "provider_settings.agent_runner_type": "local",
                        },
                    },
                    "provider_settings.quoted_message_parser.max_component_chain_depth": {
                        "description": "引用解析组件链深度",
                        "type": "int",
                        "hint": "解析 Reply 组件链时允许的最大递归深度。",
                        "condition": {
                            "provider_settings.agent_runner_type": "local",
                        },
                    },
                    "provider_settings.quoted_message_parser.max_forward_node_depth": {
                        "description": "引用解析转发节点深度",
                        "type": "int",
                        "hint": "解析合并转发节点时允许的最大递归深度。",
                        "condition": {
                            "provider_settings.agent_runner_type": "local",
                        },
                    },
                    "provider_settings.quoted_message_parser.max_forward_fetch": {
                        "description": "引用解析转发拉取上限",
                        "type": "int",
                        "hint": "递归拉取 get_forward_msg 的最大次数。",
                        "condition": {
                            "provider_settings.agent_runner_type": "local",
                        },
                    },
                    "provider_settings.quoted_message_parser.warn_on_action_failure": {
                        "description": "引用解析 action 失败告警",
                        "type": "bool",
                        "hint": "开启后，get_msg/get_forward_msg 全部尝试失败时输出 warning 日志。",
                        "condition": {
                            "provider_settings.agent_runner_type": "local",
                        },
                    },
                    "provider_settings.max_agent_step": {
                        "description": "工具调用轮数上限",
                        "type": "int",
                        "condition": {
                            "provider_settings.agent_runner_type": "local",
                        },
                    },
                    "provider_settings.tool_call_timeout": {
                        "description": "工具调用超时时间（秒）",
                        "type": "int",
                        "condition": {
                            "provider_settings.agent_runner_type": "local",
                        },
                    },
                    "provider_settings.tool_schema_mode": {
                        "description": "工具调用模式",
                        "type": "string",
                        "options": ["skills_like", "full"],
                        "labels": ["Skills-like（两阶段）", "Full（完整参数）"],
                        "hint": "skills-like 先下发工具名称与描述，再下发参数；full 一次性下发完整参数。",
                        "condition": {
                            "provider_settings.agent_runner_type": "local",
                        },
                    },
                    "provider_settings.wake_prefix": {
                        "description": "LLM 聊天额外唤醒前缀 ",
                        "type": "string",
                        "hint": "如果唤醒前缀为 /, 额外聊天唤醒前缀为 chat，则需要 /chat 才会触发 LLM 请求",
                    },
                    "provider_settings.prompt_prefix": {
                        "description": "用户提示词",
                        "type": "string",
                        "hint": "可使用 {{prompt}} 作为用户输入的占位符。如果不输入占位符则代表添加在用户输入的前面。",
                    },
                    "provider_tts_settings.dual_output": {
                        "description": "开启 TTS 时同时输出语音和文字内容",
                        "type": "bool",
                    },
                    "provider_settings.reachability_check": {
                        "description": "提供商可达性检测",
                        "type": "bool",
                        "hint": "/provider 命令列出模型时是否并发检测连通性。开启后会主动调用模型测试连通性，可能产生额外 token 消耗。",
                    },
                },
                "condition": {
                    "provider_settings.enable": True,
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
                    "disable_builtin_commands": {
                        "description": "禁用自带指令",
                        "type": "bool",
                        "hint": "禁用所有 AstrBot 的自带指令，如 help, provider, model 等。",
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
                    "content_safety.also_use_in_response": {
                        "description": "同时检查模型的响应内容",
                        "type": "bool",
                    },
                    "content_safety.baidu_aip.enable": {
                        "description": "使用百度内容安全审核",
                        "type": "bool",
                        "hint": "您需要手动安装 baidu-aip 库。",
                    },
                    "content_safety.baidu_aip.app_id": {
                        "description": "App ID",
                        "type": "string",
                        "condition": {
                            "content_safety.baidu_aip.enable": True,
                        },
                    },
                    "content_safety.baidu_aip.api_key": {
                        "description": "API Key",
                        "type": "string",
                        "condition": {
                            "content_safety.baidu_aip.enable": True,
                        },
                    },
                    "content_safety.baidu_aip.secret_key": {
                        "description": "Secret Key",
                        "type": "string",
                        "condition": {
                            "content_safety.baidu_aip.enable": True,
                        },
                    },
                    "content_safety.internal_keywords.enable": {
                        "description": "关键词检查",
                        "type": "bool",
                    },
                    "content_safety.internal_keywords.extra_keywords": {
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
                    "platform_specific.lark.pre_ack_emoji.enable": {
                        "description": "[飞书] 启用预回应表情",
                        "type": "bool",
                    },
                    "platform_specific.lark.pre_ack_emoji.emojis": {
                        "description": "表情列表（飞书表情枚举名）",
                        "type": "list",
                        "items": {"type": "string"},
                        "hint": "表情枚举名参考：https://open.feishu.cn/document/server-docs/im-v1/message-reaction/emojis-introduce",
                        "condition": {
                            "platform_specific.lark.pre_ack_emoji.enable": True,
                        },
                    },
                    "platform_specific.telegram.pre_ack_emoji.enable": {
                        "description": "[Telegram] 启用预回应表情",
                        "type": "bool",
                    },
                    "platform_specific.telegram.pre_ack_emoji.emojis": {
                        "description": "表情列表（Unicode）",
                        "type": "list",
                        "items": {"type": "string"},
                        "hint": "Telegram 仅支持固定反应集合，参考：https://gist.github.com/Soulter/3f22c8e5f9c7e152e967e8bc28c97fc9",
                        "condition": {
                            "platform_specific.telegram.pre_ack_emoji.enable": True,
                        },
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
                        "description": "间隔方法。",
                        "hint": "random 为随机时间，log 为根据消息长度计算，$y=log_<log_base>(x)$，x为字数，y的单位为秒。",
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
                        "hint": "对数间隔的底数，默认为 2.6。取值范围为 1.0-10.0。",
                        "condition": {
                            "platform_settings.segmented_reply.interval_method": "log",
                        },
                    },
                    "platform_settings.segmented_reply.words_count_threshold": {
                        "description": "分段回复字数阈值",
                        "hint": "分段回复的字数上限。只有字数小于此值的消息才会被分段，超过此值的长消息将直接发送（不分段）。默认为 150",
                        "type": "int",
                    },
                    "platform_settings.segmented_reply.split_mode": {
                        "description": "分段模式",
                        "type": "string",
                        "options": ["regex", "words"],
                        "labels": ["正则表达式", "分段词列表"],
                    },
                    "platform_settings.segmented_reply.regex": {
                        "description": "分段正则表达式",
                        "hint": "用于分隔一段消息。默认情况下会根据句号、问号等标点符号分隔。如填写 `[。？！]` 将移除所有的句号、问号、感叹号。re.findall(r'<regex>', text)",
                        "type": "string",
                        "condition": {
                            "platform_settings.segmented_reply.split_mode": "regex",
                        },
                    },
                    "platform_settings.segmented_reply.split_words": {
                        "description": "分段词列表",
                        "type": "list",
                        "hint": "检测到列表中的任意词时进行分段，如：。、？、！等",
                        "condition": {
                            "platform_settings.segmented_reply.split_mode": "words",
                        },
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
                        "hint": "需要设置群聊图片转述模型。",
                    },
                    "provider_ltm_settings.image_caption_provider_id": {
                        "description": "群聊图片转述模型",
                        "type": "string",
                        "_special": "select_provider",
                        "hint": "用于群聊上下文感知的图片理解，与默认图片转述模型分开配置。",
                        "condition": {
                            "provider_ltm_settings.image_caption": True,
                        },
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
                        "slider": {"min": 0, "max": 1, "step": 0.05},
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
                        "_special": "t2i_template",
                    },
                    "t2i_active_template": {
                        "description": "当前应用的文转图渲染模板",
                        "type": "string",
                        "hint": "此处的值由文转图模板管理页面进行维护。",
                        "invisible": True,
                    },
                    "log_level": {
                        "description": "控制台日志级别",
                        "type": "string",
                        "hint": "控制台输出日志的级别。",
                        "options": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                    },
                    "dashboard.ssl.enable": {
                        "description": "启用 WebUI HTTPS",
                        "type": "bool",
                        "hint": "启用后，WebUI 将直接使用 HTTPS 提供服务。",
                    },
                    "dashboard.ssl.cert_file": {
                        "description": "SSL 证书文件路径",
                        "type": "string",
                        "hint": "证书文件路径（PEM）。支持绝对路径和相对路径（相对于当前工作目录）。",
                        "condition": {"dashboard.ssl.enable": True},
                    },
                    "dashboard.ssl.key_file": {
                        "description": "SSL 私钥文件路径",
                        "type": "string",
                        "hint": "私钥文件路径（PEM）。支持绝对路径和相对路径（相对于当前工作目录）。",
                        "condition": {"dashboard.ssl.enable": True},
                    },
                    "dashboard.ssl.ca_certs": {
                        "description": "SSL CA 证书文件路径",
                        "type": "string",
                        "hint": "可选。用于指定 CA 证书文件路径。",
                        "condition": {"dashboard.ssl.enable": True},
                    },
                    "log_file_enable": {
                        "description": "启用文件日志",
                        "type": "bool",
                        "hint": "开启后会将日志写入指定文件。",
                    },
                    "log_file_path": {
                        "description": "日志文件路径",
                        "type": "string",
                        "hint": "相对路径以 data 目录为基准，例如 logs/astrbot.log；支持绝对路径。",
                    },
                    "log_file_max_mb": {
                        "description": "日志文件大小上限 (MB)",
                        "type": "int",
                        "hint": "超过大小后自动轮转，默认 20MB。",
                    },
                    "temp_dir_max_size": {
                        "description": "临时目录大小上限 (MB)",
                        "type": "int",
                        "hint": "用于限制 data/temp 目录总大小，单位为 MB。系统每 10 分钟检查一次，超限时按文件修改时间从旧到新删除，释放约 30% 当前体积。",
                    },
                    "trace_log_enable": {
                        "description": "启用 Trace 文件日志",
                        "type": "bool",
                        "hint": "将 Trace 事件写入独立文件（不影响控制台输出）。",
                    },
                    "trace_log_path": {
                        "description": "Trace 日志文件路径",
                        "type": "string",
                        "hint": "相对路径以 data 目录为基准，例如 logs/astrbot.trace.log；支持绝对路径。",
                    },
                    "trace_log_max_mb": {
                        "description": "Trace 日志大小上限 (MB)",
                        "type": "int",
                        "hint": "超过大小后自动轮转，默认 20MB。",
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
                    "no_proxy": {
                        "description": "直连地址列表",
                        "type": "list",
                        "items": {"type": "string"},
                    },
                },
            },
        },
    },
}


DEFAULT_VALUE_MAP = {
    "int": 0,
    "float": 0.0,
    "bool": False,
    "string": "",
    "text": "",
    "list": [],
    "file": [],
    "object": {},
    "template_list": [],
}
