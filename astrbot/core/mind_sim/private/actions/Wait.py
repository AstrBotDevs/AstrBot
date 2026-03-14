from typing import AsyncGenerator

from astrbot.core.mind_sim import Action, ActionOutput, ActionStopMsg


class WaitAction(Action):
    """等待动作 - 暂停思考，等待指定时间

    等待结束后会自动触发下一轮思考。
    可被用户消息打断。
    """

    name = "wait"
    description = """等待动作 - 暂停思考，等待指定时间

**重要：等待结束后会自动触发下一轮思考**

适用于以下情况：
- 你已经表达清楚一轮，想给对方留出空间
- 你感觉对方的话还没说完，或者自己刚刚发了好几条连续消息
- 你想要等待一定时间来让对方把话说完，或者等待对方反应
- 你想保持安静，专注"听"而不是马上回复

请你根据上下文来判断要等待多久：
- 如果你们交流间隔时间很短，聊的很频繁，不宜等待太久（10-30秒）
- 如果你们交流间隔时间很长，聊的很少，可以等待较长时间（60-120秒）

参数: {"duration": 60}
"""
    fixed_prompt = "正在等待中"
    priority = 0

    usage_guide = """
    - 当你不知道该做什么时使用
    - 当需要等待用户回复时使用
    - 当需要给对方留出思考空间时使用
    - 等待结束后会自动再次进入思考
    """

    async def run(self, params: dict) -> AsyncGenerator[ActionOutput, None]:
        self.update_state(
            progress="等待中",
            prompt_contribution="正在等待用户回复",
        )

        # 等待一段时间
        # 实际上等待动作应该由外部事件（用户消息）来打断
        wait_time = params.get("duration", 60)  # 默认等待60秒

        for i in range(int(wait_time)):
            msg = await self.check_message(timeout=1.0)
            if msg:
                if isinstance(msg, ActionStopMsg):
                    self.update_state(progress="等待被停止")
                    # 被停止时不触发重新思考（由外部控制）
                    return
                # SEND 消息可以调整等待时间
                continue

            # 更新剩余时间
            remaining = wait_time - i - 1
            if remaining > 0 and remaining % 10 == 0:
                self.update_state(
                    progress=f"等待中（剩余 {remaining} 秒）",
                )

        self.update_state(progress="等待超时，将重新思考")
        # 正常完成，会自动发送 completed 事件触发重新思考
