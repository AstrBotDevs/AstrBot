import asyncio
from typing import AsyncGenerator

from astrbot.core.mind_sim import Action, ActionOutput, ActionSendMsg, ActionStopMsg


class ReplyAction(Action):
    """回复动作 - 向用户发送消息

    支持流式回复和分段发送。
    """

    name = "reply"
    description = """回复动作 - 向用户发送消息

**回复完成后会自动触发下一轮思考**

你可以自然的顺着正在进行的聊天内容进行回复或自然的提出一个问题。
支持流式回复和分段发送。

参数: {"text": "回复内容", "stream": true}
"""
    fixed_prompt = "正在回复中"

    priority = 100  # 高优先级

    # 新增 usage_guide 属性
    usage_guide = """
    - 适用于简单的文字回复
    - 适用于需要立即响应的场景
    - 对于复杂任务，建议使用其他动作
    """

    async def run(self, params: dict) -> AsyncGenerator[ActionOutput, None]:
        text = params.get("text", "")
        stream = params.get("stream", True)
        chunk_delay = params.get("chunk_delay", 0.5)

        if not text:
            self.update_state(progress="无内容", status="completed")
            return

        self.update_state(
            progress="准备回复",
            prompt_contribution=f"回复内容为: {text[:50]}...",
            data={"original_text": text, "sent": 0}
        )

        if stream:
            # 分段发送
            chunks = self._split_text(text)
            total = len(chunks)

            for i, chunk in enumerate(chunks):
                # 检查主思考消息
                msg = await self.check_message(timeout=0)
                if msg:
                    if isinstance(msg, ActionStopMsg):
                        self.update_state(progress="回复被中断")
                        return
                    elif isinstance(msg, ActionSendMsg):
                        # 可以追加内容
                        if msg.data.get("append"):
                            text += msg.data["append"]
                            chunks.extend(self._split_text(msg.data["append"]))

                yield ActionOutput(
                    action_name=self.instance_id or self.name,
                    type="reply",
                    content=chunk,
                )

                self.update_state(
                    progress=f"发送中 {i+1}/{total}",
                    data={"sent": i + 1}
                )

                await asyncio.sleep(chunk_delay)
        else:
            # 一次性发送
            yield ActionOutput(
                action_name=self.instance_id or self.name,
                type="reply",
                content=text,
            )

        self.update_state(
            status="completed",
            progress="回复完成",
            prompt_contribution=None,
        )

    @staticmethod
    def _split_text(text: str, max_len: int = 200) -> list[str]:
        """将长文本按句子边界分段"""
        if len(text) <= max_len:
            return [text]

        chunks = []
        # 按中文句号、问号、感叹号、换行分割
        import re

        sentences = re.split(r"(?<=[。！？\n])", text)
        current = ""
        for s in sentences:
            if len(current) + len(s) > max_len and current:
                chunks.append(current)
                current = s
            else:
                current += s
        if current:
            chunks.append(current)
        return chunks if chunks else [text]

