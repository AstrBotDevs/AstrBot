VERSION = '3.3.16'
DB_PATH = 'data/data_v2.db'

# 新版本配置文件，摈弃旧版本令人困惑的配置项 :D
DEFAULT_CONFIG_VERSION_2 = {
    "config_version": 2,
    "platform": [
        {
            "id": "default",
            "name": "qq_official",
            "enable": False,
            "appid": "",
            "secret": "",
            "enable_group_c2c": True,
            "enable_guild_direct_message": True,
        },
        {
            "id": "default",
            "name": "nakuru",
            "enable": False,
            "host": "172.0.0.1",
            "port": 5700,
            "websocket_port": 6700,
            "enable_group": True,
            "enable_guild": True,
            "enable_direct_message": True,
            "enable_group_increase": True,
        },
        {
            "id": "default",
            "name": "aiocqhttp",
            "enable": False,
            "ws_reverse_host": "",
            "ws_reverse_port": 6199,
        }
    ],
    "platform_settings": {
        "unique_session": False,
        "rate_limit": {
            "time": 60,
            "count": 30,
        },
        "reply_prefix": "",
        "forward_threshold": 200, # 转发消息的阈值
    },
    "llm": [
        {
            "id": "default",
            "name": "openai",
            "enable": True,
            "key": [],
            "api_base": "",
            "prompt_prefix": "",
            "default_personality": "",
            "model_config": {
                "model": "gpt-4o",
                "max_tokens": 6000,
                "temperature": 0.9,
                "top_p": 1,
                "frequency_penalty": 0,
                "presence_penalty": 0,
            },
            "image_generation_model_config": {
                "enable": True,
                "model": "dall-e-3",
                "size": "1024x1024",
                "style": "vivid",
                "quality": "standard",
            }
        },
    ],
    "llm_settings": {
        "wake_prefix": "",
        "web_search": False,
    },
    "content_safety": {
        "baidu_aip": {
            "enable": False,
            "app_id": "",
            "api_key": "",
            "secret_key": "",
        },
        "internal_keywords": {
            "enable": True,
            "extra_keywords": [],
        }
    },
    "wake_prefix": ["/"],
    "t2i": True,
    "dump_history_interval": 10,
    "admins_id": [],
    "https_proxy": "",
    "http_proxy": "",
    "dashboard": {
        "enable": True,
        "username": "",
        "password": "",
    },
    "log_level": "INFO",
    "t2i_endpoint": "",
}

# 这个是用于迁移旧版本配置文件的映射表
MAPPINGS_1_2 = [
    [["qqbot", "enable"], ["platform", 0, "enable"]],
    [["qqbot", "appid"], ["platform", 0, "appid"]],
    [["qqbot", "token"], ["platform", 0, "secret"]],
    [["qqofficial_enable_group_message"], ["platform", 0, "enable_group_c2c"]],
    [["direct_message_mode"], ["platform", 0, "enable_guild_direct_message"]],
    [["gocqbot", "enable"], ["platform", 1, "enable"]],
    [["gocq_host"], ["platform", 1, "host"]],
    [["gocq_http_port"], ["platform", 1, "port"]],
    [["gocq_websocket_port"], ["platform", 1, "websocket_port"]],
    [["gocq_react_group"], ["platform", 1, "enable_group"]],
    [["gocq_react_guild"], ["platform", 1, "enable_guild"]],
    [["gocq_react_friend"], ["platform", 1, "enable_direct_message"]],
    [["gocq_react_group_increase"], ["platform", 1, "enable_group_increase"]],
    [["aiocqhttp", "enable"], ["platform", 2, "enable"]],
    [["aiocqhttp", "ws_reverse_host"], ["platform", 2, "ws_reverse_host"]],
    [["aiocqhttp", "ws_reverse_port"], ["platform", 2, "ws_reverse_port"]],
    [["uniqueSessionMode"], ["platform_settings", "unique_session"]],
    [["limit", "time"], ["platform_settings", "rate_limit", "time"]],
    [["limit", "count"], ["platform_settings", "rate_limit", "count"]],
    [["reply_prefix"], ["platform_settings", "reply_prefix"]],
    [["qq_forward_threshold"], ["platform_settings", "forward_threshold"]],
    
    [["openai", "key"], ["llm", 0, "key"]],
    [["openai", "api_base"], ["llm", 0, "api_base"]],
    [["openai", "chatGPTConfigs", "model"], ["llm", 0, "model_config", "model"]],
    [["openai", "chatGPTConfigs", "max_tokens"], ["llm", 0, "model_config", "max_tokens"]],
    [["openai", "chatGPTConfigs", "temperature"], ["llm", 0, "model_config", "temperature"]],
    [["openai", "chatGPTConfigs", "top_p"], ["llm", 0, "model_config", "top_p"]],
    [["openai", "chatGPTConfigs", "frequency_penalty"], ["llm", 0, "model_config", "frequency_penalty"]],
    [["openai", "chatGPTConfigs", "presence_penalty"], ["llm", 0, "model_config", "presence_penalty"]],    
    
    [["default_personality_str"], ["llm", 0, "default_personality"]],
    [["llm_env_prompt"], ["llm", 0, "prompt_prefix"]],
    [["openai_image_generate", "model"], ["llm", 0, "image_generation_model_config", "model"]],
    [["openai_image_generate", "size"], ["llm", 0, "image_generation_model_config", "size"]],
    [["openai_image_generate", "style"], ["llm", 0, "image_generation_model_config", "style"]],
    [["openai_image_generate", "quality"], ["llm", 0, "image_generation_model_config", "quality"]],
    
    [["llm_wake_prefix"], ["llm_settings", "wake_prefix"]],
    
    [["baidu_aip", "enable"], ["content_safety", "baidu_aip", "enable"]],
    [["baidu_aip", "app_id"], ["content_safety", "baidu_aip", "app_id"]],
    [["baidu_aip", "api_key"], ["content_safety", "baidu_aip", "api_key"]],
    [["baidu_aip", "secret_key"], ["content_safety", "baidu_aip", "secret_key"]],
    
    [["qq_pic_mode"], ["t2i"]],
    [["dump_history_interval"], ["dump_history_interval"]],
    [["other_admins"], ["admins_id"]],
    [["http_proxy"], ["http_proxy"]],
    [["https_proxy"], ["https_proxy"]],
    [["dashboard_username"], ["dashboard", "username"]],
    [["dashboard_password"], ["dashboard", "password"]],
    [["nick_qq"], ["wake_prefix"]],
]

# 配置项的中文描述、值类型
CONFIG_METADATA_2 = {
    "config_version": {"description": "配置版本", "type": "int"},
    "platform": {
        "description": "平台配置",
        "type": "list",
        "items": {
            "name": {"description": "平台名称", "type": "string"},
            "enable": {"description": "启用", "type": "bool"},
            "appid": {"description": "appid", "type": "string"},
            "secret": {"description": "secret", "type": "string"},
            "enable_group_c2c": {"description": "启用消息列表单聊", "type": "bool"},
            "enable_guild_direct_message": {"description": "启用频道私聊", "type": "bool"},
            "host": {"description": "主机地址", "type": "string"},
            "port": {"description": "端口", "type": "int"},
            "websocket_port": {"description": "Websocket 端口", "type": "int"},
            "ws_reverse_host": {"description": "反向 Websocket 主机地址", "type": "string"},
            "ws_reverse_port": {"description": "反向 Websocket 端口", "type": "int"},
            "enable_group": {"description": "接收群组消息", "type": "bool"},
            "enable_guild": {"description": "接收频道消息", "type": "bool"},
            "enable_direct_message": {"description": "接收频道私聊", "type": "bool"},
            "enable_group_increase": {"description": "接收群组成员增加事件", "type": "bool"},
        }
    },
    "platform_settings": {
        "description": "平台设置",
        "type": "object",
        "items": {
            "unique_session": {"description": "会话隔离到单个人", "type": "bool"},
            "rate_limit": {
                "description": "速率限制",
                "type": "object",
                "items": {
                    "time": {"description": "消息速率限制时间", "type": "int"},
                    "count": {"description": "消息速率限制计数", "type": "int"},
                }
            },
            "reply_prefix": {"description": "回复前缀", "type": "string"},
            "forward_threshold": {"description": "转发消息的字数阈值", "type": "int"},
        }
    },
    "llm": {
        "description": "大语言模型配置",
        "type": "list",
        "items": {
            "name": {"description": "模型名称", "type": "string"},
            "enable": {"description": "启用", "type": "bool"},
            "key": {"description": "API Key", "type": "list", "items": {"type": "string"}},
            "api_base": {"description": "API Base URL", "type": "string"},
            "prompt_prefix": {"description": "Prompt 前缀", "type": "string"},
            "default_personality": {"description": "默认人格", "type": "string"},
            "model_config": {
                "description": "模型配置",
                "type": "object",
                "items": {
                    "model": {"description": "模型名称", "type": "string"},
                    "max_tokens": {"description": "最大令牌数", "type": "int"},
                    "temperature": {"description": "温度", "type": "float"},
                    "top_p": {"description": "Top P值", "type": "float"},
                    "frequency_penalty": {"description": "频率惩罚", "type": "float"},
                    "presence_penalty": {"description": "存在惩罚", "type": "float"},
                }
            },
            "image_generation_model_config": {
                "description": "图像生成模型配置",
                "type": "object",
                "items": {
                    "enable": {"description": "启用(需要该提供商支持图像生成模型)", "type": "bool"},
                    "model": {"description": "模型名称", "type": "string"},
                    "size": {"description": "图像尺寸", "type": "string"},
                    "style": {"description": "图像风格", "type": "string"},
                    "quality": {"description": "图像质量", "type": "string"},
                }
            },
        }
    },
    "llm_settings": {
        "description": "大语言模型设置",
        "type": "object",
        "items": {
            "wake_prefix": {"description": "LLM 聊天额外唤醒前缀", "type": "string"},
            "web_search": {"description": "启用网页搜索(能访问 Google 时效果最佳)", "type": "bool"},
        }
    },
    "content_safety": {
        "description": "内容安全",
        "type": "object",
        "items": {
            "baidu_aip": {
                "description": "百度内容审核配置",
                "type": "object",
                "items": {
                    "enable": {"description": "启用百度内容审核(需手动安装 baidu-aip 库)", "type": "bool"},
                    "app_id": {"description": "APP ID", "type": "string"},
                    "api_key": {"description": "API Key", "type": "string"},
                    "secret_key": {"description": "Secret Key", "type": "string"},
                }
            },
            "internal_keywords": {
                "description": "内部关键词过滤",
                "type": "object",
                "items": {
                    "enable": {"description": "启用内部关键词过滤", "type": "bool"},
                    "extra_keywords": {"description": "额外关键词(支持正则)", "type": "list", "items": {"type": "string"}},
                }
            }
        }
    },
    "wake_prefix": {"description": "唤醒前缀列表", "type": "list", "items": {"type": "string"}},
    "t2i": {"description": "文本转图像功能", "type": "bool"},
    "dump_history_interval": {"description": "历史记录转储间隔", "type": "int"},
    "admins_id": {"description": "管理员ID列表", "type": "list", "items": {"type": "int"}},
    "https_proxy": {"description": "HTTPS代理", "type": "string"},
    "http_proxy": {"description": "HTTP代理", "type": "string"},
    "dashboard": {
        "description": "仪表盘配置",
        "type": "object",
        "items": {
            "enable": {"description": "启用", "type": "bool"},
            "username": {"description": "用户名", "type": "string"},
            "password": {"description": "密码", "type": "string"},
        }
    },
    "log_level": {"description": "控制台日志级别(DEBUG, INFO, WARNING, ERROR)", "type": "string"},
    "t2i_endpoint": {"description": "文本转图像服务接口(为空时使用公共服务器)", "type": "string"},
}
