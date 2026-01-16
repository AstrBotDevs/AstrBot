import builtins
import copy
import datetime
import zoneinfo

from astrbot.api import logger, sp, star
from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import Image, Reply
from astrbot.api.provider import Provider, ProviderRequest
from astrbot.core.agent.message import TextPart
from astrbot.core.pipeline.process_stage.utils import (
    CHATUI_SPECIAL_DEFAULT_PERSONA_PROMPT,
)
from astrbot.core.provider.func_tool_manager import ToolSet


class ProcessLLMRequest:
    def __init__(self, context: star.Context):
        self.ctx = context
        cfg = context.get_config()
        self.timezone = cfg.get("timezone")
        if not self.timezone:
            # 系统默认时区
            self.timezone = None
        else:
            logger.info(f"Timezone set to: {self.timezone}")

    async def _ensure_persona(
        self, req: ProviderRequest, cfg: dict, umo: str, platform_type: str
    ):
        """确保用户人格已加载"""
        if not req.conversation:
            return
        # persona inject

        # custom rule is preferred
        persona_id = (
            await sp.get_async(
                scope="umo", scope_id=umo, key="session_service_config", default={}
            )
        ).get("persona_id")

        if not persona_id:
            persona_id = req.conversation.persona_id or cfg.get("default_personality")
            if not persona_id and persona_id != "[%None]":  # [%None] 为用户取消人格
                default_persona = self.ctx.persona_manager.selected_default_persona_v3
                if default_persona:
                    persona_id = default_persona["name"]

                    # ChatUI special default persona
                    if platform_type == "webchat":
                        # non-existent persona_id to let following codes not working
                        persona_id = "_chatui_default_"
                        req.system_prompt += CHATUI_SPECIAL_DEFAULT_PERSONA_PROMPT

        persona = next(
            builtins.filter(
                lambda persona: persona["name"] == persona_id,
                self.ctx.persona_manager.personas_v3,
            ),
            None,
        )
        if persona:
            if prompt := persona["prompt"]:
                req.system_prompt += prompt
            if begin_dialogs := copy.deepcopy(persona["_begin_dialogs_processed"]):
                req.contexts[:0] = begin_dialogs

        # tools select
        tmgr = self.ctx.get_llm_tool_manager()
        if (persona and persona.get("tools") is None) or not persona:
            # select all
            toolset = tmgr.get_full_tool_set()
            for tool in toolset:
                if not tool.active:
                    toolset.remove_tool(tool.name)
        else:
            toolset = ToolSet()
            if persona["tools"]:
                for tool_name in persona["tools"]:
                    tool = tmgr.get_func(tool_name)
                    if tool and tool.active:
                        toolset.add_tool(tool)
        req.func_tool = toolset
        logger.debug(f"Tool set for persona {persona_id}: {toolset.names()}")

    async def _ensure_img_caption(
        self,
        req: ProviderRequest,
        cfg: dict,
        img_cap_prov_id: str,
    ):
        try:
            caption = await self._request_img_caption(
                img_cap_prov_id,
                cfg,
                req.image_urls,
            )
            if caption:
                req.extra_user_content_parts.append(
                    TextPart(text=f"<image_caption>{caption}</image_caption>")
                )
                req.image_urls = []
        except Exception as e:
            logger.error(f"处理图片描述失败: {e}")

    async def _request_img_caption(
        self,
        provider_id: str,
        cfg: dict,
        image_urls: list[str],
    ) -> str:
        if prov := self.ctx.get_provider_by_id(provider_id):
            if isinstance(prov, Provider):
                img_cap_prompt = cfg.get(
                    "image_caption_prompt",
                    "Please describe the image.",
                )
                logger.debug(f"Processing image caption with provider: {provider_id}")
                llm_resp = await prov.text_chat(
                    prompt=img_cap_prompt,
                    image_urls=image_urls,
                )
                return llm_resp.completion_text
            raise ValueError(
                f"Cannot get image caption because provider `{provider_id}` is not a valid Provider, it is {type(prov)}.",
            )
        raise ValueError(
            f"Cannot get image caption because provider `{provider_id}` is not exist.",
        )

    async def process_llm_request(self, event: AstrMessageEvent, req: ProviderRequest):
        """在请求 LLM 前注入人格信息、Identifier、时间、回复内容等 System Prompt"""
        cfg: dict = self.ctx.get_config(umo=event.unified_msg_origin)[
            "provider_settings"
        ]

        # prompt prefix
        if prefix := cfg.get("prompt_prefix"):
            # 支持 {{prompt}} 作为用户输入的占位符
            if "{{prompt}}" in prefix:
                req.prompt = prefix.replace("{{prompt}}", req.prompt)
            else:
                req.prompt = prefix + req.prompt

        # 收集系统提醒信息
        system_parts = []

        # user identifier
        if cfg.get("identifier"):
            user_id = event.message_obj.sender.user_id
            user_nickname = event.message_obj.sender.nickname
            system_parts.append(f"User ID: {user_id}, Nickname: {user_nickname}")

        # group name identifier
        if cfg.get("group_name_display") and event.message_obj.group_id:
            if not event.message_obj.group:
                logger.error(
                    f"Group name display enabled but group object is None. Group ID: {event.message_obj.group_id}"
                )
                return
            group_name = event.message_obj.group.group_name
            if group_name:
                system_parts.append(f"Group name: {group_name}")

        # time info
        if cfg.get("datetime_system_prompt"):
            current_time = None
            if self.timezone:
                # 启用时区
                try:
                    now = datetime.datetime.now(zoneinfo.ZoneInfo(self.timezone))
                    current_time = now.strftime("%Y-%m-%d %H:%M (%Z)")
                except Exception as e:
                    logger.error(f"时区设置错误: {e}, 使用本地时区")
            if not current_time:
                current_time = (
                    datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M (%Z)")
                )
            system_parts.append(f"Current datetime: {current_time}")

        img_cap_prov_id: str = cfg.get("default_image_caption_provider_id") or ""
        if req.conversation:
            # inject persona for this request
            platform_type = event.get_platform_name()
            await self._ensure_persona(
                req, cfg, event.unified_msg_origin, platform_type
            )

            # image caption
            if img_cap_prov_id and req.image_urls:
                await self._ensure_img_caption(req, cfg, img_cap_prov_id)

        # quote message processing
        # 解析引用内容
        quote = None
        for comp in event.message_obj.message:
            if isinstance(comp, Reply):
                quote = comp
                break
        if quote:
            content_parts = []

            # 1. 处理引用的文本
            sender_info = (
                f"({quote.sender_nickname}): " if quote.sender_nickname else ""
            )
            message_str = quote.message_str or "[Empty Text]"
            content_parts.append(f"{sender_info}{message_str}")

            # 2. 处理引用的图片 (保留原有逻辑，但改变输出目标)
            image_seg = None
            if quote.chain:
                for comp in quote.chain:
                    if isinstance(comp, Image):
                        image_seg = comp
                        break

            if image_seg:
                try:
                    # 找到可以生成图片描述的 provider
                    prov = None
                    if img_cap_prov_id:
                        prov = self.ctx.get_provider_by_id(img_cap_prov_id)
                    if prov is None:
                        prov = self.ctx.get_using_provider(event.unified_msg_origin)

                    # 调用 provider 生成图片描述
                    if prov and isinstance(prov, Provider):
                        llm_resp = await prov.text_chat(
                            prompt="Please describe the image content.",
                            image_urls=[await image_seg.convert_to_file_path()],
                        )
                        if llm_resp.completion_text:
                            # 将图片描述作为文本添加到 content_parts
                            content_parts.append(
                                f"[Image Caption in quoted message]: {llm_resp.completion_text}"
                            )
                    else:
                        logger.warning(
                            "No provider found for image captioning in quote."
                        )
                except BaseException as e:
                    logger.error(f"处理引用图片失败: {e}")

            # 3. 将所有部分组合成文本并添加到 extra_user_content_parts 中
            # 确保引用内容被正确的标签包裹
            quoted_content = "\n".join(content_parts)
            # 确保所有内容都在<Quoted Message>标签内
            quoted_text = f"<Quoted Message>\n{quoted_content}\n</Quoted Message>"

            req.extra_user_content_parts.append(TextPart(text=quoted_text))

        # 统一包裹所有系统提醒
        if system_parts:
            system_content = (
                "<system_reminder>" + "\n".join(system_parts) + "</system_reminder>"
            )
            req.extra_user_content_parts.append(TextPart(text=system_content))
