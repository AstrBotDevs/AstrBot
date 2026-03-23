"""高级人格 MindSim 子阶段

作为 AstrMessageEvent 和 MindSim 之间的桥梁（适配器），负责：
1. 从 AstrMessageEvent 提取信息，构建 MindContext
2. 调用 factory 启动 MindSim 并获取事件流
3. 监听 MindEvent 事件流，将回复发送到消息平台
4. 不控制事件生命周期（由主思考 Brain 决定何时结束）

职责划分：
- internal_mind：管理 Brain 生命周期、监听事件流
- ReplyAction：生成回复、发送消息、保存 AI 回复到历史
- MemoryManager：不在此阶段管理（由其他模块处理）
"""

import json
from collections.abc import AsyncGenerator

from astrbot.core import logger
from astrbot.core.message.components import (
    BaseMessageComponent,
    Face,
    File,
    Image,
    Plain,
    Reply,
    WechatEmoji,
)
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.mind_sim import MindContext
from astrbot.core.mind_sim.dispatcher import PrivateBrainFactory
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
        # 每个 InternalMindSubStage 实例持有一个 BrainFactory
        # 不再使用全局单例
        self._brain_factory = PrivateBrainFactory()
        # 图片描述缓存：{event_id: caption_text}，避免重复描述同一张图片
        self._image_caption_cache: dict[str, str] = {}

    async def process(
        self, event: AstrMessageEvent, provider_wake_prefix: str
    ) -> AsyncGenerator[None, None]:
        """处理高级人格事件

        流程：
        1. 获取或创建对话
        2. 预处理消息（图片转描述、表情描述、文件描述）
        3. 保存用户消息到历史（包含完整的媒体描述）
        4. 获取/创建 Brain 实例（通过 PrivateBrainFactory）
        5. 监听事件流，每条回复发送并保存
        """
        # 1. 获取或创建对话
        conversation = await _get_or_create_conversation(event, self.conv_manager)
        conversation_id = conversation.cid

        # 2. 获取高级人格配置（必须先于预处理，因为预处理需要人格的图片描述模型配置）
        persona = await self._resolve_persona(event)

        # 3. 预处理消息：提取图片/表情/文件，生成文本描述（传入 persona 以读取图片描述模型）
        processed_message = await self._preprocess_message(event, persona)

        # 4. 保存用户消息到历史
        await self._save_user_message(event, conversation_id, processed_message)

        # 5. 构建 MindContext
        mind_ctx = self._build_mind_context(event, conversation_id, persona)

        # 6. 启动事件流，ReplyAction 通过 event.send() 直接发送回复
        # dispatch() 内部已处理活跃事件流的消息投递
        # 使用预处理后的消息（包含图片描述等）替代原始 message_str
        event_stream = self._brain_factory.dispatch(
            ctx=mind_ctx,
            message=processed_message,
            sender_id=event.get_sender_id(),
            sender_name=event.get_sender_name(),
            persona=persona,
        )

        async for mind_event in event_stream:
            if mind_event.type == MindEventType.TYPING:
                await event.send_typing()
            elif mind_event.type == MindEventType.ERROR:
                error_msg = mind_event.data.get("message", "思考出错")
                logger.error(f"[InternalMindSubStage] MindSim 错误: {error_msg}")
                await event.send(MessageChain([Plain(f"[错误] {error_msg}")]))
            elif mind_event.type == MindEventType.PIPELINE_YIELD:
                # AgentMindSubStage 请求 pipeline yield
                # event.result 已由 AgentMindSubStage 设置好
                done_event = mind_event.data.get("done_event")
                logger.debug("[InternalMindSubStage] 收到 PIPELINE_YIELD，yield 给 pipeline")
                yield  # 传递给 pipeline 框架，RespondStage 处理 event.result
                # pipeline yield 返回后，通知 AgentMindSubStage 继续
                if done_event:
                    done_event.set()
            elif mind_event.type == MindEventType.END:
                logger.debug("[InternalMindSubStage] 收到 END 事件，思考结束")
                break

        return
        yield  # noqa: 使函数保持 AsyncGenerator 类型

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
        """从 PersonaManager 解析当前会话的高级人格配置

        resolve_selected_persona 返回的是 Personality TypedDict（本质是 dict），
        可以直接用 .get() 访问嵌套字段。
        """
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
            # Persona 是 Personality TypedDict（dict 的别名），直接返回
            return persona or {}
        except Exception as e:
            logger.warning(f"[InternalMindSubStage] 解析人格配置失败: {e}")
            return {}

    async def _save_user_message(
        self, event: AstrMessageEvent, conversation_id: str, processed_message: str
    ) -> None:
        """保存用户消息到历史

        Args:
            event: 消息事件
            conversation_id: 对话 ID
            processed_message: 预处理后的消息文本（包含媒体描述）
        """
        try:
            conversation = await self.conv_manager.get_conversation(
                event.unified_msg_origin, conversation_id
            )
            history = (
                json.loads(conversation.history)
                if conversation and conversation.history
                else []
            )
            # 保存预处理后的消息，而非原始 message_str（保留了图片/表情描述）
            history.append({"role": "user", "content": processed_message})
            await self.conv_manager.update_conversation(
                event.unified_msg_origin,
                conversation_id,
                history=history,
            )
        except Exception as e:
            logger.warning(f"[InternalMindSubStage] 保存用户消息失败: {e}")

    async def _preprocess_message(self, event: AstrMessageEvent, persona: dict) -> str:
        """预处理用户消息，提取并描述图片、表情、文件等媒体

        Args:
            event: 消息事件
            persona: 高级人格配置（用于读取图片描述模型配置）

        Returns:
            预处理后的完整消息文本
        """
        parts: list[str] = []

        # 获取基础文本（已去除唤醒前缀）
        base_text = event.message_str.strip()
        if base_text:
            parts.append(base_text)

        # 获取消息链
        message_chain = getattr(event.message_obj, "message", [])
        if not message_chain:
            return event.message_str

        # 遍历消息组件，提取媒体描述（传入 persona 以读取图片描述模型）
        media_descriptions = await self._extract_media_descriptions(
            event, message_chain, persona
        )
        parts.extend(media_descriptions)

        return "\n".join(parts).strip() or event.message_str

    async def _extract_media_descriptions(
        self,
        event: AstrMessageEvent,
        components: list[BaseMessageComponent],
        persona: dict,
    ) -> list[str]:
        """从消息组件中提取媒体描述

        Args:
            event: 消息事件
            components: 消息组件列表
            persona: 高级人格配置

        Returns:
            媒体描述文本列表
        """
        descriptions: list[str] = []
        image_paths: list[str] = []

        for comp in components:
            if isinstance(comp, Plain):
                # Plain 文本已通过 message_str 处理，跳过避免重复
                continue
            elif isinstance(comp, Image):
                try:
                    image_path = await comp.convert_to_file_path()
                    image_paths.append(image_path)
                except Exception as e:
                    logger.warning(f"[InternalMindSubStage] 转换图片失败: {e}")
                    descriptions.append("[图片（无法读取）]")
            elif isinstance(comp, Face):
                # QQ 表情 ID 转为描述
                descriptions.append(f"[QQ表情: {comp.id}]")
            elif isinstance(comp, WechatEmoji):
                # 微信表情描述
                emoji_desc = self._describe_wechat_emoji(comp)
                descriptions.append(f"[微信表情: {emoji_desc}]")
            elif isinstance(comp, File):
                # 文件描述
                file_name = getattr(comp, "name", None) or getattr(comp, "file", "未知文件")
                file_size = getattr(comp, "size", None)
                size_str = f" ({file_size} bytes)" if file_size else ""
                descriptions.append(f"[文件: {file_name}{size_str}]")
            elif isinstance(comp, Reply):
                # 处理引用消息中的媒体
                if comp.chain:
                    chain_descs = await self._extract_media_descriptions(
                        event, comp.chain, persona
                    )
                    descriptions.extend(chain_descs)
                # 引用消息的文本内容已通过 message_str 处理

        # 批量处理图片描述（避免多次调用 LLM）
        if image_paths:
            try:
                caption_text = await self._describe_images(event, image_paths, persona)
                if caption_text:
                    descriptions.append(f"<image_caption>{caption_text}</image_caption>")
            except Exception as e:
                logger.warning(f"[InternalMindSubStage] 图片描述失败: {e}")
                descriptions.append(f"[图片 x{len(image_paths)}]")

        return descriptions

    def _describe_wechat_emoji(self, emoji: WechatEmoji) -> str:
        """生成微信表情的文字描述"""
        # 优先使用 md5 作为标识
        md5 = getattr(emoji, "md5", None)
        if md5:
            return f"微信表情包表情 (md5={md5[:8]}...)"
        cdnurl = getattr(emoji, "cdnurl", None)
        if cdnurl:
            return f"微信表情包表情 (url={cdnurl[:50]}...)"
        return "微信表情包表情"

    async def _describe_images(
        self, event: AstrMessageEvent, image_paths: list[str], persona: dict
    ) -> str:
        """通过 LLM 生成图片描述

        优先级：人格配置的 image_caption_model → 全局配置 → 默认正在使用的提供商。
        参考 AgentMindSubStage 的模型注册模式。

        Args:
            event: 消息事件
            image_paths: 图片本地路径列表
            persona: 高级人格配置

        Returns:
            图片描述文本，失败时返回空字符串
        """
        plugin_context = self.ctx.plugin_manager.context

        # 1. 尝试获取人格配置的图片描述模型
        llm_config = persona.get("llm_model_config", {})
        img_caption_config = llm_config.get("image_caption_model", {}) or {}

        provider_id = img_caption_config.get("provider_id", "")
        model = img_caption_config.get("model", "")
        prompt = img_caption_config.get(
            "prompt", "请简洁描述这张图片的内容，用一句话概括。"
        )

        # 2. 如果人格未配置，回退到全局配置
        if not provider_id or not model:
            cfg = plugin_context.get_config(event.unified_msg_origin)
            provider_settings = cfg.get("provider_settings", {})
            provider_id = provider_settings.get("default_image_caption_provider_id", "")
            prompt = provider_settings.get(
                "image_caption_prompt", "请简洁描述这张图片的内容，用一句话概括。"
            )

        # 3. 如果仍未找到 provider_id，使用默认的正在使用的提供商
        if not provider_id:
            prov = plugin_context.get_using_provider(event.unified_msg_origin)
            if prov:
                provider_id = prov.provider_config.get("id", "")
                # 如果人格也没配置 model，则用 provider 的默认 model
                if not model:
                    model = prov.get_model()
            else:
                logger.warning("[InternalMindSubStage] 未找到可用的图片描述模型")
                return ""

        # 4. 获取 Provider 实例
        provider = plugin_context.get_provider_by_id(provider_id)
        if not provider:
            logger.warning(
                f"[InternalMindSubStage] 图片描述 Provider 不存在: {provider_id}"
            )
            return ""

        # 5. 调用 LLM 生成描述
        try:
            logger.debug(
                f"[InternalMindSubStage] 生成图片描述，使用 provider={provider_id}, model={model}"
            )
            llm_resp = await provider.text_chat(
                prompt=prompt,
                image_urls=image_paths,
            )
            caption = llm_resp.completion_text or ""
            if caption:
                logger.debug(f"[InternalMindSubStage] 图片描述结果: {caption[:100]}")
            return caption
        except Exception as e:
            logger.error(f"[InternalMindSubStage] LLM 图片描述调用失败: {e}")
            return ""
