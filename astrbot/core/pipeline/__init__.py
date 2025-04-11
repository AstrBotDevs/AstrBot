from astrbot.core.message.message_event_result import (
    MessageEventResult,
    EventResultType,
)

from .waking_check.stage import WakingCheckStage
from .whitelist_check.stage import WhitelistCheckStage
from .rate_limit_check.stage import RateLimitStage
from .content_safety_check.stage import ContentSafetyCheckStage
from .platform_compatibility.stage import PlatformCompatibilityStage
from .preprocess_stage.stage import PreProcessStage
from .process_stage.stage import ProcessStage
from .result_decorate.stage import ResultDecorateStage
from .respond.stage import RespondStage

# 管道阶段顺序
STAGES_ORDER = [
    "WakingCheckStage",  # 检查是否需要唤醒
    "WhitelistCheckStage",  # 检查是否在群聊/私聊白名单
    "RateLimitStage",  # 检查会话是否超过频率限制
    "ContentSafetyCheckStage",  # 检查内容安全
    "PlatformCompatibilityStage",  # 检查所有处理器的平台兼容性
    "PreProcessStage",  # 预处理
    "ProcessStage",  # 交由 Stars 处理（a.k.a 插件），或者 LLM 调用
    "ResultDecorateStage",  # 处理结果，比如添加回复前缀、t2i、转换为语音 等
    "RespondStage",  # 发送消息
]

__all__ = [
    "WakingCheckStage",
    "WhitelistCheckStage",
    "RateLimitStage",
    "ContentSafetyCheckStage",
    "PlatformCompatibilityStage",
    "PreProcessStage",
    "ProcessStage",
    "ResultDecorateStage",
    "RespondStage",
    "MessageEventResult",
    "EventResultType",
]
