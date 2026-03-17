"""高级人格 MindSim 子阶段

作为 AstrMessageEvent 和 MindSim 之间的桥梁（适配器），负责：
1. 从 AstrMessageEvent 提取信息，构建 MindContext
2. 创建 MindSimLLM 实例，传给 dispatcher
3. 调用 dispatcher 启动 MindSim 并获取事件流
4. 监听 MindEvent 事件流，将回复发送到消息平台
5. 独立保存历史记录（收到用户消息保存一次，每条 AI 回复保存一次）
6. 不控制事件生命周期（由主思考 Brain 决定何时结束）
"""

import json
from collections.abc import AsyncGenerator

from astrbot.core import logger
from astrbot.core.message.components import Plain
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.mind_sim import MindContext, MindSimLLM, get_dispatcher
from astrbot.core.mind_sim.messages import MindEventType
from astrbot.core.pipeline.stage import Stage
from astrbot.core.platform.astr_message_event import AstrMessageEvent

from ....context import PipelineContext


async def _get_or_create_conversation(event: AstrMessageEvent, conv_manager):
    """获取或创建当前会话的对话"""
    # 先尝试获取当前对话ID
    cid = await conv_manager.get_curr_conversation_id(event.unified_msg_origin)
    if cid:
        conversation = await conv_manager.get_conversation(
            event.unified_msg_origin, cid
        )
        if conversation:
            return conversation

    # 如果没有当前对话，创建新的
    cid = await conv_manager.new_conversation(
        event.unified_msg_origin, event.get_platform_id()
    )
    conversation = await conv_manager.get_conversation(event.unified_msg_origin, cid)
    if not conversation:
        raise RuntimeError("无法创建新的对话。")
    return conversation


class InternalMindSubStage(Stage):
    """高级人格 MindSim 子阶段"""

    async def initialize(self, ctx: PipelineContext) -> None:
        self.ctx = ctx
        self.conv_manager = ctx.plugin_manager.context.conversation_manager

    async def process(
        self, event: AstrMessageEvent, provider_wake_prefix: str
    ) -> AsyncGenerator[None, None]:
        """处理高级人格事件

        收发消息独立，不阻塞：
        - 用户消息到达时立即保存历史
        - MindSim 每产生一条回复就立即发送到平台并保存历史
        - 事件流结束由 Brain 主思考控制
        """
        # 1. 获取或创建对话
        conversation = await _get_or_create_conversation(event, self.conv_manager)
        conversation_id = conversation.cid

        # 2. 保存用户消息到历史
        await self._save_user_message(event, conversation_id)

        # 3. 获取 Provider 并创建 MindSimLLM
        llm = self._create_llm(event)

        # 4. 获取高级人格配置
        persona = await self._resolve_persona(event)

        # 5. 构建 MindContext
        mind_ctx = self._build_mind_context(event, conversation_id, persona)

        # 6. 调用 dispatcher 获取事件流
        dispatcher = get_dispatcher()
        event_stream = dispatcher.dispatch(
            ctx=mind_ctx,
            message=event.message_str,
            sender_id=event.get_sender_id(),
            sender_name=event.get_sender_name(),
            llm=llm,
            persona=persona,
        )
        yield
        # 7. 监听事件流并处理
        async for mind_event in event_stream:
            if mind_event.type == MindEventType.REPLY:
                text = mind_event.data.get("text", "")
                if not text:
                    continue

                # 发送到消息平台
                await event.send(MessageChain([Plain(text)]))

                # 保存 AI 回复到历史
                await self._save_assistant_message(event, conversation_id, text)

                # yield 让管道继续
                yield

            elif mind_event.type == MindEventType.TYPING:
                await event.send_typing()

            elif mind_event.type == MindEventType.ERROR:
                error_msg = mind_event.data.get("message", "思考出错")
                logger.error(f"[InternalMindSubStage] MindSim 错误: {error_msg}")
                await event.send(MessageChain([Plain(f"[错误] {error_msg}")]))
                yield

            elif mind_event.type == MindEventType.END:
                logger.debug("[InternalMindSubStage] 收到 END 事件，思考结束")
                break

    def _create_llm(self, event: AstrMessageEvent) -> MindSimLLM | None:
        """从 PipelineContext 获取 Provider 并创建 MindSimLLM"""
        try:
            provider = self.ctx.plugin_manager.context.get_using_provider(
                umo=event.unified_msg_origin
            )
            if not provider:
                logger.warning("[InternalMindSubStage] 未找到可用 Provider")
                return None

            provider_manager = self.ctx.plugin_manager.context.provider_manager

            # 获取人格配置（如果有）
            persona_config = getattr(event, "_persona_config", {}) or {}

            if persona_config:
                return MindSimLLM.from_persona_config(
                    provider=provider,
                    persona_config=persona_config,
                    provider_manager=provider_manager,
                )
            else:
                return MindSimLLM(
                    provider_manager=provider_manager,
                    default_provider=provider,
                )
        except Exception as e:
            logger.error(f"[InternalMindSubStage] 创建 MindSimLLM 失败: {e}")
            return None

    def _build_mind_context(
        self,
        event: AstrMessageEvent,
        conversation_id: str,
        persona: dict,
    ) -> MindContext:
        """从 AstrMessageEvent 构建 MindContext"""
        plugin_context = self.ctx.plugin_manager.context
        return MindContext(
            session_id=str(event.session),
            unified_msg_origin=event.unified_msg_origin,
            is_private=event.is_private_chat(),
            persona_id=getattr(event, "_persona_id", "default"),
            system_prompt=persona.get("prompt", ""),
            personality_config=persona.get("personality_config", {}),
            chat_config=persona.get("chat_config", {}),
            robot_config=persona.get("robot_config", {}),
            user_id=event.get_sender_id(),
            user_name=event.get_sender_name(),
            conv_manager=self.conv_manager,
            conversation_id=conversation_id,
            event=event,
            plugin_context=plugin_context,
        )

    async def _resolve_persona(self, event: AstrMessageEvent) -> dict:
        """从 PersonaManager 解析当前会话的高级人格配置"""
        try:
            plugin_context = self.ctx.plugin_manager.context
            persona_manager = plugin_context.persona_manager
            cfg = plugin_context.get_config(event.unified_msg_origin)
            provider_settings = cfg.get("provider_settings", {})

            persona_id, persona, _, _ = await persona_manager.resolve_selected_persona(
                umo=event.unified_msg_origin,
                conversation_persona_id=getattr(event, "_persona_id", None),
                platform_name=event.get_platform_name(),
                provider_settings=provider_settings,
            )
            return persona or {}
        except Exception as e:
            logger.warning(f"[InternalMindSubStage] 解析人格配置失败: {e}")
            return {}

    async def _save_user_message(
        self, event: AstrMessageEvent, conversation_id: str
    ) -> None:
        """保存用户消息到历史（追加模式）"""
        try:
            conversation = await self.conv_manager.get_conversation(
                event.unified_msg_origin, conversation_id
            )
            history = json.loads(conversation.history) if conversation and conversation.history else []
            history.append({"role": "user", "content": event.message_str})
            await self.conv_manager.update_conversation(
                event.unified_msg_origin,
                conversation_id,
                history=history,
            )
        except Exception as e:
            logger.warning(f"[InternalMindSubStage] 保存用户消息失败: {e}")

    async def _save_assistant_message(
        self, event: AstrMessageEvent, conversation_id: str, content: str
    ) -> None:
        """保存 AI 回复到历史（追加模式）"""
        try:
            conversation = await self.conv_manager.get_conversation(
                event.unified_msg_origin, conversation_id
            )
            history = json.loads(conversation.history) if conversation and conversation.history else []
            history.append({"role": "assistant", "content": content})
            await self.conv_manager.update_conversation(
                event.unified_msg_origin,
                conversation_id,
                history=history,
            )
        except Exception as e:
            logger.warning(f"[InternalMindSubStage] 保存 AI 回复失败: {e}")
