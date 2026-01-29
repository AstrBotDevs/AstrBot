"""平台适配器相关的默认配置"""

# 平台默认配置
PLATFORMS_DEFAULT_CONFIG = {
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
    "persona": [],  # deprecated
}

# 平台配置的键列表（用于迁移检测）
PLATFORMS_CONFIG_KEYS = [
    "platform",
    "platform_specific",
    "persona",
]
