import builtins
import copy
import datetime
import zoneinfo

from astrbot.api import logger, star
from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import Image, Reply
from astrbot.api.provider import Provider, ProviderRequest
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

    def _ensure_persona(self, req: ProviderRequest, cfg: dict):
        """确保用户人格已加载"""
        if not req.conversation:
            return
        # persona inject
        persona_id = req.conversation.persona_id or cfg.get("default_personality")
        if not persona_id and persona_id != "[%None]":  # [%None] 为用户取消人格
            default_persona = self.ctx.persona_manager.selected_default_persona_v3
            if default_persona:
                persona_id = default_persona["name"]
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
                req.prompt = f"(Image Caption: {caption})\n\n{req.prompt}"
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

        # user identifier
        if cfg.get("identifier"):
            user_id = event.message_obj.sender.user_id
            user_nickname = event.message_obj.sender.nickname
            req.prompt = (
                f"\n[User ID: {user_id}, Nickname: {user_nickname}]\n{req.prompt}"
            )

        # group name identifier
        if cfg.get("group_name_display") and event.message_obj.group_id:
            group_name = event.message_obj.group.group_name
            if group_name:
                req.system_prompt += f"\nGroup name: {group_name}\n"

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
            req.system_prompt += f"\nCurrent datetime: {current_time}\n"

        img_cap_prov_id: str = cfg.get("default_image_caption_provider_id") or ""
        if req.conversation:
            # inject persona for this request
            self._ensure_persona(req, cfg)

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
            sender_info = ""
            if quote.sender_nickname:
                sender_info = f"(Sent by {quote.sender_nickname})"
            message_str = quote.message_str or "[Empty Text]"
            req.system_prompt += (
                f"\nUser is quoting a message{sender_info}.\n"
                f"Here are the information of the quoted message: Text Content: {message_str}.\n"
            )
            image_seg = None
            if quote.chain:
                for comp in quote.chain:
                    if isinstance(comp, Image):
                        image_seg = comp
                        break
            if image_seg:
                try:
                    prov = None
                    if img_cap_prov_id:
                        prov = self.ctx.get_provider_by_id(img_cap_prov_id)
                    if prov is None:
                        prov = self.ctx.get_using_provider(event.unified_msg_origin)
                    if prov and isinstance(prov, Provider):
                        llm_resp = await prov.text_chat(
                            prompt="Please describe the image content.",
                            image_urls=[await image_seg.convert_to_file_path()],
                        )
                        if llm_resp.completion_text:
                            req.system_prompt += (
                                f"Image Caption: {llm_resp.completion_text}\n"
                            )
                    else:
                        logger.warning("No provider found for image captioning.")
                except BaseException as e:
                    logger.error(f"处理引用图片失败: {e}")
