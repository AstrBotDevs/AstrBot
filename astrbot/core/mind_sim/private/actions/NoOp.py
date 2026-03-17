from typing import AsyncGenerator

from astrbot.core.mind_sim import Action, ActionOutput


class NoOpAction(Action):
    """空动作 - 什么都不做

    适用于：
    - 跳过当前思考轮次，不产生任何输出
    - 保持静默状态一段时间

    **完成后不会触发重新思考**
    """

    name = "noop"
    description = """空动作 - 什么都不做

**重要：完成后不会触发重新思考**

适用于：
- 保持静默状态
- 跳过本次思考轮次
- 临时沉默

参数: {}
"""
    fixed_prompt = "无操作"
    priority = -100  # 最低优先级

    usage_guide = """
    - 适用于需要暂时停止但不离场的情况
    - 适用于占据思考轮次但不产生回复
    - 不会触发重新思考，保持当前状态
    """

    def get_completion_output(self) -> ActionOutput | None:
        """重写完成行为：不触发重新思考"""
        return ActionOutput(
            action_name=self.instance_id or self.name,
            type="completed_no_think",
            content="",
        )

    async def on_complete(self, params: dict) -> None:
        """完成后添加临时提示词"""
        self.add_temp_prompt("刚刚选择了静默，没有要回复的内容", rounds=3)

    async def run(self, params: dict) -> AsyncGenerator[ActionOutput, None]:
        self.update_state(
            progress="无操作",
            prompt_contribution="当前选择静默",
        )

        # 什么也不做，直接完成
        yield ActionOutput(
            action_name=self.instance_id or self.name,
            type="noop",
            content="",
        )