import enum
from . import HandlerFilter
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.config import AstrBotConfig
from astrbot.core.platform.message_type import MessageType

class PermissionType(enum.Flag):
    '''权限类型。当选择 MEMBER，ADMIN 也可以通过。
    '''
    ADMIN = "admin"
    MEMBER = "member"

class PermissionTypeFilter(HandlerFilter):
    def __init__(self, permission_type: PermissionType, raise_error: bool = True):
        self.permission_type = permission_type
        self.raise_error = raise_error
        
    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        '''过滤器
        '''
        if self.permission_type == PermissionType.ADMIN:
            if not event.is_admin():
                event.stop_event()
                raise ValueError("您没有权限执行此操作。")

        return True
