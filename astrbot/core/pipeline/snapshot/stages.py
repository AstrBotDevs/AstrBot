from __future__ import annotations

from typing import Any

from astrbot.core.pipeline import STAGES_ORDER
from astrbot.core.star.star_handler import EventType

STAGE_META: dict[str, dict[str, Any]] = {
    "WakingCheckStage": {
        "title": "平台消息下发时",
        "description": "消息到达后进入流程的入口点；同时展示消息处理器的触发条件摘要。",
        "kind": "gate",
    },
    "WhitelistCheckStage": {
        "title": "系统规则：白名单检查",
        "description": "系统层白名单校验（无插件介入时可隐藏）。",
        "kind": "gate",
    },
    "SessionStatusCheckStage": {
        "title": "系统规则：会话状态检查",
        "description": "系统层会话启用状态检查（无插件介入时可隐藏）。",
        "kind": "gate",
    },
    "RateLimitStage": {
        "title": "系统规则：频率限制",
        "description": "系统层频率限制检查（无插件介入时可隐藏）。",
        "kind": "gate",
    },
    "ContentSafetyCheckStage": {
        "title": "系统规则：内容安全检查",
        "description": "系统层内容安全检测（无插件介入时可隐藏）。",
        "kind": "gate",
    },
    "PreProcessStage": {
        "title": "系统内部预处理",
        "description": "系统内部预处理阶段（通常无插件介入，可隐藏）。",
        "kind": "processing",
    },
    "ProcessStage": {
        "title": "插件处理/LLM请求",
        "description": "插件处理、LLM 请求/响应相关 hook、以及函数工具调用等发生的主要阶段。",
        "kind": "processing",
    },
    "ResultDecorateStage": {
        "title": "回复消息前",
        "description": "发送消息前的结果装饰/修改钩子。",
        "kind": "processing",
    },
    "RespondStage": {
        "title": "发送消息后",
        "description": "发送消息及发送后钩子。",
        "kind": "processing",
    },
}


def stage_for_event_type(event_type: EventType) -> list[str]:
    """
    返回该 event_type 在静态视角下“归属的阶段列表”。

    设计方案要求：
    - AdapterMessageEvent 在 WakingCheckStage 展示触发条件摘要；
      同时其 handler 实际执行发生在 ProcessStage，因此也归属 ProcessStage。
    """
    if event_type == EventType.AdapterMessageEvent:
        return ["WakingCheckStage", "ProcessStage"]
    if event_type in (
        EventType.OnLLMRequestEvent,
        EventType.OnLLMResponseEvent,
        EventType.OnCallingFuncToolEvent,
    ):
        return ["ProcessStage"]
    if event_type == EventType.OnDecoratingResultEvent:
        return ["ResultDecorateStage"]
    if event_type == EventType.OnAfterMessageSentEvent:
        return ["RespondStage"]
    return []


def build_stage_snapshot(stage_id: str, participants: list[dict[str, Any]]) -> dict[str, Any]:
    meta = STAGE_META.get(stage_id) or {
        "title": stage_id,
        "description": "",
        "kind": "processing",
    }
    return {
        "stage": {
            "id": stage_id,
            "title": meta["title"],
            "description": meta["description"],
            "kind": meta["kind"],
        },
        "participants": participants,
    }


__all__ = ["STAGES_ORDER", "STAGE_META", "build_stage_snapshot", "stage_for_event_type"]