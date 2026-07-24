"""Structured semantic state used by the Agent Control Plane.

The module deliberately contains deterministic, provider-independent signals.
It does not attempt to generate an answer or execute a tool.  A bounded model
classifier may enrich the state later, while the executor remains authoritative.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Any

LIVE_MARKERS = (
    "今天",
    "今日",
    "现在",
    "刚刚",
    "最新",
    "实时",
    "价格",
    "金价",
    "天气",
    "新闻",
    "版本",
    "核验",
    "可信吗",
)
CONTEXT_MARKERS = (
    "这个",
    "这张",
    "上面",
    "刚才",
    "之前",
    "他刚才",
    "她刚才",
    "这句话",
    "这个梗",
    "什么意思",
)
MEMORY_MARKERS = (
    "记住",
    "记忆",
    "以前我说过",
    "之前我说过",
    "我的偏好",
    "之前的偏好",
    "我的资料",
    "个人资料",
    "记一下",
    "保存这个",
    "别忘了",
    "删除我的记忆",
    "忘掉",
)
MEDIA_MARKERS = (
    "图片",
    "照片",
    "截图",
    "表情",
    "语音",
    "音频",
    "录音",
    "声音",
    "视频",
    "bv",
    "b站",
)
ACTION_MARKERS = ("搜索", "查询", "查一下", "总结", "提取", "播放", "打开", "读取")
VIDEO_MARKERS = ("bilibili", "哔哩哔哩", "b站", "bv", "视频")
MEME_MARKERS = ("梗", "网络梗", "流行语", "哈基米", "南北绿豆", "表情包")


def _normalize(text: str) -> str:
    """Normalize user text for stable deterministic feature extraction."""

    return " ".join(unicodedata.normalize("NFKC", text or "").casefold().split())


@dataclass(slots=True)
class SemanticState:
    """A compact semantic snapshot attached to one message event."""

    goal: str = "conversation"
    dialogue_act: str = "chat"
    intent: str = "chat"
    entities: dict[str, str] = field(default_factory=dict)
    temporal_scope: str = "none"
    references: list[str] = field(default_factory=list)
    emotional_context: str = "neutral"
    required_evidence: list[str] = field(default_factory=list)
    known_facts: list[str] = field(default_factory=list)
    uncertain_facts: list[str] = field(default_factory=list)
    confidence: float = 0.0
    should_reply: bool = True
    should_search: bool = False
    should_use_memory: bool = False
    should_use_vision: bool = False
    should_use_audio: bool = False
    should_use_video: bool = False
    needs_planner: bool = False

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation for event extras and audits."""

        return asdict(self)


def infer_semantic_state(
    text: str, *, has_image: bool = False, has_audio: bool = False
) -> SemanticState:
    """Infer semantic requirements without calling a model.

    Args:
        text: Current user message.
        has_image: Whether the event contains an image or image reference.
        has_audio: Whether the event contains an audio record.

    Returns:
        Deterministic semantic state used to decide whether bounded planning is
        warranted.  It never authorizes a tool by itself.
    """

    normalized = _normalize(text)
    state = SemanticState()
    if not normalized and not (has_image or has_audio):
        state.should_reply = False
        state.confidence = 1.0
        return state

    question = bool(
        re.search(r"[?？]|吗|么|什么|怎么|如何|为何|为什么|呢$|可信", normalized)
    )
    # A temporal word alone is not evidence that a web lookup is required:
    # "今天心情不错" is conversation, while "今天金价" is a fresh fact.
    fresh_domain = any(
        marker in normalized
        for marker in (
            "价格",
            "金价",
            "天气",
            "新闻",
            "版本",
            "实时",
            "最新",
            "股价",
            "汇率",
            "比赛",
            "比分",
            "政策",
            "公告",
            "官方资料",
            "核验",
            "可信",
            "事实核查",
            "辟谣",
        )
    )
    time_word = any(marker in normalized for marker in LIVE_MARKERS[:5])
    live = fresh_domain or (time_word and question)
    context = any(marker in normalized for marker in CONTEXT_MARKERS)
    memory = any(marker in normalized for marker in MEMORY_MARKERS)
    media = (
        has_image or has_audio or any(marker in normalized for marker in MEDIA_MARKERS)
    )
    action = any(marker in normalized for marker in ACTION_MARKERS)
    video = any(marker in normalized for marker in VIDEO_MARKERS)
    meme = any(marker in normalized for marker in MEME_MARKERS)
    state.temporal_scope = "current" if live else "none"
    state.should_search = live or (action and not memory and not media)
    state.should_use_memory = memory
    state.should_use_vision = has_image or any(
        marker in normalized for marker in ("图片", "照片", "截图", "表情")
    )
    state.should_use_audio = has_audio or any(
        marker in normalized for marker in ("语音", "音频", "录音", "声音")
    )
    state.should_use_video = video
    state.references = ["recent_context"] if context else []
    if state.should_use_vision:
        state.required_evidence.append("image")
    if state.should_use_audio:
        state.required_evidence.append("audio")
    if state.should_use_video:
        state.required_evidence.append("video")
    if meme and not state.should_use_vision and not state.should_use_audio:
        # Meme explanations need social context; ordinary chat containing
        # generic verbs such as "看" must not trigger a web lookup.
        state.should_search = True
        if "fresh_web" not in state.required_evidence:
            state.required_evidence.append("fresh_web")
    if state.should_search:
        if "fresh_web" not in state.required_evidence:
            state.required_evidence.append("fresh_web")
    if state.should_use_memory:
        state.required_evidence.append("scoped_memory")

    if state.should_use_vision:
        state.intent = "vision"
        state.goal = "understand_image"
        state.dialogue_act = "question" if question or context else "describe"
    elif state.should_use_audio:
        state.intent = "audio"
        state.goal = "understand_audio"
        state.dialogue_act = "question"
    elif state.should_use_memory:
        state.intent = "memory"
        state.goal = "read_or_update_memory"
        state.dialogue_act = "request"
    elif state.should_use_video:
        state.intent = "video"
        state.goal = "understand_video"
        state.dialogue_act = "question" if question or context else "request"
    elif state.should_search:
        state.intent = "search"
        state.goal = "retrieve_fresh_facts"
        state.dialogue_act = "question" if question else "request"
    elif context:
        state.intent = "context_followup"
        state.goal = "resolve_reference"
        state.dialogue_act = "question" if question else "followup"
    elif action:
        state.intent = "tool_request"
        state.goal = "execute_capability"
        state.dialogue_act = "request"
    elif question:
        state.dialogue_act = "question"

    state.needs_planner = bool(
        state.required_evidence
        or state.intent in {"context_followup", "tool_request"}
        or question
        and len(normalized) > 8
    )
    state.confidence = min(
        0.96,
        0.55
        + (0.18 if state.intent != "chat" else 0.0)
        + (0.12 if state.required_evidence else 0.0)
        + (0.08 if question else 0.0),
    )
    return state
