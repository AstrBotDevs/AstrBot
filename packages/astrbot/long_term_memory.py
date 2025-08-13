import datetime
import uuid
import random
import astrbot.api.star as star
from astrbot.api.event import AstrMessageEvent
from astrbot.api.platform import MessageType
from astrbot.api.provider import ProviderRequest
from astrbot.api.message_components import Plain, Image
from astrbot import logger
from collections import defaultdict
from astrbot.core.astrbot_config_mgr import AstrBotConfigManager

"""
聊天记忆增强
"""


class LongTermMemory:
    def __init__(self, acm: AstrBotConfigManager, context: star.Context):
        self.acm = acm
        self.context = context
        self.session_chats = defaultdict(list)
        """记录群成员的群聊记录"""

    def cfg(self, event: AstrMessageEvent):
        cfg = self.context.get_config(umo=event.unified_msg_origin)
        try:
            max_cnt = int(cfg["group_message_max_cnt"])
        except BaseException as e:
            logger.error(e)
            max_cnt = 300
        image_caption = cfg["image_caption"]
        image_caption_prompt = cfg["image_caption_prompt"]
        image_caption_provider_id = cfg["image_caption_provider_id"]
        active_reply = cfg["active_reply"]
        enable_active_reply = active_reply.get("enable", False)
        ar_method = active_reply["method"]
        ar_possibility = active_reply["possibility_reply"]
        ar_prompt = active_reply.get("prompt", "")
        ar_whitelist = active_reply.get("whitelist", [])
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
        }
        return ret

    async def remove_session(self, event: AstrMessageEvent) -> int:
        cnt = 0
        if event.unified_msg_origin in self.session_chats:
            cnt = len(self.session_chats[event.unified_msg_origin])
            del self.session_chats[event.unified_msg_origin]
        return cnt

    async def get_image_caption(
        self, image_url: str, image_caption_provider_id: str, image_caption_prompt: str
    ) -> str:
        if not image_caption_provider_id:
            provider = self.context.get_using_provider()
        else:
            provider = self.context.get_provider_by_id(image_caption_provider_id)
            if not provider:
                raise Exception(f"没有找到 ID 为 {image_caption_provider_id} 的提供商")
        response = await provider.text_chat(
            prompt=image_caption_prompt,
            session_id=uuid.uuid4().hex,
            image_urls=[image_url],
            persist=False,
        )
        return response.completion_text

    async def need_active_reply(self, event: AstrMessageEvent) -> bool:
        cfg = self.cfg(event)
        if not cfg["enable_active_reply"]:
            return False
        if event.get_message_type() != MessageType.GROUP_MESSAGE:
            return False

        if event.is_at_or_wake_command:
            # if the message is a command, let it pass
            return False

        if cfg["ar_whitelist"] and (
            event.unified_msg_origin not in cfg["ar_whitelist"]
            and (event.get_group_id() and event.get_group_id() not in cfg["ar_whitelist"])
        ):
            return False

        match cfg["ar_method"]:
            case "possibility_reply":
                trig = random.random() < cfg["ar_possibility"]
                return trig

        return False

    async def handle_message(self, event: AstrMessageEvent):
        """仅支持群聊"""
        if event.get_message_type() == MessageType.GROUP_MESSAGE:
            datetime_str = datetime.datetime.now().strftime("%H:%M:%S")

            final_message = f"[{event.message_obj.sender.nickname}/{datetime_str}]: "

            cfg = self.cfg(event)

            for comp in event.get_messages():
                if isinstance(comp, Plain):
                    final_message += f" {comp.text}"
                elif isinstance(comp, Image):
                    cfg = self.cfg(event)
                    if cfg["image_caption"]:
                        try:
                            caption = await self.get_image_caption(
                                comp.url if comp.url else comp.file,
                                cfg["image_caption_provider_id"],
                                cfg["image_caption_prompt"],
                            )
                            final_message += f" [Image: {caption}]"
                        except Exception as e:
                            logger.error(f"获取图片描述失败: {e}")
                    else:
                        final_message += " [Image]"
            logger.debug(f"ltm | {event.unified_msg_origin} | {final_message}")
            self.session_chats[event.unified_msg_origin].append(final_message)
            if len(self.session_chats[event.unified_msg_origin]) > cfg["max_cnt"]:
                self.session_chats[event.unified_msg_origin].pop(0)

    async def on_req_llm(self, event: AstrMessageEvent, req: ProviderRequest):
        """当触发 LLM 请求前，调用此方法修改 req"""
        if event.unified_msg_origin not in self.session_chats:
            return

        chats_str = "\n---\n".join(self.session_chats[event.unified_msg_origin])

        cfg = self.cfg(event)
        if cfg["enable_active_reply"]:
            prompt = req.prompt
            req.prompt = f"You are now in a chatroom. The chat history is as follows:\n{chats_str}"
            req.prompt += f"\nNow, a new message is coming: `{prompt}`. Please react to it. Only output your response and do not output any other information."
            req.contexts = []  # 清空上下文，当使用了主动回复，所有聊天记录都在一个prompt中。
        else:
            req.system_prompt += (
                "You are now in a chatroom. The chat history is as follows: \n"
            )
            req.system_prompt += chats_str

    async def after_req_llm(self, event: AstrMessageEvent):
        if event.unified_msg_origin not in self.session_chats:
            return

        if event.get_result() and event.get_result().is_llm_result():
            final_message = f"[You/{datetime.datetime.now().strftime('%H:%M:%S')}]: {event.get_result().get_plain_text()}"
            logger.debug(f"ltm | {event.unified_msg_origin} | {final_message}")
            self.session_chats[event.unified_msg_origin].append(final_message)
            cfg = self.cfg(event)
            if len(self.session_chats[event.unified_msg_origin]) > cfg["max_cnt"]:
                self.session_chats[event.unified_msg_origin].pop(0)
