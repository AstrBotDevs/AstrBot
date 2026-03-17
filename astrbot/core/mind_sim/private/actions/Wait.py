from typing import AsyncGenerator
import asyncio

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

    async def on_complete(self, params: dict) -> None:
        """完成后添加临时提示词（仅正常完成时调用）"""
        # 从 state 中获取实际等待时间
        wait_time = self._state.data.get("actual_wait_time",0)
        if wait_time:
            self.add_temp_prompt(
                f"已等待: {int(wait_time)}秒 ，如果有重复的等待，其实可以调用空时间啥也不用干",
                rounds=5,
                min_duration=30.0
            )

    async def run(self, params: dict) -> AsyncGenerator[ActionOutput, None]:
        self.update_state(
            progress="等待中",
            prompt_contribution="正在等待用户回复",
        )

        wait_time = float(params.get("duration", 60))  # 转换为 float
        start_time = asyncio.get_event_loop().time()
        update_interval = 10.0  # 每10秒更新一次进度
        check_interval = 2.0  # 每2秒检查一次消息

        try:
            while True:
                elapsed = asyncio.get_event_loop().time() - start_time
                remaining = wait_time - elapsed

                if remaining <= 0.0:
                    # 等待时间到
                    break

                # 每次只检查1秒，避免长时间阻塞
                msg = await self.check_message(timeout=check_interval)

                if msg:
                    if isinstance(msg, ActionStopMsg):
                        self.update_state(progress="等待被停止")
                        # 被停止时不触发重新思考（由外部控制）
                        return
                    # SEND 消息可以调整等待时间或其他操作
                    continue

                # 每隔 update_interval 更新一次进度
                elapsed = asyncio.get_event_loop().time() - start_time
                remaining = wait_time - elapsed
                if remaining > 0.0 and int(elapsed) % int(update_interval) == 0:
                    self.update_state(
                        progress=f"等待中（剩余 {int(remaining)} 秒）",
                    )

        except asyncio.CancelledError:
            self.update_state(progress="等待被取消")
            return

        # 记录实际等待时间
        actual_wait = asyncio.get_event_loop().time() - start_time
        self.update_state(data={"actual_wait_time": actual_wait})
        self.update_state(progress="等待完成，将重新思考")

        # 正常完成，yield 一个标记
        yield ActionOutput(
            action_name=self.instance_id or self.name,
            type="completed",
            content="",
        )
        # 正常完成，会自动发送 completed 事件触发重新思考
