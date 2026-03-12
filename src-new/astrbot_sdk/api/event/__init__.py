"""事件处理 API 模块。

提供事件相关的公共接口：
- AstrMessageEvent: 消息事件类，包含消息文本、用户信息、平台信息等
- filter: 事件过滤器命名空间，提供命令、正则、权限等装饰器
- ADMIN: 管理员权限常量

此模块是旧版 astrbot_sdk.api.event 的兼容层。
新版 API 建议直接使用 astrbot_sdk.events.MessageEvent 和 astrbot_sdk.decorators。

# TODO: 相比旧版 event 模块，新版缺少以下内容：

## 缺失的文件：
1. astrbot_message.py:
   - MessageMember: 消息成员数据类
   - Group: 群组数据类
   - AstrBotMessage: AstrBot 消息对象

2. astr_message_event.py:
   - AstrMessageEvent: 完整的消息事件类（当前只有 MessageEvent 别名）
   - AstrMessageEventModel: Pydantic 模型版本

3. event_result.py:
   - EventResultType: 事件结果类型枚举
   - ResultContentType: 结果内容类型枚举
   - MessageEventResult: 消息事件结果类

4. event_type.py:
   - EventType: 内部事件类型枚举

5. message_session.py:
   - MessageSession: 消息会话标识类

6. message_type.py:
   - MessageType: 消息类型枚举

## 缺失的功能：
旧版 AstrMessageEvent 提供的便捷方法：
- get_platform_name/id(), get_message_str/messages/type()
- get_session_id/group_id/self_id/sender_id/sender_name()
- set_extra/get_extra/clear_extra() 额外信息存储
- is_private_chat/is_wake_up/is_admin() 状态检查
- set_result/stop_event/continue_event/is_stopped() 事件控制
- make_result/plain_result/image_result/chain_result() 结果构建
- send(), react(), get_group() 消息操作
"""

from ...events import MessageEvent as AstrMessageEvent
from .filter import ADMIN, filter

__all__ = ["ADMIN", "AstrMessageEvent", "filter"]
