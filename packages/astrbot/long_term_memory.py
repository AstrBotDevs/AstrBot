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

"""
聊天记忆增强
"""


class LongTermMemory:
    def __init__(self, config: dict, context: star.Context):
        self.config = config
        self.context = context
        self.session_chats = defaultdict(list)
        """记录群成员的群聊记录"""
        try:
            self.max_cnt = int(self.config["group_message_max_cnt"])
        except BaseException as e:
            logger.error(e)
            self.max_cnt = 300
        self.image_caption = self.config["image_caption"]
        self.image_caption_prompt = self.config["image_caption_prompt"]
        self.image_caption_provider_id = self.config["image_caption_provider_id"]

        self.active_reply = self.config["active_reply"]
        self.enable_active_reply = self.active_reply.get("enable", False)
        self.ar_method = self.active_reply["method"]
        self.ar_possibility = self.active_reply["possibility_reply"]
        self.ar_prompt = self.active_reply.get("prompt", "")
        self.ar_whitelist = self.active_reply.get("whitelist", [])

        # self.put_history_to_prompt = self.config["put_history_to_prompt"]

    async def remove_session(self, event: AstrMessageEvent) -> int:
        cnt = 0
        if event.unified_msg_origin in self.session_chats:
            cnt = len(self.session_chats[event.unified_msg_origin])
            del self.session_chats[event.unified_msg_origin]
        return cnt

    async def get_image_caption(self, image_url: str) -> str:
        if not self.image_caption_provider_id:
            provider = self.context.get_using_provider()
        else:
            provider = self.context.get_provider_by_id(self.image_caption_provider_id)
            if not provider:
                raise Exception(
                    f"没有找到 ID 为 {self.image_caption_provider_id} 的提供商"
                )
        response = await provider.text_chat(
            prompt=self.image_caption_prompt,
            session_id=uuid.uuid4().hex,
            image_urls=[image_url],
            persist=False,
        )
        return response.completion_text

    async def need_active_reply(self, event: AstrMessageEvent) -> bool:
        if not self.enable_active_reply:
            return False
        if event.get_message_type() != MessageType.GROUP_MESSAGE:
            return False

        if event.is_at_or_wake_command:
            # if the message is a command, let it pass
            return False

        if self.ar_whitelist and (
            event.unified_msg_origin not in self.ar_whitelist
            and (event.get_group_id() and event.get_group_id() not in self.ar_whitelist)
        ):
            return False

        match self.ar_method:
            case "possibility_reply":
                trig = random.random() < self.ar_possibility
                return trig

        return False

    async def handle_message(self, event: AstrMessageEvent):
        """仅支持群聊"""
        if event.get_message_type() == MessageType.GROUP_MESSAGE:
            datetime_str = datetime.datetime.now().strftime("%H:%M:%S")

            final_message = f"[{event.message_obj.sender.nickname}/{datetime_str}]: "

            for comp in event.get_messages():
                if isinstance(comp, Plain):
                    final_message += f" {comp.text}"
                elif isinstance(comp, Image):
                    # image_urls.append(comp.url if comp.url else comp.file)
                    if self.image_caption:
                        try:
                            caption = await self.get_image_caption(
                                comp.url if comp.url else comp.file
                            )
                            final_message += f" [Image: {caption}]"
                        except Exception as e:
                            logger.error(f"获取图片描述失败: {e}")
                    else:
                        final_message += " [Image]"
            logger.debug(f"ltm | {event.unified_msg_origin} | {final_message}")
            self.session_chats[event.unified_msg_origin].append(final_message)
            if len(self.session_chats[event.unified_msg_origin]) > self.max_cnt:
                self.session_chats[event.unified_msg_origin].pop(0)

    async def on_req_llm(self, event: AstrMessageEvent, req: ProviderRequest):
        """当触发 LLM 请求前，调用此方法修改 req"""
        if event.unified_msg_origin not in self.session_chats:
            return

        chats_str = "\n---\n".join(self.session_chats[event.unified_msg_origin])

        if self.enable_active_reply:
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
            final_message = f"[AstrBot/{datetime.datetime.now().strftime('%H:%M:%S')}]: {event.get_result().get_plain_text()}"
            logger.debug(f"ltm | {event.unified_msg_origin} | {final_message}")
            self.session_chats[event.unified_msg_origin].append(final_message)
            if len(self.session_chats[event.unified_msg_origin]) > self.max_cnt:
                self.session_chats[event.unified_msg_origin].pop(0)
