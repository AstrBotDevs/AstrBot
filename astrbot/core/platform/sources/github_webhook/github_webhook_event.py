from astrbot.api.platform import AstrBotMessage, PlatformMetadata

from ...astr_message_event import AstrMessageEvent


class GitHubWebhookMessageEvent(AstrMessageEvent):
    """GitHub Webhook 消息事件"""

    def __init__(
        self,
        message_str: str,
        message_obj: AstrBotMessage,
        platform_meta: PlatformMetadata,
        session_id: str,
        event_type: str,
        event_data: dict,
    ):
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.event_type = event_type
        """GitHub 事件类型: issues, issue_comment, pull_request"""
        self.event_data = event_data
        """原始事件数据"""
