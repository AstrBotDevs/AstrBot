import datetime
import random
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Literal

from astrbot import logger
from astrbot.api import star
from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import At, Image, Plain
from astrbot.api.platform import MessageType
from astrbot.api.provider import LLMResponse, Provider, ProviderRequest
from astrbot.core.astrbot_config_mgr import AstrBotConfigManager


@dataclass
class ChatRecord:
    """单条聊天记录，用于长期记忆存储。"""

    msg_id: str
    """消息唯一标识（用户消息取 message_obj.message_id，AI 回复取 'ai:<uuid>'）"""
    role: Literal["user", "assistant"]
    """角色：user 表示用户消息，assistant 表示 AI 回复"""
    text: str
    """格式化后的文本，如 '[昵称/HH:MM:SS]: ...' 或 '[You/HH:MM:SS]: ...'"""
    created_at: str = field(default_factory=lambda: datetime.datetime.now().isoformat())
    """创建时间（ISO 格式），用于调试/扩展"""


def _get_event_msg_id(event: AstrMessageEvent) -> str:
    """
    获取当前事件对应的消息 ID。
    以保证同一事件链路（handle_message -> on_req_llm -> after_req_llm）使用同一 ID。
    """
    msg_id = getattr(event.message_obj, "message_id", None)
    if msg_id:
        return str(msg_id)
    # fallback: 使用 extra 缓存
    cached = event.get_extra("_ltm_msg_id")
    if cached:
        return cached
    generated = f"ltm:{uuid.uuid4().hex}"
    event.set_extra("_ltm_msg_id", generated)
    return generated


class LongTermMemory:
    def __init__(self, acm: AstrBotConfigManager, context: star.Context) -> None:
        self.acm = acm
        self.context = context
        self.session_chats = defaultdict(list)
        """记录群成员的群聊记录"""

    def cfg(self, event: AstrMessageEvent):
        cfg = self.context.get_config(umo=event.unified_msg_origin)
        try:
            max_cnt = int(cfg["provider_ltm_settings"]["group_message_max_cnt"])
        except BaseException as e:
            logger.error(e)
            max_cnt = 300
        image_caption_prompt = cfg["provider_settings"]["image_caption_prompt"]
        image_caption_provider_id = cfg["provider_ltm_settings"].get(
            "image_caption_provider_id"
        )
        image_caption = cfg["provider_ltm_settings"]["image_caption"] and bool(
            image_caption_provider_id
        )
        active_reply = cfg["provider_ltm_settings"]["active_reply"]
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
        self,
        image_url: str,
        image_caption_provider_id: str,
        image_caption_prompt: str,
    ) -> str:
        if not image_caption_provider_id:
            provider = self.context.get_using_provider()
        else:
            provider = self.context.get_provider_by_id(image_caption_provider_id)
            if not provider:
                raise Exception(f"没有找到 ID 为 {image_caption_provider_id} 的提供商")
        if not isinstance(provider, Provider):
            raise Exception(f"提供商类型错误({type(provider)})，无法获取图片描述")
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
            and (
                event.get_group_id() and event.get_group_id() not in cfg["ar_whitelist"]
            )
        ):
            return False

        match cfg["ar_method"]:
            case "possibility_reply":
                trig = random.random() < cfg["ar_possibility"]
                return trig

        return False

    async def handle_message(self, event: AstrMessageEvent) -> None:
        """仅支持群聊"""
        if event.get_message_type() == MessageType.GROUP_MESSAGE:
            datetime_str = datetime.datetime.now().strftime("%H:%M:%S")

            parts = [f"[{event.message_obj.sender.nickname}/{datetime_str}]: "]

            cfg = self.cfg(event)

            for comp in event.get_messages():
                if isinstance(comp, Plain):
                    parts.append(f" {comp.text}")
                elif isinstance(comp, Image):
                    if cfg["image_caption"]:
                        try:
                            url = comp.url if comp.url else comp.file
                            if not url:
                                raise Exception("图片 URL 为空")
                            caption = await self.get_image_caption(
                                url,
                                cfg["image_caption_provider_id"],
                                cfg["image_caption_prompt"],
                            )
                            parts.append(f" [Image: {caption}]")
                        except Exception as e:
                            logger.error(f"获取图片描述失败: {e}")
                    else:
                        parts.append(" [Image]")
                elif isinstance(comp, At):
                    parts.append(f" [At: {comp.name}]")

            final_message = "".join(parts)
            logger.debug(f"ltm | {event.unified_msg_origin} | {final_message}")

            msg_id = _get_event_msg_id(event)
            record = ChatRecord(msg_id=msg_id, role="user", text=final_message)
            self.session_chats[event.unified_msg_origin].append(record)

            if len(self.session_chats[event.unified_msg_origin]) > cfg["max_cnt"]:
                self.session_chats[event.unified_msg_origin].pop(0)

    async def on_req_llm(self, event: AstrMessageEvent, req: ProviderRequest) -> None:
        """当触发 LLM 请求前，调用此方法修改 req"""
        if event.unified_msg_origin not in self.session_chats:
            return

        current_msg_id = _get_event_msg_id(event)

        # 构造历史字符串时按 msg_id 过滤当前轮消息
        history_records: list[ChatRecord] = self.session_chats[event.unified_msg_origin]
        filtered_texts = [
            rec.text for rec in history_records if rec.msg_id != current_msg_id
        ]
        chats_str = "\n---\n".join(filtered_texts)

        cfg = self.cfg(event)
        if cfg["enable_active_reply"]:
            prompt = req.prompt
            req.prompt = (
                f"You are now in a chatroom. The chat history is as follows:\n{chats_str}"
                f"\nNow, a new message is coming: `{prompt}`. "
                "Please react to it. Only output your response and do not output any other information. "
                "You MUST use the SAME language as the chatroom is using."
            )
            req.contexts = []  # 清空上下文，当使用了主动回复，所有聊天记录都在一个prompt中。
        else:
            req.system_prompt += (
                "You are now in a chatroom. The chat history is as follows: \n"
            )
            req.system_prompt += chats_str

    async def after_req_llm(
        self, event: AstrMessageEvent, llm_resp: LLMResponse
    ) -> None:
        if event.unified_msg_origin not in self.session_chats:
            return

        if llm_resp.completion_text:
            final_message = f"[You/{datetime.datetime.now().strftime('%H:%M:%S')}]: {llm_resp.completion_text}"
            logger.debug(
                f"Recorded AI response: {event.unified_msg_origin} | {final_message}"
            )

            ai_msg_id = f"ai:{uuid.uuid4().hex}"
            record = ChatRecord(msg_id=ai_msg_id, role="assistant", text=final_message)
            self.session_chats[event.unified_msg_origin].append(record)

            cfg = self.cfg(event)
            if len(self.session_chats[event.unified_msg_origin]) > cfg["max_cnt"]:
                self.session_chats[event.unified_msg_origin].pop(0)
