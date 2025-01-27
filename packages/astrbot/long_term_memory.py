import datetime
import uuid
import astrbot.api.star as star
from astrbot.api.event import AstrMessageEvent
from astrbot.api.platform import MessageType
from astrbot.api.provider import ProviderRequest
from astrbot.api.message_components import Plain, Image
from astrbot import logger
from collections import defaultdict


class LongTermMemory:
    def __init__(self, config: dict, context: star.Context):
        self.config = config
        self.context = context
        self.session_chats = defaultdict(list)
        """记录群成员的群聊记录"""
        self.max_cnt = self.config["group_message_max_cnt"]
        self.image_caption = self.config["image_caption"]
        self.image_caption_prompt = self.config["image_caption_prompt"]
        
    async def remove_session(self, event: AstrMessageEvent) -> int:
        cnt = 0
        if event.unified_msg_origin in self.session_chats:
            cnt = len(self.session_chats[event.unified_msg_origin])
            del self.session_chats[event.unified_msg_origin]
        return cnt

    async def get_image_caption(self, image_url: str) -> str:
        provider = self.context.get_using_provider()
        response = await provider.text_chat(
            prompt=self.image_caption_prompt,
            session_id=uuid.uuid4().hex,
            image_urls=[image_url],
            persist=False,
        )
        return response.completion_text

    async def handle_message(self, event: AstrMessageEvent):
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
            logger.debug(f"ltm | {event.unified_msg_origin} | {final_message}")
            self.session_chats[event.unified_msg_origin].append(final_message)
            if len(self.session_chats[event.unified_msg_origin]) > self.max_cnt:
                self.session_chats[event.unified_msg_origin].pop(0)

    async def on_req_llm(self, event: AstrMessageEvent, req: ProviderRequest):
        if event.unified_msg_origin not in self.session_chats:
            return
        
        chats_str = '\n---\n'.join(self.session_chats[event.unified_msg_origin])
        req.system_prompt += "You are now in a chatroom. The chat history is as follows: \n"
        req.system_prompt += chats_str
        if self.image_caption:
            req.system_prompt += (
                "The images sent by the members are displayed in text form above."
            )

    async def after_req_llm(self, event: AstrMessageEvent):
        if event.unified_msg_origin not in self.session_chats:
            return

        if event.get_result() and event.get_result().is_llm_result():
            final_message = f"[AstrBot/{datetime.datetime.now().strftime('%H:%M:%S')}]: {event.get_result().get_plain_text()}"
            logger.debug(f"ltm | {event.unified_msg_origin} | {final_message}")
            self.session_chats[event.unified_msg_origin].append(final_message)
            if len(self.session_chats[event.unified_msg_origin]) > self.max_cnt:
                self.session_chats[event.unified_msg_origin].pop(0)
