"""MindSim 记忆系统数据库模型"""

from sqlmodel import Field, SQLModel, Text

from astrbot.core.db.po import TimestampMixin


class MindSimChatMemory(TimestampMixin, SQLModel, table=True):
    """对话记忆表 - 存储话题总结"""

    __tablename__: str = "mindsim_chat_memories"

    id: int | None = Field(
        default=None,
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
    )
    chat_id: str = Field(nullable=False, index=True)
    """对话标识（unified_msg_origin）"""
    start_time: float = Field(nullable=False)
    """话题起始时间戳"""
    end_time: float = Field(nullable=False)
    """话题结束时间戳"""
    original_text: str = Field(default="", sa_type=Text)
    """原始聊天记录文本"""
    participants: str = Field(default="[]")
    """参与者昵称列表（JSON）"""
    theme: str = Field(default="")
    """主题/话题标题"""
    keywords: str = Field(default="[]")
    """关键词（JSON list）"""
    summary: str = Field(default="", sa_type=Text)
    """概括（50-200字）"""
    key_point: str | None = Field(default=None, sa_type=Text)
    """关键信息点（JSON list）"""
    count: int = Field(default=0)
    """被检索次数"""


class MindSimPersonMemory(TimestampMixin, SQLModel, table=True):
    """人物记忆表 - 存储对人物的印象"""

    __tablename__: str = "mindsim_person_memories"

    id: int | None = Field(
        default=None,
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
    )
    chat_id: str = Field(nullable=False, index=True)
    """来源对话（unified_msg_origin）"""
    user_id: str = Field(nullable=False, index=True)
    """用户ID"""
    nickname: str = Field(default="")
    """昵称"""
    impression: str = Field(default="", sa_type=Text)
    """印象描述"""
    traits: str | None = Field(default=None)
    """性格特点（JSON list）"""
    relationship: str | None = Field(default=None)
    """关系描述"""
    memorable_events: str | None = Field(default=None, sa_type=Text)
    """值得记忆的事件（JSON list）"""
