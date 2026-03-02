import json
from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class KookConfig:
    """KOOK 适配器配置类"""

    # 基础配置
    token: str
    enable: bool = False
    id: str = "kook"

    # 重连配置
    reconnect_delay: int = 1
    """重连延迟基数(秒)，指数退避"""
    max_reconnect_delay: int = 60
    """最大重连延迟(秒)"""
    max_retry_delay: int = 60
    """最大重试延迟(秒)"""

    # 心跳配置
    heartbeat_interval: int = 30
    """心跳间隔(秒)"""
    heartbeat_timeout: int = 6
    """心跳超时时间(秒)"""
    max_heartbeat_failures: int = 3
    """最大心跳失败次数"""

    # 失败处理
    max_consecutive_failures: int = 5
    """最大连续失败次数"""

    @classmethod
    def from_dict(cls, config_dict: dict) -> "KookConfig":
        """从字典创建配置对象"""
        return cls(
            # 适配器id 应该是不能改的
            # id=config_dict.get("id", "kook"),
            enable=config_dict.get("enable", False),
            token=config_dict.get("kook_bot_token", ""),
            reconnect_delay=config_dict.get(
                "kook_reconnect_delay",
            )
            or KookConfig.reconnect_delay,
            max_reconnect_delay=config_dict.get(
                "kook_max_reconnect_delay",
            )
            or KookConfig.max_reconnect_delay,
            max_retry_delay=config_dict.get(
                "kook_max_retry_delay",
            )
            or KookConfig.max_retry_delay,
            heartbeat_interval=config_dict.get(
                "kook_heartbeat_interval",
            )
            or KookConfig.heartbeat_interval,
            heartbeat_timeout=config_dict.get(
                "kook_heartbeat_timeout",
            )
            or KookConfig.heartbeat_timeout,
            max_heartbeat_failures=config_dict.get(
                "kook_max_heartbeat_failures",
            )
            or KookConfig.max_heartbeat_failures,
            max_consecutive_failures=config_dict.get(
                "kook_max_consecutive_failures",
            )
            or KookConfig.max_consecutive_failures,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def pretty_jsons(self, indent=2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


# TODO 没用上的config配置,未来有空会实现这些配置描述的功能?
# # 连接配置
# CONNECTION_CONFIG = {
#     # 心跳配置
#     "heartbeat_interval": 30,  # 心跳间隔（秒）
#     "heartbeat_timeout": 6,  # 心跳超时时间（秒）
#     "max_heartbeat_failures": 3,  # 最大心跳失败次数
#     # 重连配置
#     "initial_reconnect_delay": 1,  # 初始重连延迟（秒）
#     "max_reconnect_delay": 60,  # 最大重连延迟（秒）
#     "max_consecutive_failures": 5,  # 最大连续失败次数
#     # WebSocket配置
#     "websocket_timeout": 10,  # WebSocket接收超时（秒）
#     "connection_timeout": 30,  # 连接超时（秒）
#     # 消息处理配置
#     "enable_compression": True,  # 是否启用消息压缩
#     "max_message_size": 1024 * 1024,  # 最大消息大小（字节）
# }

# # 日志配置
# LOGGING_CONFIG = {
#     "level": "INFO",  # 日志级别：DEBUG, INFO, WARNING, ERROR
#     "format": "[KOOK] %(message)s",
#     "enable_heartbeat_logs": False,  # 是否启用心跳日志
#     "enable_message_logs": False,  # 是否启用消息日志
# }

# # 错误处理配置
# ERROR_HANDLING_CONFIG = {
#     "retry_on_network_error": True,  # 网络错误时是否重试
#     "retry_on_token_expired": True,  # Token过期时是否重试
#     "max_retry_attempts": 3,  # 最大重试次数
#     "retry_delay_base": 2,  # 重试延迟基数（秒）
# }

# # 性能配置
# PERFORMANCE_CONFIG = {
#     "enable_message_buffering": True,  # 是否启用消息缓冲
#     "buffer_size": 100,  # 缓冲区大小
#     "enable_connection_pooling": True,  # 是否启用连接池
#     "max_concurrent_requests": 10,  # 最大并发请求数
# }

# # 安全配置
# SECURITY_CONFIG = {
#     "verify_ssl": True,  # 是否验证SSL证书
#     "enable_rate_limiting": True,  # 是否启用速率限制
#     "rate_limit_requests": 100,  # 速率限制请求数
#     "rate_limit_window": 60,  # 速率限制窗口（秒）
# }
