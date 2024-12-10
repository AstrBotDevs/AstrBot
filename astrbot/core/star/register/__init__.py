from .star import register_star
from .star_handler import (
    register_command,
    register_command_group,
    register_event_message_type,
    register_platform_adapter_type,
    register_regex,
    register_permission_type
)

__all__ = [
    'register_star',
    'register_command',
    'register_command_group',
    'register_event_message_type',
    'register_platform_adapter_type',
    'register_regex',
    'register_permission_type'
]