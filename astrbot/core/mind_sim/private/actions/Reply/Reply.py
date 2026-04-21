"""回复动作 - 调用 LLM 生成并发送消息

支持根据主思考传入的参数生成不同风格的回复。

职责：
1. 调用 LLM 生成回复（通过 AgentMindSubStage.call，完整流程）
2. 发送消息到用户（AgentMindSubStage 自动处理）
3. 保存 AI 回复到对话历史
"""

import json
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from astrbot.core import logger
from astrbot.core.mind_sim import Action, ActionOutput
from astrbot.core.mind_sim.private.actions.Reply.reply_prompts import (
    build_reply_prompt,
)
from astrbot.core.mind_sim.private.prompts import (
    build_action_states_prompt,
    build_history_prompt,
    build_temp_prompts_section,
)

if TYPE_CHECKING:
    pass


class ReplyAction(Action):
    """回复动作 - 调用 LLM 生成并发送消息

    支持根据主思考传入的参数生成不同风格的回复。
    """

    name = "reply"
    description = """回复动作 - 调用 LLM 生成回复并发送 不要回复太频繁，像真人一样，能拒绝回复
**回复完成后会自动触发下一轮思考**
**自动调用 LLM 生成回复内容**：
- reply_type: 正常回复(normal)/追加回复(append)
- reply_guidance: 给指导方向，什么话题，传入给回复器的知识，内容等等，这是给另一个大模型进行专门回复的参考与指导
- target: 追加回复时，要补充的原发言内容（仅 append 类型需要）
- reason: 追加回复时，补充的原因（仅 append 类型需要）
参数: {"reply_type": "normal", "reply_guidance": "就今天天气很好进行回复，今天天气17°"}
追加示例: {"reply_type": "append", "reply_guidance": "", "target": "今天天气不错", "reason": "忘了说温度"}
"""
    fixed_prompt = "正在生成回复"
    priority = 100

    usage_guide = """
    - 适用于需要 AI 生成回复的场景
    - normal: 正常回复，根据聊天内容口语化回复
    - append: 追加回复，补充说明自己刚刚的发言，需要传入 target 和 reason
    - 主思考传入 reply_guidance 指导回复方向
    """

    async def on_complete(self, params: dict) -> None:
        """完成后添加临时提示词"""
        text = self._state.data.get("reply_text", "")
        if text:
            self.add_temp_prompt(
                f"已回复: {text} 提示：距离0秒的这条语句 则这是回复后调用思考，可以选择只等待，或者追加回复，避免频繁回复，不要回复的太频繁",
                rounds=5,
            )

    async def run(self, params: dict) -> AsyncGenerator[ActionOutput, None]:
        """运行回复动作

        流程：
        1. 获取对话历史和上下文
        2. 调用 LLM 生成回复
        3. 发送消息到用户
        4. 保存回复到历史
        """
        reply_type = params.get("reply_type", "normal")
        reply_guidance = params.get("reply_guidance", "")
        target = params.get("target", "")
        reason = params.get("reason", "")

        self.update_state(
            progress="准备生成回复",
            prompt_contribution=f"正在生成 {reply_type} 风格回复",
            data={"reply_type": reply_type},
        )

        # 获取对话历史
        dialogue_history = await self._get_dialogue_history_formatted()

        # 获取临时提醒
        temp_prompts_str = self._build_temp_prompts_formatted()

        # 获取运行中的动作实例状态
        running_actions_str = self._build_running_states_formatted()

        # 构建提示词
        prompt = build_reply_prompt(
            reply_type=reply_type,
            reply_guidance=reply_guidance,
            ctx=self.ctx,
            dialogue_history=dialogue_history,
            target=target,
            reason=reason,
            temp_prompts=temp_prompts_str,
            running_actions=running_actions_str,
        )

        ORANGE = "\033[38;5;214m"
        RESET = "\033[0m"
        logger.debug(f"{ORANGE}[ReplyAction] 回复提示词: {prompt}{RESET}")

        # 调用 LLM 生成回复（与 internal.py 架构完全一致）
        # 会自动处理：typing 状态、事件钩子、会话锁、流式/普通响应、保存历史
        self.update_state(progress="调用 LLM 生成回复中")
        reply_text = ""

        try:
            # send_to_platform=True：通过 PIPELINE_YIELD 桥接 pipeline 框架发送消息
            # 自动处理 typing、hook、session lock
            reply_text = await self.llm.call(
                prompt=prompt,
                role="reply",
                send_to_platform=True,
            )

        except Exception as e:
            self.update_state(
                progress="LLM 调用失败",
                prompt_contribution=f"生成回复失败: {e}",
            )
            yield ActionOutput(
                action_name=self.instance_id or self.name,
                type="reply",
                content="抱歉，生成回复时出错了",
            )
            return

        # 清理回复内容
        reply_text = self._clean_response(reply_text)

        if not reply_text:
            self.update_state(progress="回复为空", prompt_contribution="LLM 返回空内容")
            # return
        else:
            self.update_state(
                progress="发送回复",
                prompt_contribution=f"回复内容: {reply_text[:50]}...",
                data={"reply_text": reply_text},
            )

        # 保存回复到历史（call 已通过 event.send 发送，这里只保存历史）
        await self._save_reply_to_history(reply_text)

        # 通知主思考回复已完成，触发重新思考
        yield ActionOutput(
            action_name=self.instance_id or self.name,
            type="completed",
            prompt=f"已回复: {reply_text}",
            content="",
        )

        self.update_state(
            status="completed",
            progress="回复完成",
            prompt_contribution=None,
        )

    async def _save_reply_to_history(self, text: str) -> None:
        """保存 AI 回复到对话历史

        从 conv_manager 读取当前 history，追加 assistant 消息，然后更新。
        """
        if not self.ctx.conv_manager or not self.ctx.conversation_id:
            logger.debug(
                "[ReplyAction] 无法保存历史：缺少 conv_manager 或 conversation_id"
            )
            return

        try:
            conv = await self.ctx.conv_manager.get_conversation(
                self.ctx.unified_msg_origin, self.ctx.conversation_id
            )
            if not conv:
                logger.debug("[ReplyAction] 无法保存历史：对话不存在")
                return

            history = json.loads(conv.history) if conv.history else []
            history.append({"role": "assistant", "content": text})

            await self.ctx.conv_manager.update_conversation(
                self.ctx.unified_msg_origin,
                self.ctx.conversation_id,
                history=history,
            )
            logger.debug(f"[ReplyAction] 已保存回复到历史，长度: {len(text)}")
        except Exception as e:
            logger.warning(f"[ReplyAction] 保存历史失败: {e}")

    async def _get_dialogue_history_formatted(self) -> str:
        """获取格式化的对话历史"""
        if not self.ctx.conv_manager or not self.ctx.conversation_id:
            return "暂无对话历史"

        try:
            conv = await self.ctx.conv_manager.get_conversation(
                self.ctx.unified_msg_origin, self.ctx.conversation_id
            )
            if not conv or not conv.history:
                return "暂无对话历史"

            history = json.loads(conv.history)
            if not history:
                return "暂无对话历史"

            chat_config = self.ctx.chat_config or {}
            message_length = chat_config.get("message_length", 10)
            if not isinstance(message_length, int) or message_length < 1:
                message_length = 10

            return build_history_prompt(history, max_turns=message_length)
        except Exception:
            return "暂无对话历史"

    def _build_temp_prompts_formatted(self) -> str:
        """获取格式化的临时提醒"""
        if not self._executor:
            return ""
        temp_contents = self._executor.tick_temp_prompts(consume_rounds=False)
        if not temp_contents:
            return ""
        return build_temp_prompts_section(temp_contents)

    def _build_running_states_formatted(self) -> str:
        """获取格式化的动作实例状态"""
        if not self._executor:
            return ""
        running_states = self._executor.get_running_states()
        if not running_states:
            return ""
        return build_action_states_prompt(running_states)

    @staticmethod
    def _clean_response(text: str) -> str:
        """清理 LLM 返回的内容"""
        if not text:
            return ""

        # 移除常见前缀
        prefixes_to_remove = [
            "回复：",
            "以下是我的回复：",
            "我的回复：",
            "答复：",
            "回答：",
        ]
        for prefix in prefixes_to_remove:
            if text.startswith(prefix):
                text = text[len(prefix) :].strip()

        # 移除常见后缀
        suffixes_to_remove = [
            "以上",
            "以上就是",
        ]
        for suffix in suffixes_to_remove:
            if text.endswith(suffix):
                text = text[: -len(suffix)].strip()

        return text.strip()
