import asyncio
import random
import re
import time
import traceback
from collections.abc import AsyncGenerator

from astrbot import logger
from astrbot.core.message.components import At, Image, Json, Node, Plain, Record, Reply
from astrbot.core.message.message_event_result import ResultContentType
from astrbot.core.pipeline.content_safety_check.stage import ContentSafetyCheckStage
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.message_type import MessageType
from astrbot.core.star.session_llm_manager import SessionServiceManager
from astrbot.core.star.star_handler import EventType

from ..context import PipelineContext
from ..stage import Stage


class ResultDecorateStage(Stage):
    async def initialize(self, ctx: PipelineContext) -> None:
        self.ctx = ctx
        self.reply_prefix = ctx.astrbot_config["platform_settings"]["reply_prefix"]
        self.reply_with_mention = ctx.astrbot_config["platform_settings"][
            "reply_with_mention"
        ]
        self.reply_with_quote = ctx.astrbot_config["platform_settings"][
            "reply_with_quote"
        ]
        self.t2i_word_threshold = ctx.astrbot_config["t2i_word_threshold"]
        try:
            self.t2i_word_threshold = int(self.t2i_word_threshold)
            self.t2i_word_threshold = max(self.t2i_word_threshold, 50)
        except Exception:
            self.t2i_word_threshold = 150
        self.t2i_active_template = ctx.astrbot_config["t2i_active_template"]
        self.t2i_use_file_service = bool(
            ctx.astrbot_config.get("t2i_use_file_service", False),
        )

        self.forward_threshold = ctx.astrbot_config["platform_settings"][
            "forward_threshold"
        ]

        trigger_probability = ctx.astrbot_config["provider_tts_settings"].get(
            "trigger_probability",
            1,
        )
        try:
            self.tts_trigger_probability = max(
                0.0,
                min(float(trigger_probability), 1.0),
            )
        except TypeError, ValueError:
            self.tts_trigger_probability = 1.0

        # 分段回复
        self.words_count_threshold = int(
            ctx.astrbot_config["platform_settings"]["segmented_reply"][
                "words_count_threshold"
            ],
        )
        self.enable_segmented_reply = ctx.astrbot_config["platform_settings"][
            "segmented_reply"
        ]["enable"]
        self.only_llm_result = ctx.astrbot_config["platform_settings"][
            "segmented_reply"
        ]["only_llm_result"]
        self.split_mode = ctx.astrbot_config["platform_settings"][
            "segmented_reply"
        ].get("split_mode", "regex")
        self.regex = ctx.astrbot_config["platform_settings"]["segmented_reply"]["regex"]
        self.split_words = ctx.astrbot_config["platform_settings"][
            "segmented_reply"
        ].get("split_words", ["。", "？", "！", "~", "…"])
        if self.split_words:
            escaped_words = sorted(
                [re.escape(word) for word in self.split_words], key=len, reverse=True
            )
            self.split_words_pattern = re.compile(
                f"(.*?({'|'.join(escaped_words)})|.+$)", re.DOTALL
            )
        else:
            self.split_words_pattern = None
        self.content_cleanup_rule = ctx.astrbot_config["platform_settings"][
            "segmented_reply"
        ]["content_cleanup_rule"]

        # exception
        self.content_safe_check_reply = ctx.astrbot_config["content_safety"][
            "also_use_in_response"
        ]
        self.content_safe_check_stage = None
        if self.content_safe_check_reply:
            self.content_safe_check_stage = ContentSafetyCheckStage()
            await self.content_safe_check_stage.initialize(ctx)

        provider_cfg = ctx.astrbot_config.get("provider_settings", {})
        self.show_reasoning = provider_cfg.get("display_reasoning_text", False)
        if ctx.preferences is None:
            raise RuntimeError("ResultDecorateStage requires shared preferences")
        self.session_services = SessionServiceManager(ctx.preferences)

    def _split_text_by_words(self, text: str) -> list[str]:
        """使用分段词列表分段文本"""
        if not self.split_words_pattern:
            return [text]

        segments = self.split_words_pattern.findall(text)
        result = []
        for seg in segments:
            if isinstance(seg, tuple):
                content = seg[0]
                if not isinstance(content, str):
                    continue
                for word in self.split_words:
                    if content.endswith(word):
                        content = content[: -len(word)]
                        break
                if content.strip():
                    result.append(content)
            elif seg and seg.strip():
                result.append(seg)
        return result if result else [text]

    async def process(
        self,
        event: AstrMessageEvent,
    ) -> AsyncGenerator[None]:
        result = event.get_result()
        if result is None or not result.chain:
            return

        if result.result_content_type == ResultContentType.STREAMING_RESULT:
            return
        is_stream = result.result_content_type == ResultContentType.STREAMING_FINISH
        async for _ in self._check_content_safety(event, result, is_stream):
            yield
        if not await self._run_decorating_hooks(event, is_stream):
            return
        if is_stream:
            return

        # Hooks may replace or clear the event result, so always retrieve it again.
        result = event.get_result()
        if result is None or not result.chain:
            return
        self._apply_prefix(result)
        self._segment_result(event, result)
        used_tts = await self._apply_tts(event, result)
        if not used_tts:
            self._add_reasoning(event, result)
            await self._apply_t2i(event, result)
        self._apply_forward_node(event, result)
        self._apply_mention_and_quote(event, result)

    async def _check_content_safety(self, event, result, is_stream):
        if not (
            self.content_safe_check_reply
            and isinstance(self.content_safe_check_stage, ContentSafetyCheckStage)
            and result.is_llm_result()
            and not is_stream
        ):
            return
        async for item in self.content_safe_check_stage.process(
            event,
            check_text="".join(c.text for c in result.chain if isinstance(c, Plain)),
        ):
            yield item

    async def _run_decorating_hooks(self, event, is_stream: bool) -> bool:
        for handler in self.ctx.handlers.get_handlers_by_event_type(
            EventType.OnDecoratingResultEvent, plugins_name=event.plugins_name
        ):
            plugin_name = handler.handler_module_path
            try:
                plugin = self.ctx.plugins.get_by_module(handler.handler_module_path)
                plugin_name = plugin.name if plugin else handler.handler_module_path
                logger.debug(
                    "hook(on_decorating_result) -> %s - %s",
                    plugin_name,
                    handler.handler_name,
                )
                if is_stream:
                    logger.warning(
                        "启用流式输出时，依赖发送消息前事件钩子的插件可能无法正常工作"
                    )
                await handler.handler(event)
                if (result := event.get_result()) is None or not result.chain:
                    logger.debug(
                        "hook(on_decorating_result) -> %s - %s 将消息结果清空。",
                        plugin_name,
                        handler.handler_name,
                    )
            except asyncio.CancelledError:
                raise
            except KeyboardInterrupt, SystemExit:
                raise
            except Exception:
                logger.error(traceback.format_exc())
            if event.is_stopped():
                logger.info(
                    "%s - %s 终止了事件传播。",
                    plugin_name,
                    handler.handler_name,
                )
                return False
        return True

    def _apply_prefix(self, result) -> None:
        if self.reply_prefix:
            for component in result.chain:
                if isinstance(component, Plain):
                    component.text = self.reply_prefix + component.text
                    return

    def _segment_result(self, event, result) -> None:
        if not self.enable_segmented_reply or event.get_platform_name() in {
            "qq_official_webhook",
            "weixin_official_account",
            "dingtalk",
        }:
            return
        if self.only_llm_result and not result.is_model_result():
            return
        chain = []
        for component in result.chain:
            if (
                not isinstance(component, Plain)
                or len(component.text) > self.words_count_threshold
            ):
                chain.append(component)
                continue
            if self.split_mode == "words":
                parts = self._split_text_by_words(component.text)
            else:
                try:
                    parts = re.findall(
                        self.regex, component.text, re.DOTALL | re.MULTILINE
                    )
                except re.error:
                    logger.error(
                        "分段回复正则表达式错误，使用默认分段方式: %s",
                        traceback.format_exc(),
                    )
                    parts = re.findall(
                        r".*?[。？！~…]+|.+$", component.text, re.DOTALL | re.MULTILINE
                    )
            if not parts:
                chain.append(component)
                continue
            for part in parts:
                if self.content_cleanup_rule:
                    try:
                        part = re.sub(self.content_cleanup_rule, "", part)
                    except re.error:
                        logger.error(
                            "分段回复过滤表达式失败，无法成功过滤：%s",
                            traceback.format_exc(),
                        )
                        self.content_cleanup_rule = None
                if part := part.strip():
                    chain.append(Plain(part))
        result.chain = chain

    async def _register_generated_file(self, event, file_path: str) -> str:
        register_owned = getattr(
            self.ctx.file_token_service,
            "register_owned_file",
            None,
        )
        if callable(register_owned):
            from collections.abc import Awaitable
            from typing import cast

            return await cast(Awaitable[str], register_owned(file_path, event))
        return await self.ctx.file_token_service.register_file(file_path)

    async def _apply_tts(self, event, result) -> bool:
        should_tts = (
            bool(self.ctx.astrbot_config["provider_tts_settings"]["enable"])
            and result.is_llm_result()
            and await self.session_services.should_process_tts_request(event)
            and random.random() <= self.tts_trigger_probability
        )
        if not should_tts:
            return False
        provider = self.ctx.execution_context.get_using_tts_provider(
            event.unified_msg_origin
        )
        if not provider:
            logger.warning("会话 %s 未配置文本转语音模型。", event.unified_msg_origin)
            return False
        chain = []
        settings = self.ctx.astrbot_config["provider_tts_settings"]
        callback_base = str(
            self.ctx.astrbot_config.get("callback_api_base", "") or ""
        ).rstrip("/")
        for component in result.chain:
            if not isinstance(component, Plain) or len(component.text) <= 1:
                chain.append(component)
                continue
            try:
                audio_path = await provider.get_audio(component.text)
                if not audio_path:
                    raise RuntimeError("TTS audio file is empty")
                event.track_temporary_local_file(audio_path)
                url = audio_path
                if settings["use_file_service"] and callback_base:
                    token = await self._register_generated_file(event, audio_path)
                    url = f"{callback_base}/api/v1/files/tokens/{token}"
                chain.append(Record(file=url, url=url, text=component.text))
                if settings["dual_output"]:
                    chain.append(component)
            except Exception:
                logger.error("TTS 失败，使用文本发送。\n%s", traceback.format_exc())
                chain.append(component)
        result.chain = chain
        return True

    def _add_reasoning(self, event, result) -> None:
        reasoning = event.get_extra("_llm_reasoning_content")
        if not self.show_reasoning or not reasoning:
            return
        if event.get_platform_name() == "lark":
            result.chain.insert(
                0,
                Json(
                    data={
                        "type": "lark_collapsible_panel_reasoning",
                        "title": "💭 Thinking",
                        "expanded": False,
                        "content": str(reasoning),
                    }
                ),
            )
        else:
            result.chain.insert(0, Plain(f"🤔 思考: {reasoning}\n\n────\n"))

    async def _apply_t2i(self, event, result) -> None:
        if not (
            (result.use_t2i_ is None and self.ctx.astrbot_config["t2i"])
            or result.use_t2i_
        ):
            return
        text = "".join("\n\n" + c.text for c in result.chain if isinstance(c, Plain))
        if not text or len(text) <= self.t2i_word_threshold:
            return
        started = time.time()
        try:
            image_path = await self.ctx.html_renderer.render_t2i(
                text, template_name=self.t2i_active_template
            )
        except asyncio.CancelledError:
            raise
        except KeyboardInterrupt, SystemExit:
            raise
        except Exception as exc:
            logger.error("文本转图片失败，使用文本发送：%s", exc)
            return
        if time.time() - started > 3:
            logger.warning(
                "文本转图片耗时超过了 3 秒，如果觉得很慢可以在 WebUI 中关闭文本转图片模式。"
            )
        if not image_path:
            return
        event.track_temporary_local_file(image_path)
        callback_base = str(
            self.ctx.astrbot_config.get("callback_api_base", "") or ""
        ).rstrip("/")
        if callback_base and (
            self.t2i_use_file_service
            or event.get_platform_name() in {"aiocqhttp", "napcat"}
        ):
            try:
                token = await self._register_generated_file(event, image_path)
                result.chain = [
                    Image.fromURL(f"{callback_base}/api/v1/files/tokens/{token}")
                ]
                return
            except Exception:
                logger.warning("文转图文件服务注册失败，回退为本地图片发送。")
        result.chain = [Image.fromFileSystem(image_path)]

    def _apply_forward_node(self, event, result) -> None:
        if event.get_platform_name() != "aiocqhttp":
            return
        if (
            sum(len(c.text) for c in result.chain if isinstance(c, Plain))
            > self.forward_threshold
        ):
            result.chain = [
                Node(uin=event.get_self_id(), name="AstrBot", content=[*result.chain])
            ]

    def _apply_mention_and_quote(self, event, result) -> None:
        if not all(isinstance(item, (Plain, Image)) for item in result.chain):
            return
        if (
            self.reply_with_mention
            and event.get_message_type() != MessageType.FRIEND_MESSAGE
        ):
            result.chain.insert(
                0, At(qq=event.get_sender_id(), name=event.get_sender_name())
            )
            if len(result.chain) > 1 and isinstance(result.chain[1], Plain):
                result.chain[1].text = "\n" + result.chain[1].text
        if self.reply_with_quote:
            result.chain.insert(0, Reply(id=event.message_obj.message_id))
