"""
astrbot.api.star.register
该模块包括所有插件注册相关模块, 注册各种 Handler 等等
"""

# 注册插件
from astrbot.core.star.register import (
    register_star as register,
)

# 注册 Handler
"""
注解:
- 监听器: 监听的对象是事件, 根据选择的特定类型, 将事件交由该 Handler 处理
- 触发器: 在消息处理流水线中的某个时机触发, 此时流水线将执行注册的 Handler
"""
from astrbot.core.star.register import (
    register_command as command,  # 注册命令
    register_command_group as command_group,  # 注册命令组
    register_event_message_type as event_message_type,  # 注册监听器: 事件消息类型
    register_regex as regex,  # 注册监听器: 正则表达式
    register_platform_adapter_type as platform_adapter_type,  # 注册监听器: 平台适配器类型
    register_permission_type as permission_type,  # 注册监听器: 权限类型
    register_custom_filter as custom_filter,  # 注册监听器: 自定义过滤器
    register_on_astrbot_loaded as on_astrbot_loaded,  # 注册触发器: AstrBot 加载完成时
    register_on_llm_request as on_llm_request,  # 注册触发器: LLM 请求时
    register_on_llm_response as on_llm_response,  # 注册触发器: LLM 响应时
    register_on_decorating_result as on_decorating_result,  # 注册触发器: 装饰结果时
    register_after_message_sent as after_message_sent,  # 注册触发器: 消息发送后
    register_llm_tool as llm_tool,  # 注册 LLM 工具
)

# 监听器所用到的过滤器和类型
from astrbot.core.star.filter.event_message_type import (
    EventMessageTypeFilter,
    EventMessageType,
)
from astrbot.core.star.filter.platform_adapter_type import (
    PlatformAdapterTypeFilter,
    PlatformAdapterType,
)
from astrbot.core.star.filter.permission import PermissionTypeFilter, PermissionType
from astrbot.core.star.filter.custom_filter import CustomFilter

# 注册平台适配器
from astrbot.core.provider.register import register_provider_adapter

__all__ = [
    "register",
    "command",
    "command_group",
    "event_message_type",
    "regex",
    "platform_adapter_type",
    "permission_type",
    "custom_filter",
    "on_astrbot_loaded",
    "on_llm_request",
    "on_llm_response",
    "on_decorating_result",
    "after_message_sent",
    "llm_tool",
    "EventMessageTypeFilter",
    "EventMessageType",
    "PlatformAdapterTypeFilter",
    "PlatformAdapterType",
    "PermissionTypeFilter",
    "PermissionType",
    "CustomFilter",
    "register_provider_adapter",
]
