# =============================================================================
# 新旧对比 - decorators.py
# =============================================================================
#
# 【旧版 src/astrbot_sdk/api/event/filter.py】
# 导出的装饰器和类型:
# - 装饰器: command, regex, custom_filter, event_message_type, permission_type,
#          platform_adapter_type, after_message_sent, on_astrbot_loaded,
#          on_platform_loaded, on_decorating_result, on_llm_request, on_llm_response,
#          command_group, llm_tool (注释掉)
# - 类型: CustomFilter, EventMessageType, EventMessageTypeFilter,
#         PermissionType, PermissionTypeFilter, PlatformAdapterType, PlatformAdapterTypeFilter
#
# 【新版 src-new/astrbot_sdk/decorators.py】
# 提供的装饰器:
# - on_command, on_message, on_event, on_schedule, require_admin
# - 内部类型: HandlerMeta, HandlerCallable
#
# =============================================================================
# TODO: 功能缺失
# =============================================================================
#
# 1. 缺少装饰器
#    - custom_filter: 自定义过滤器装饰器
#    - event_message_type: 消息类型过滤器
#    - permission_type: 权限类型过滤器 (有 require_admin 但更通用)
#    - platform_adapter_type: 平台适配器类型过滤器
#    - after_message_sent: 消息发送后钩子
#    - on_astrbot_loaded: AstrBot 加载完成钩子
#    - on_platform_loaded: 平台加载完成钩子
#    - on_decorating_result: 结果装饰钩子
#    - on_llm_request: LLM 请求钩子
#    - on_llm_response: LLM 响应钩子
#    - command_group: 命令组装饰器
#    - llm_tool: LLM 工具装饰器 (旧版已注释)
#
# 2. 缺少类型定义
#    - CustomFilter: 自定义过滤器基类
#    - EventMessageType: 消息类型枚举
#    - EventMessageTypeFilter: 消息类型过滤器
#    - PermissionType: 权限类型枚举
#    - PermissionTypeFilter: 权限类型过滤器
#    - PlatformAdapterType: 平台适配器类型枚举
#    - PlatformAdapterTypeFilter: 平台适配器类型过滤器
#
# 3. 命名差异
#    - 旧版 command -> 新版 on_command
#    - 旧版 regex -> 新版 on_message(regex=...)
#    - 新版 on_message 支持关键词和平台过滤
#
# 4. 新增功能
#    - on_schedule: 定时任务装饰器 (旧版无)
#    - require_admin: 管理员权限快捷装饰器 (旧版用 permission_type)
#
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .protocol.descriptors import (
    CommandTrigger,
    EventTrigger,
    MessageTrigger,
    Permissions,
    ScheduleTrigger,
)

HandlerCallable = Callable[..., Any]
HANDLER_META_ATTR = "__astrbot_handler_meta__"


@dataclass(slots=True)
class HandlerMeta:
    trigger: CommandTrigger | MessageTrigger | EventTrigger | ScheduleTrigger | None = (
        None
    )
    priority: int = 0
    permissions: Permissions = field(default_factory=Permissions)


def _get_or_create_meta(func: HandlerCallable) -> HandlerMeta:
    meta = getattr(func, HANDLER_META_ATTR, None)
    if meta is None:
        meta = HandlerMeta()
        setattr(func, HANDLER_META_ATTR, meta)
    return meta


def get_handler_meta(func: HandlerCallable) -> HandlerMeta | None:
    return getattr(func, HANDLER_META_ATTR, None)


def on_command(
    command: str,
    *,
    aliases: list[str] | None = None,
    description: str | None = None,
) -> Callable[[HandlerCallable], HandlerCallable]:
    def decorator(func: HandlerCallable) -> HandlerCallable:
        meta = _get_or_create_meta(func)
        meta.trigger = CommandTrigger(
            command=command,
            aliases=aliases or [],
            description=description,
        )
        return func

    return decorator


def on_message(
    *,
    regex: str | None = None,
    keywords: list[str] | None = None,
    platforms: list[str] | None = None,
) -> Callable[[HandlerCallable], HandlerCallable]:
    def decorator(func: HandlerCallable) -> HandlerCallable:
        meta = _get_or_create_meta(func)
        meta.trigger = MessageTrigger(
            regex=regex,
            keywords=keywords or [],
            platforms=platforms or [],
        )
        return func

    return decorator


def on_event(event_type: str) -> Callable[[HandlerCallable], HandlerCallable]:
    def decorator(func: HandlerCallable) -> HandlerCallable:
        meta = _get_or_create_meta(func)
        meta.trigger = EventTrigger(event_type=event_type)
        return func

    return decorator


def on_schedule(
    *,
    cron: str | None = None,
    interval_seconds: int | None = None,
) -> Callable[[HandlerCallable], HandlerCallable]:
    def decorator(func: HandlerCallable) -> HandlerCallable:
        meta = _get_or_create_meta(func)
        meta.trigger = ScheduleTrigger(cron=cron, interval_seconds=interval_seconds)
        return func

    return decorator


def require_admin(func: HandlerCallable) -> HandlerCallable:
    meta = _get_or_create_meta(func)
    meta.permissions.require_admin = True
    return func
