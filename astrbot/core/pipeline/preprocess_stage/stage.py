import asyncio
import random
import traceback
from collections.abc import AsyncGenerator

from astrbot.core import logger
from astrbot.core.message.components import Image, Plain, Record, Reply
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.utils.media_utils import ensure_wav

from ..context import PipelineContext
from ..stage import Stage, register_stage


@register_stage
class PreProcessStage(Stage):
    async def initialize(self, ctx: PipelineContext) -> None:
        self.ctx = ctx
        self.config = ctx.astrbot_config
        self.plugin_manager = ctx.plugin_manager

        self.stt_settings: dict = self.config.get("provider_stt_settings", {})
        self.platform_settings: dict = self.config.get("platform_settings", {})

    async def process(
        self,
        event: AstrMessageEvent,
    ) -> None | AsyncGenerator[None, None]:
        """在处理事件之前的预处理"""
        # 平台特异配置：platform_specific.<platform>.pre_ack_emoji
        supported = {"telegram", "lark", "discord"}
        platform = event.get_platform_name()
        cfg = (
            self.config.get("platform_specific", {})
            .get(platform, {})
            .get("pre_ack_emoji", {})
        ) or {}
        emojis = cfg.get("emojis") or []
        if (
            cfg.get("enable", False)
            and platform in supported
            and emojis
            and event.is_at_or_wake_command
        ):
            try:
                await event.react(random.choice(emojis))
            except Exception as e:
                logger.warning(f"{platform} 预回应表情发送失败: {e}")

        # 路径映射
        if mappings := self.platform_settings.get("path_mapping", []):
            # 支持 Record，Image 消息段的路径映射。
            message_chain = event.get_messages()

            for idx, component in enumerate(message_chain):
                if isinstance(component, Record | Image) and component.url:
                    for mapping in mappings:
                        from_, to_ = mapping.split(":")
                        from_ = from_.removesuffix("/")
                        to_ = to_.removesuffix("/")

                        url = component.url.removeprefix("file://")
                        if url.startswith(from_):
                            component.url = url.replace(from_, to_, 1)
                            logger.debug(f"路径映射: {url} -> {component.url}")
                    message_chain[idx] = component

        # In here, we convert all Record components to wav format and update the file path.
        message_chain = event.get_messages()
        for idx, component in enumerate(message_chain):
            if isinstance(component, Record):
                try:
                    original_path = await component.convert_to_file_path()
                    record_path = await ensure_wav(original_path)
                    if record_path != original_path:
                        event.track_temporary_local_file(record_path)
                    component.file = record_path
                    component.path = record_path
                    message_chain[idx] = component
                except Exception as e:
                    logger.warning(f"Voice processing failed: {e}")

        # Also process Record components inside Reply chains (wav conversion)
        for component in event.get_messages():
            if isinstance(component, Reply) and component.chain:
                for idx, reply_comp in enumerate(component.chain):
                    if isinstance(reply_comp, Record):
                        try:
                            original_path = await reply_comp.convert_to_file_path()
                            record_path = await ensure_wav(original_path)
                            if record_path != original_path:
                                event.track_temporary_local_file(record_path)
                            reply_comp.file = record_path
                            reply_comp.path = record_path
                            component.chain[idx] = reply_comp
                        except Exception as e:
                            logger.warning(
                                f"Voice processing in reply chain failed: {e}"
                            )

        # STT
        if self.stt_settings.get("enable", False):
            # TODO: 独立
            ctx = self.plugin_manager.context
            stt_provider = ctx.get_using_stt_provider(event.unified_msg_origin)
            if not stt_provider:
                logger.warning(
                    f"会话 {event.unified_msg_origin} 未配置语音转文本模型。",
                )
                return

            async def _stt_record(record_comp: Record, is_reply: bool = False):
                """对单个 Record 组件执行语音转文本，成功返回 Plain，失败返回 None。"""
                prefix = "引用消息" if is_reply else ""
                try:
                    path = await record_comp.convert_to_file_path()
                except Exception as e:
                    logger.warning(f"获取{prefix}语音路径失败: {e}")
                    return None

                retry = 5
                for i in range(retry):
                    try:
                        result = await stt_provider.get_text(audio_url=path)
                        if result:
                            suffix = "(引用消息)" if is_reply else ""
                            logger.info(f"语音转文本{suffix}结果: " + result)
                            return Plain(result)
                        break
                    except FileNotFoundError:
                        # napcat workaround: file may not be ready immediately
                        logger.debug(f"文件尚未就绪 ({path})，重试 {i + 1}/{retry}")
                        await asyncio.sleep(0.5)
                        continue
                    except BaseException as e:
                        logger.error(traceback.format_exc())
                        suffix = "(引用消息)" if is_reply else ""
                        logger.error(f"语音转文本{suffix}失败: {e}")
                        break
                return None

            message_chain = event.get_messages()
            for idx, component in enumerate(message_chain):
                if isinstance(component, Record):
                    plain_comp = await _stt_record(component)
                    if plain_comp:
                        message_chain[idx] = plain_comp
                        event.message_str += plain_comp.text
                        event.message_obj.message_str += plain_comp.text

            # Also STT for Record components inside Reply chains
            for component in event.get_messages():
                if isinstance(component, Reply) and component.chain:
                    for idx, reply_comp in enumerate(component.chain):
                        if isinstance(reply_comp, Record):
                            plain_comp = await _stt_record(reply_comp, is_reply=True)
                            if plain_comp:
                                component.chain[idx] = plain_comp
                                event.message_str += plain_comp.text
                                event.message_obj.message_str += plain_comp.text
