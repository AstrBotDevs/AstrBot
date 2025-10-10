import datetime
import uuid
from ...runner import EliosEventHandler
from collections import defaultdict
from astrbot.api.event import AstrMessageEvent
from astrbot.api.all import Context
from astrbot.api.message_components import Plain, Image
from astrbot.api.provider import Provider
from astrbot import logger


class AstrImplEventHandler(EliosEventHandler):
    def __init__(self, ctx: Context) -> None:
        self.ctx = ctx
        self.session_chats = defaultdict(list)
        self.session_mentioned_arousal = defaultdict(float)

    def cfg(self, event: AstrMessageEvent):
        cfg = self.ctx.get_config(umo=event.unified_msg_origin)

        tiny_model_prov_id = cfg.get("tiny_model_provider_id")
        interest_points = cfg.get("interest_points", [])

        try:
            max_cnt = int(cfg["provider_ltm_settings"]["group_message_max_cnt"])
        except BaseException as e:
            logger.error(e)
            max_cnt = 300
        image_caption = (
            True
            if cfg["provider_settings"]["default_image_caption_provider_id"]
            else False
        )
        image_caption_prompt = cfg["provider_settings"]["image_caption_prompt"]
        image_caption_provider_id = cfg["provider_settings"][
            "default_image_caption_provider_id"
        ]
        active_reply = cfg["provider_ltm_settings"]["active_reply"]
        enable_active_reply = active_reply.get("enable", False)
        ar_method = active_reply["method"]
        ar_possibility = active_reply["possibility_reply"]
        ar_prompt = active_reply.get("prompt", "")
        ar_whitelist = active_reply.get("whitelist", [])
        ar_keywords = active_reply.get("keywords", [])
        ret = {
            "max_cnt": max_cnt,
            "image_caption": image_caption,
            "image_caption_prompt": image_caption_prompt,
            "image_caption_provider_id": image_caption_provider_id,
            "enable_active_reply": enable_active_reply,
            "ar_method": ar_method,
            "ar_possibility": ar_possibility,
            "ar_prompt": ar_prompt,
            "ar_whitelist": ar_whitelist,
            "ar_keywords": ar_keywords,
            "interest_points": interest_points,
            "tiny_model_prov_id": tiny_model_prov_id,
        }
        return ret

    async def append_session_chats(self, event: AstrMessageEvent, cfg) -> None:
        comps = event.get_messages()

        datetime_str = datetime.datetime.now().strftime("%H:%M:%S")
        final_message = f"[{event.message_obj.sender.nickname}/{datetime_str}]: "
        for comp in comps:
            if isinstance(comp, Plain):
                final_message += f" {comp.text}"
            elif isinstance(comp, Image):
                image_url = comp.url if comp.url else comp.file
                if cfg["image_caption"] and image_url:
                    try:
                        caption = await self.get_image_caption(
                            image_url,
                            cfg["image_caption_provider_id"],
                            cfg["image_caption_prompt"],
                        )
                        final_message += f" [Image: {caption}]"
                    except Exception as e:
                        logger.error(f"获取图片描述失败: {e}")
                else:
                    final_message += " [Image]"
        self.session_chats[event.unified_msg_origin].append(final_message)
        logger.debug(f"添加会话 {event.unified_msg_origin} 的对话记录: {final_message}")
        if len(self.session_chats[event.unified_msg_origin]) > cfg["max_cnt"]:
            self.session_chats[event.unified_msg_origin].pop(0)

    async def get_image_caption(
        self, image_url: str, image_caption_provider_id: str, image_caption_prompt: str
    ) -> str:
        if not image_caption_provider_id:
            provider = self.ctx.get_using_provider()
        else:
            provider = self.ctx.get_provider_by_id(image_caption_provider_id)
            if not provider:
                raise Exception(f"没有找到 ID 为 {image_caption_provider_id} 的提供商")
        if not isinstance(provider, Provider):
            raise Exception(
                f"提供商类型错误, {image_caption_provider_id} 不是 Provider 类型"
            )
        response = await provider.text_chat(
            prompt=image_caption_prompt,
            session_id=uuid.uuid4().hex,
            image_urls=[image_url],
            persist=False,
        )
        return response.completion_text

    async def on_event(self, event, soul):
        content = event.content
        astr_event = content.get("astr_event")
        assert astr_event is not None and isinstance(astr_event, AstrMessageEvent)

        cfg = self.cfg(astr_event)

        if not cfg["tiny_model_prov_id"]:
            logger.warning("小模型未设置，跳过情绪更新")

        # 添加对话记录
        await self.append_session_chats(astr_event, cfg)

        #
