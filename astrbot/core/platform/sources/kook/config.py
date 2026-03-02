"""
KOOK适配器配置文件
包含连接参数、重连策略、心跳设置等配置项
"""

# 连接配置
CONNECTION_CONFIG = {
    # 心跳配置
    "heartbeat_interval": 30,  # 心跳间隔（秒）
    "heartbeat_timeout": 6,  # 心跳超时时间（秒）
    "max_heartbeat_failures": 3,  # 最大心跳失败次数
    # 重连配置
    "initial_reconnect_delay": 1,  # 初始重连延迟（秒）
    "max_reconnect_delay": 60,  # 最大重连延迟（秒）
    "max_consecutive_failures": 5,  # 最大连续失败次数
    # WebSocket配置
    "websocket_timeout": 10,  # WebSocket接收超时（秒）
    "connection_timeout": 30,  # 连接超时（秒）
    # 消息处理配置
    "enable_compression": True,  # 是否启用消息压缩
    "max_message_size": 1024 * 1024,  # 最大消息大小（字节）
}

# 日志配置
LOGGING_CONFIG = {
    "level": "INFO",  # 日志级别：DEBUG, INFO, WARNING, ERROR
    "format": "[KOOK] %(message)s",
    "enable_heartbeat_logs": False,  # 是否启用心跳日志
    "enable_message_logs": False,  # 是否启用消息日志
}

# 错误处理配置
ERROR_HANDLING_CONFIG = {
    "retry_on_network_error": True,  # 网络错误时是否重试
    "retry_on_token_expired": True,  # Token过期时是否重试
    "max_retry_attempts": 3,  # 最大重试次数
    "retry_delay_base": 2,  # 重试延迟基数（秒）
}

# 性能配置
PERFORMANCE_CONFIG = {
    "enable_message_buffering": True,  # 是否启用消息缓冲
    "buffer_size": 100,  # 缓冲区大小
    "enable_connection_pooling": True,  # 是否启用连接池
    "max_concurrent_requests": 10,  # 最大并发请求数
}

# 安全配置
SECURITY_CONFIG = {
    "verify_ssl": True,  # 是否验证SSL证书
    "enable_rate_limiting": True,  # 是否启用速率限制
    "rate_limit_requests": 100,  # 速率限制请求数
    "rate_limit_window": 60,  # 速率限制窗口（秒）
}


def get_config():
    """获取完整配置"""
    return {
        "connection": CONNECTION_CONFIG,
        "logging": LOGGING_CONFIG,
        "error_handling": ERROR_HANDLING_CONFIG,
        "performance": PERFORMANCE_CONFIG,
        "security": SECURITY_CONFIG,
    }


def get_connection_config():
    """获取连接配置"""
    return CONNECTION_CONFIG


def get_logging_config():
    """获取日志配置"""
    return LOGGING_CONFIG
