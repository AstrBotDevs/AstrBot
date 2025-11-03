from enum import Enum


class PluginType(Enum):
    """插件大类."""
    # 兼容保留
    LEGACY = "legacy"  # 经典插件，直接在主进程中运行 -- 逐渐淘汰

    # 后两者为新插件机制
    STDIO = "stdio"  # 子进程 -- 进程间通信
    WEB = "web"  # 通过 HTTP/HTTPS 协议调用
