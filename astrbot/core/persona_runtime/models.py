from dataclasses import dataclass, field
from datetime import datetime
from typing import TypedDict


@dataclass(slots=True)
class PersonaRuntimeSignal:
    persona_id: str
    umo: str
    user_text: str
    assistant_text: str
    sender_id: str
    conversation_id: str | None = None
    occurred_at: datetime | None = None
    mentioned: bool = False


@dataclass(slots=True)
class PersonaRuntimeContext:
    persona_id: str
    umo: str
    agent_state: str
    talk_frequency_adjust: float
    consecutive_idle_count: int
    cooldown_until: datetime | None
    last_interaction_at: datetime | None
    last_proactive_at: datetime | None
    extra_state: dict = field(default_factory=dict)


class Personality(TypedDict):
    """LLM 人格类。

    在 v4.0.0 版本及之后，推荐使用 ``astrbot.core.db.po.Persona``。
    """

    prompt: str
    name: str
    begin_dialogs: list[str]
    tools: list[str] | None
    """工具列表。None 表示使用所有工具，空列表表示不使用任何工具"""
    skills: list[str] | None
    """Skills 列表。None 表示使用所有 Skills，空列表表示不使用任何 Skills"""
    custom_error_message: str | None
    """可选的人格自定义报错回复信息。配置后将优先发送给最终用户。"""

    # cache
    _begin_dialogs_processed: list[dict]
