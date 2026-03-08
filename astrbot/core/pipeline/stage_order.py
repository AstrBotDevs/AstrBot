"""Pipeline stage execution order."""

STAGES_ORDER = [
    "WakingCheckStage",  # 检查是否需要唤醒
    "WhitelistCheckStage",  # 检查是否在群聊/私聊白名单
    "SessionStatusCheckStage",  # 检查会话是否整体启用
    "RateLimitStage",  # 检查会话是否超过频率限制
    "ContentSafetyCheckStage",  # 检查内容安全
    "PreProcessStage",  # 预处理
    "ProcessStage",  # 交由 Stars 处理（a.k.a 插件），或者 LLM 调用
    "ResultDecorateStage",  # 处理结果，比如添加回复前缀、t2i、转换为语音 等
    "RespondStage",  # 发送消息
]

__all__ = ["STAGES_ORDER"]
