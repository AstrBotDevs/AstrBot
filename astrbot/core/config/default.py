"""
如需修改配置，请在 `data/cmd_config.json` 中修改或者在管理面板中可视化修改。
"""

VERSION = "3.4.6"
DB_PATH = "data/data_v3.db"

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
        "forward_threshold": 200,
        "enable_id_white_list": True,
        "id_whitelist": [],
        "id_whitelist_log": True,
        "wl_ignore_admin_on_group": True,
        "wl_ignore_admin_on_friend": True,
    },
    "provider": [],
    "provider_settings": {
        "enable": True,
        "wake_prefix": "",
        "web_search": False,
        "identifier": False,
        "datetime_system_prompt": True,
        "default_personality": "default",
        "prompt_prefix": "",
    },
    "provider_stt_settings": {
      "enable": False,
      "provider_id": "",  
    },
    "content_safety": {
        "internal_keywords": {"enable": True, "extra_keywords": []},
        "baidu_aip": {"enable": False, "app_id": "", "api_key": "", "secret_key": ""},
    },
    "admins_id": [],
    "t2i": False,
    "http_proxy": "",
    "dashboard": {
        "enable": True,
        "username": "astrbot",
        "password": "77b90590a8945a7d36c963981a307dc9",
    },
    "platform": [],
    "wake_prefix": ["/"],
    "log_level": "INFO",
    "t2i_endpoint": "",
    "pip_install_arg": "",
    "plugin_repo_mirror": "",
    "knowledge_db": {},
    "persona": [
        {
            "name": "default",
            "prompt": "如果用户寻求帮助或者打招呼，请告诉他可以用 /help 查看 AstrBot 帮助。",
            "begin_dialogs": [],
            "mood_imitation_dialogs": []
        }
    ]
}


# 配置项的中文描述、值类型
CONFIG_METADATA_2 = {
    "platform_group": {
        "name": "消息平台",
        "metadata": {
            "platform": {
                "description": "消息平台适配器",
                "type": "list",
                "config_template": {
                    "qq_official(QQ)": {
                        "id": "default",
                        "type": "qq_official",
                        "enable": False,
                        "appid": "",
                        "secret": "",
                        "enable_group_c2c": True,
                        "enable_guild_direct_message": True,
                    },
                    "aiocqhtp(QQ)": {
                        "id": "default",
                        "type": "aiocqhttp",
                        "enable": False,
                        "ws_reverse_host": "",
                        "ws_reverse_port": 6199,
                    },
                    "vchat(微信)": {"id": "default", "type": "vchat", "enable": False},
                },
                "items": {
                    "id": {
                        "description": "ID",
                        "type": "string",
                        "hint": "提供商 ID 名，用于在多实例下方便管理和识别。自定义，ID 不能重复。",
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
                        "hint": "必填项。QQ 官方机器人平台的 secret。如何获取请参考文档。",
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
                        "description": "反向 Websocket 主机地址",
                        "type": "string",
                        "hint": "aiocqhttp 适配器的反向 Websocket 服务器 IP 地址，不包含端口号。",
                    },
                    "ws_reverse_port": {
                        "description": "反向 Websocket 端口",
                        "type": "int",
                        "hint": "aiocqhttp 适配器的反向 Websocket 端口。",
                    },
                },
            },
            "platform_settings": {
                "description": "平台设置",
                "type": "object",
                "items": {
                    "unique_session": {
                        "description": "会话隔离",
                        "type": "bool",
                        "hint": "启用后，在群组或者频道中，每个人的消息上下文都是独立的。",
                    },
                    "rate_limit": {
                        "description": "速率限制",
                        "hint": "每个会话在 `time` 秒内最多只能发送 `count` 条消息。",
                        "type": "object",
                        "items": {
                            "time": {"description": "消息速率限制时间", "type": "int"},
                            "count": {"description": "消息速率限制计数", "type": "int"},
                            "strategy": {
                                "description": "速率限制策略",
                                "type": "string",
                                "options": ["stall", "discard"],
                                "hint": "当消息速率超过限制时的处理策略。stall 为等待，discard 为丢弃。",
                            },
                        },
                    },
                    "reply_prefix": {
                        "description": "回复前缀",
                        "type": "string",
                        "hint": "机器人回复消息时带有的前缀。",
                    },
                    "forward_threshold": {
                        "description": "转发消息的字数阈值",
                        "type": "int",
                        "hint": "超过一定字数后，机器人会将消息折叠成 QQ 群聊的 “转发消息”，以防止刷屏。目前仅 QQ 平台适配器适用。",
                    },
                    "enable_id_white_list": {
                        "description": "启用 ID 白名单",
                        "type": "bool"
                    },
                    "id_whitelist": {
                        "description": "ID 白名单",
                        "type": "list",
                        "items": {"type": "int"},
                        "hint": "填写后，将只处理所填写的 ID 发来的消息事件。为空时表示不启用白名单过滤。可以使用 /myid 指令获取在某个平台上的会话 ID。也可在 AstrBot 日志内获取会话 ID，当一条消息没通过白名单时，会输出 INFO 级别的日志。会话 ID 类似 aiocqhttp:GroupMessage:547540978",
                    },
                    "id_whitelist_log": {
                        "description": "打印白名单日志",
                        "type": "bool",
                        "hint": "启用后，当一条消息没通过白名单时，会输出 INFO 级别的日志。",
                    },
                    "wl_ignore_admin_on_group": {
                        "description": "管理员群组消息无视 ID 白名单",
                        "type": "bool",
                    },
                    "wl_ignore_admin_on_friend": {
                        "description": "管理员私聊消息无视 ID 白名单",
                        "type": "bool",
                    },
                },
            },
            "content_safety": {
                "description": "内容安全",
                "type": "object",
                "items": {
                    "baidu_aip": {
                        "description": "百度内容审核配置",
                        "type": "object",
                        "items": {
                            "enable": {
                                "description": "启用百度内容审核",
                                "type": "bool",
                                "hint": "启用此功能前，您需要手动在设备中安装 baidu-aip 库。一般来说，安装指令如下: `pip3 install baidu-aip`",
                            },
                            "app_id": {"description": "APP ID", "type": "string"},
                            "api_key": {"description": "API Key", "type": "string"},
                            "secret_key": {
                                "description": "Secret Key",
                                "type": "string",
                            },
                        },
                    },
                    "internal_keywords": {
                        "description": "内部关键词过滤",
                        "type": "object",
                        "items": {
                            "enable": {
                                "description": "启用内部关键词过滤",
                                "type": "bool",
                            },
                            "extra_keywords": {
                                "description": "额外关键词",
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
                "description": "服务提供商配置",
                "type": "list",
                "config_template": {
                    "openai": {
                        "id": "default",
                        "type": "openai_chat_completion",
                        "enable": True,
                        "key": [],
                        "api_base": "",
                        "model_config": {
                            "model": "gpt-4o-mini",
                        },
                    },
                    "ollama": {
                        "id": "ollama_default",
                        "type": "openai_chat_completion",
                        "enable": True,
                        "key": ["ollama"],  # ollama 的 key 默认是 ollama
                        "api_base": "http://localhost:11434",
                        "model_config": {
                            "model": "llama3.1-8b",
                        },
                    },
                    "gemini(OpenAI兼容)": {
                        "id": "gemini_default",
                        "type": "openai_chat_completion",
                        "enable": True,
                        "key": [],
                        "api_base": "https://generativelanguage.googleapis.com/v1beta/openai/",
                        "model_config": {
                            "model": "gemini-1.5-flash",
                        },
                    },
                    "gemini(googlegenai原生)": {
                        "id": "gemini_default",
                        "type": "googlegenai_chat_completion",
                        "enable": True,
                        "key": [],
                        "api_base": "https://generativelanguage.googleapis.com/",
                        "model_config": {
                            "model": "gemini-1.5-flash",
                        },
                    },
                    "deepseek": {
                        "id": "deepseek_default",
                        "type": "openai_chat_completion",
                        "enable": True,
                        "key": [],
                        "api_base": "https://api.deepseek.com/v1",
                        "model_config": {
                            "model": "deepseek-chat",
                        },
                    },
                    "zhipu": {
                        "id": "zhipu_default",
                        "type": "zhipu_chat_completion",
                        "enable": True,
                        "key": [],
                        "api_base": "https://open.bigmodel.cn/api/paas/v4/",
                        "model_config": {
                            "model": "glm-4-flash",
                        },
                    },
                    "llmtuner": {
                        "id": "llmtuner_default",
                        "type": "llm_tuner",
                        "enable": True,
                        "base_model_path": "",
                        "adapter_model_path": "",
                        "llmtuner_template": "",
                        "finetuning_type": "lora",
                        "quantization_bit": 4,
                    },
                    "dify": {
                        "id": "dify_app_default",
                        "type": "dify",
                        "enable": True,
                        "dify_api_type": "chat",
                        "dify_api_key": "",
                        "dify_api_base": "https://api.dify.ai/v1",
                        "dify_workflow_output_key": "",
                    },
                    "whisper(API)": {
                        "id": "whisper",
                        "type": "openai_whisper_api",
                        "enable": False,
                        "api_key": "",
                        "api_base": "",
                        "model": "whisper-1",
                    },
                    "whisper(本地加载)": {
                        "whisper_hint": "(不用修改我)",
                        "enable": False,
                        "id": "whisper",
                        "type": "openai_whisper_selfhost",
                        "model": "tiny",
                    }
                },
                "items": {
                    "whisper_hint": {
                        "description": "本地部署 Whisper 模型须知",
                        "type": "string",
                        "hint": "启用前请 pip 安装 openai-whisper 库（N卡用户大约下载 2GB，主要是 torch 和 cuda，CPU 用户大约下载 1 GB），并且安装 ffmpeg。否则将无法正常转文字。",
                        "obvious_hint": True
                    },
                    "id": {
                        "description": "ID",
                        "type": "string",
                        "hint": "提供商 ID 名，用于在多实例下方便管理和识别。自定义，ID 不能重复。",
                    },
                    "type": {
                        "description": "模型提供商类型",
                        "type": "string",
                        "invisible": True,
                    },
                    "enable": {
                        "description": "启用",
                        "type": "bool",
                        "hint": "是否启用该模型。未启用的模型将不会被使用。",
                    },
                    "key": {
                        "description": "API Key",
                        "type": "list",
                        "items": {"type": "string"},
                        "hint": "API Key 列表。填写好后输入回车即可添加 API Key。支持多个 API Key。",
                    },
                    "api_base": {
                        "description": "API Base URL",
                        "type": "string",
                        "hint": "API Base URL 请在在模型提供商处获得。支持 Ollama 开放的 API 地址。如果您确认填写正确但是使用时出现了 404 异常，可以尝试在地址末尾加上 `/v1`。",
                    },
                    "base_model_path": {
                        "description": "基座模型路径",
                        "type": "string",
                        "hint": "基座模型路径。",
                    },
                    "adapter_model_path": {
                        "description": "Adapter 模型路径",
                        "type": "string",
                        "hint": "Adapter 模型路径。如 Lora",
                    },
                    "llmtuner_template": {
                        "description": "template",
                        "type": "string",
                        "hint": "基座模型的类型。如 llama3, qwen, 请参考 LlamaFactory 文档。",
                    },
                    "finetuning_type": {
                        "description": "微调类型",
                        "type": "string",
                        "hint": "微调类型。如 `lora`",
                    },
                    "quantization_bit": {
                        "description": "量化位数",
                        "type": "int",
                        "hint": "量化位数。如 4",
                    },
                    "model_config": {
                        "description": "文本生成模型",
                        "type": "object",
                        "items": {
                            "model": {
                                "description": "模型名称",
                                "type": "string",
                                "hint": "大语言模型的名称，一般是小写的英文。如 gpt-4o-mini, deepseek-chat 等。",
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
                        "hint": "Dify API 类型。根据 Dify 官网，目前支持 chat, agent, workflow 三种应用类型",
                        "options": ["chat", "agent", "workflow"],
                    },
                    "dify_workflow_output_key": {
                        "description": "Dify Workflow 输出变量名",
                        "type": "string",
                        "hint": "Dify Workflow 输出变量名。当应用类型为 workflow 时才使用。默认为 astrbot_wf_output。",
                    }
                },
            },
            "provider_settings": {
                "description": "大语言模型设置",
                "type": "object",
                "items": {
                    "enable": {
                        "description": "启用大语言模型聊天",
                        "type": "bool",
                        "hint": "如需切换大语言模型提供商，请使用 `/provider` 命令。",
                        "obvious_hint": True
                    },
                    "wake_prefix": {
                        "description": "LLM 聊天额外唤醒前缀",
                        "type": "string",
                        "hint": "使用 LLM 聊天额外的触发条件。如填写 `chat`，则需要消息前缀加上 `/chat` 才能触发 LLM 聊天，是一个防止滥用的手段。",
                    },
                    "web_search": {
                        "description": "启用网页搜索",
                        "type": "bool",
                        "hint": "能访问 Google 时效果最佳。如果 Google 访问失败，程序会依次访问 Bing, Sogo 搜索引擎。",
                    },
                    "identifier": {
                        "description": "启动识别群员",
                        "type": "bool",
                        "hint": "在 Prompt 前加上群成员的名字以让模型更好地了解群聊状态。启用将略微增加 token 开销。",
                    },
                    "datetime_system_prompt": {
                        "description": "启用日期时间系统提示",
                        "type": "bool",
                        "hint": "启用后，会在系统提示词中加上当前机器的日期时间。",
                    },
                    "default_personality": {
                        "description": "默认采用的人格情景的名称",
                        "type": "string",
                        "hint": "",
                    },
                    "prompt_prefix": {
                        "description": "Prompt 前缀文本",
                        "type": "string",
                        "hint": "添加之后，会在每次对话的 Prompt 前加上此文本。",
                    },
                },
            },
            "persona": {
                "description": "人格情景设置",
                "type": "list",
                "config_template": {
                    "新人格情景": {
                        "name": "",
                        "prompt": "",
                        "begin_dialogs": [],
                        "mood_imitation_dialogs": []
                    }
                },
                "tmpl_display_title": "name",
                "items": {
                    "name": {
                        "description": "人格名称",
                        "type": "string",
                        "hint": "人格名称，用于在多个人格中区分。",
                    },
                    "prompt": {
                        "description": "设定(系统提示词)",
                        "type": "text",
                        "hint": "填写人格的身份背景、性格特征、兴趣爱好、个人经历、口头禅等。",
                    },
                    "begin_dialogs": {
                        "description": "预设对话",
                        "type": "list",
                        "items": {},
                        "hint": "可选。在每个对话前会插入这些预设对话。格式要求：按照用户、助手...的格式。即第一句为用户，第二句为助手，以此类推。",
                        "obvious_hint": True
                    },
                    "mood_imitation_dialogs": {
                        "description": "对话风格模仿",
                        "type": "list",
                        "items": {},
                        "hint": "旨在让模型尽可能模仿学习到所填写的对话的语气风格。格式和 `预设对话` 一样。",
                        "obvious_hint": True
                    },
                }
            },
            
            "provider_stt_settings": {
                "description": "语音转文本(STT)",
                "type": "object",
                "items": {
                    "enable": {
                        "description": "启用语音转文本(STT)",
                        "type": "bool",
                        "hint": "启用前请在 服务提供商配置 处创建支持 语音转文本任务 的提供商。如 whisper。",
                        "obvious_hint": True
                    },
                    "provider_id": {
                        "description": "提供商 ID，不填则默认第一个STT提供商",
                        "type": "string",
                        "hint": "语音转文本提供商 ID。如果不填写将使用载入的第一个提供商。",
                    },
                },
            },
        },
    },
    "misc_config_group": {
        "name": "其他配置",
        "metadata": {
            "wake_prefix": {
                "description": "机器人唤醒前缀",
                "type": "list",
                "items": {"type": "string"},
                "hint": "在不 @ 机器人的情况下，可以通过外加消息前缀来唤醒机器人。",
            },
            "t2i": {
                "description": "文本转图像",
                "type": "bool",
                "hint": "启用后，超出一定长度的文本将会通过 AstrBot API 渲染成 Markdown 图片发送。可以缓解审核和消息过长刷屏的问题，并提高 Markdown 文本的可读性。",
            },
            "admins_id": {
                "description": "管理员 ID",
                "type": "list",
                "items": {"type": "int"},
                "hint": "管理员 ID 列表，管理员可以使用一些特权命令，如 `update`, `plugin` 等。ID 可以通过 `/myid` 指令获得。回车添加，可添加多个。",
            },
            "http_proxy": {
                "description": "HTTP 代理",
                "type": "string",
                "hint": "启用后，会以添加环境变量的方式设置代理。格式为 `http://ip:port`",
            },
            "log_level": {
                "description": "控制台日志级别",
                "type": "string",
                "hint": "控制台输出日志的级别。",
                "options": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
            },
            "t2i_endpoint": {
                "description": "文本转图像服务接口",
                "type": "string",
                "hint": "为空时使用 AstrBot API 服务",
            },
            "pip_install_arg": {
                "description": "pip 安装参数",
                "type": "string",
                "hint": "安装插件依赖时，会使用 Python 的 pip 工具。这里可以填写额外的参数，如 `--break-system-package` 等。",
            },
            "plugin_repo_mirror": {
                "description": "插件仓库镜像",
                "type": "string",
                "hint": "插件仓库的镜像地址，用于加速插件的下载。",
                "options": [
                    "default",
                    "https://ghp.ci/",
                    "https://github-mirror.us.kg/",
                ],
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
    "object": {},
}


# "project_atri": {
#     "description": "Project ATRI 配置",
#     "type": "object",
#     "items": {
#         "enable": {"description": "启用", "type": "bool"},
#         "long_term_memory": {
#             "description": "长期记忆",
#             "type": "object",
#             "items": {
#                 "enable": {"description": "启用", "type": "bool"},
#                 "summary_threshold_cnt": {
#                     "description": "摘要阈值",
#                     "type": "int",
#                     "hint": "当一个会话的对话记录数量超过该阈值时，会自动进行摘要。",
#                 },
#                 "embedding_provider_id": {
#                     "description": "Embedding provider ID",
#                     "type": "string",
#                     "hint": "只有当启用了长期记忆时，才需要填写此项。将会使用指定的 provider 来获取 Embedding，请确保所填的 provider id 在 `配置页` 中存在并且设置了 Embedding 配置",
#                     "obvious_hint": True,
#                 },
#                 "summarize_provider_id": {
#                     "description": "Summary provider ID",
#                     "type": "string",
#                     "hint": "只有当启用了长期记忆时，才需要填写此项。将会使用指定的 provider 来获取 Summary，请确保所填的 provider id 在 `配置页` 中存在。",
#                     "obvious_hint": True,
#                 },
#             },
#         },
#         "active_message": {
#             "description": "主动消息",
#             "type": "object",
#             "items": {
#                 "enable": {"description": "启用", "type": "bool"},
#             },
#         },
#         "vision": {
#             "description": "视觉理解",
#             "type": "object",
#             "items": {
#                 "enable": {"description": "启用", "type": "bool"},
#                 "provider_id_or_ofa_model_path": {
#                     "description": "提供商 ID 或 OFA 模型路径",
#                     "type": "string",
#                     "hint": "将会使用指定的 provider 来进行视觉处理，请确保所填的 provider id 在 `配置页` 中存在。",
#                 },
#             },
#         },
#         "split_response": {
#             "description": "是否分割回复",
#             "type": "bool",
#             "hint": "启用后，将会根据句子分割回复以更像人类回复。每次回复之间具有随机的时间间隔。默认启用。",
#         },
#         "persona": {
#             "description": "人格",
#             "type": "string",
#             "hint": "默认人格。当启动 ATRI 之后，在 Provider 处设置的人格将会失效。",
#             "obvious_hint": True,
#         },
#         "chat_provider_id": {
#             "description": "Chat provider ID",
#             "type": "string",
#             "hint": "将会使用指定的 provider 来进行文本聊天，请确保所填的 provider id 在 `配置页` 中存在。",
#             "obvious_hint": True,
#         },
#         "chat_base_model_path": {
#             "description": "用于聊天的基座模型路径",
#             "type": "string",
#             "hint": "用于聊天的基座模型路径。当填写此项和 Lora 路径后，将会忽略上面设置的 Chat provider ID。",
#             "obvious_hint": True,
#         },
#         "chat_adapter_model_path": {
#             "description": "用于聊天的 Lora 模型路径",
#             "type": "string",
#             "hint": "Lora 模型路径。",
#             "obvious_hint": True,
#         },
#         "quantization_bit": {
#             "description": "量化位数",
#             "type": "int",
#             "hint": "模型量化位数。如果你不知道这是什么，请不要修改。默认为 4。",
#             "obvious_hint": True,
#         },
#     },
# },
