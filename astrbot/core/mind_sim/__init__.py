"""mind_sim - 高级人格的持续思考引擎

mind_sim 是高级人格的核心模块，负责：
- 持续循环思考
- 管理多个并发动作
- 协调动作之间的通信
- 与外部（用户、平台）交互

核心概念：
- MindContext: 会话上下文状态
- mind_sim: 主引擎，负责思考循环
- Action: 独立运行的动作协程
- Decision: LLM 产生的决策

使用示例:
```python
from astrbot.core.mind_sim import MindContext, MindSimLLM
from astrbot.core.mind_sim.private.actions import get_available_actions, create_action
import time

# 创建上下文
ctx = MindContext(
    session_id="test",
    unified_msg_origin="webchat:private:test",
    is_private=True,
    persona_id="advanced_1",
    system_prompt="你是一个有帮助的助手",
)

# 获取可用动作
actions = get_available_actions(is_private=True)

# 创建动作实例
reply_action = create_action("reply", ctx)
```
"""

from .action import Action, ActionExecutor, PreExecuteResult, RunningAction, TempPrompt
from .context import MindContext
from .messages import (
    ActionOutput,
    ActionSendMsg,
    ActionState,
    ActionStateUpdate,
    ActionStopMsg,
    Decision,
    IncomingUserMessage,
    MindEvent,
    MindEventType,
    MindMessage,
)

__all__ = [
    # 核心
    "MindContext",
    "Action",
    "ActionExecutor",
    "TempPrompt",
    "PreExecuteResult",
    "RunningAction",
    # 消息类型
    "MindMessage",
    "ActionState",
    "ActionSendMsg",
    "ActionStopMsg",
    "ActionStateUpdate",
    "ActionOutput",
    "IncomingUserMessage",
    "Decision",
    "MindEvent",
    "MindEventType",

]
