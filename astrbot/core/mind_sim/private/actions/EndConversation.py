from collections.abc import AsyncGenerator

from astrbot.core.mind_sim import Action, ActionOutput


class EndConversationAction(Action):
    """结束对话动作 - 停止所有动作并退出

    适用于：
    - 结束当前对话场景
    - 停止所有正在执行的动作
    - 发送 END 事件退出事件流

    **注意：此动作会停止整个思考流程**
    """

    name = "end_conversation"
    description = """结束对话动作 - 退出当前对话场景

**重要：此动作会停止所有动作并退出思考流程**
适用于：
- 结束当前对话
- 清理所有正在进行的动作
- 完全退出当前思考流程
如果你想结束对话,请输入为什么想结束对话
参数: {"reason": "向用户说的结束原因",reply:"根据你的性格特征结束对话回复给用户的内容"（可选）}
"""
    fixed_prompt = "正在结束对话"
    priority = -200  # 最低优先级

    usage_guide = """
    - 适用于需要完全结束对话的场景
    - 会停止所有正在运行的动作
    - 退出后不会再触发任何思考
    """

    def get_completion_output(self) -> ActionOutput | None:
        """重写完成行为：发送 END 类型"""
        # END 类型是特殊的事件，会直接关闭事件流
        return ActionOutput(
            action_name=self.instance_id or self.name,
            type="end",
            content="对话已结束",
        )

    async def run(self, params: dict) -> AsyncGenerator[ActionOutput, None]:
        reason = params.get("reason", "用户主动结束")

        self.update_state(
            progress="结束对话中",
            prompt_contribution=f"正在结束对话: {reason}",
        )

        # 先停止所有其他正在运行的动作
        # 注意：这里需要通过 executor 来停止，但 Action 本身无法直接访问 executor
        # 所以通过发送消息的方式来处理
        relpy = params.get("reply", None)

        if relpy:
            # yield ActionOutput( #后续编辑使用，应该传入事件使用
            #     action_name=self.instance_id or self.name,
            #     type="reply",
            #     content=f"{relpy}",
            #     metadata={"no_think": True},  # 标记不触发重新思考
            # )
            yield ActionOutput(
                action_name=self.instance_id or self.name,
                type="noop",
                content="对话已结束",
            )
        else:
            yield ActionOutput(
                action_name=self.instance_id or self.name,
                type="noop",
                content="对话已结束",
            )
