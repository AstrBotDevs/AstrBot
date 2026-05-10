import datetime
import random
import uuid
from collections import defaultdict

from astrbot import logger
from astrbot.api import star
from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import At, Image, Plain
from astrbot.api.platform import MessageType
from astrbot.api.provider import LLMResponse, Provider, ProviderRequest
from astrbot.core.agent.message import TextPart
from astrbot.core.astrbot_config_mgr import AstrBotConfigManager

"""
聊天记忆增强
"""


class LongTermMemory:
    DEFAULT_MAX_GROUP_MESSAGES = 50
    DEFAULT_GROUP_ICL_TOKEN_BUDGET = 4000

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
            max_cnt = self.DEFAULT_MAX_GROUP_MESSAGES
        max_cnt = max(1, max_cnt)
        try:
            group_icl_token_budget = int(
                cfg["provider_ltm_settings"].get(
                    "group_icl_token_budget",
                    self.DEFAULT_GROUP_ICL_TOKEN_BUDGET,
                )
            )
        except BaseException as e:
            logger.error(e)
            group_icl_token_budget = self.DEFAULT_GROUP_ICL_TOKEN_BUDGET
        group_icl_token_budget = max(1, group_icl_token_budget)
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
            "group_icl_token_budget": group_icl_token_budget,
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

    @staticmethod
    def _estimate_text_tokens(text: str) -> int:
        chinese_count = len([c for c in text if "\u4e00" <= c <= "\u9fff"])
        other_count = len(text) - chinese_count
        return int(chinese_count * 0.6 + other_count * 0.3)

    def _trim_text_to_token_budget(self, text: str, token_budget: int) -> str:
        marker = "[truncated]\n"
        marker_tokens = self._estimate_text_tokens(marker)
        if self._estimate_text_tokens(text) <= token_budget:
            return text
        if token_budget <= marker_tokens:
            return marker.strip()

        low = 0
        high = len(text)
        best = ""
        target_budget = token_budget - marker_tokens
        while low <= high:
            mid = (low + high) // 2
            candidate = text[-mid:] if mid else ""
            if self._estimate_text_tokens(candidate) <= target_budget:
                best = candidate
                low = mid + 1
            else:
                high = mid - 1
        return f"{marker}{best}"

    def _build_chats_context(
        self,
        chats: list[str],
        token_budget: int,
    ) -> tuple[str, int, int]:
        separator = "\n---\n"
        separator_tokens = self._estimate_text_tokens(separator)
        selected: list[str] = []
        total_tokens = 0

        for chat in reversed(chats):
            chat_tokens = self._estimate_text_tokens(chat)
            extra_tokens = chat_tokens + (separator_tokens if selected else 0)
            if selected and total_tokens + extra_tokens > token_budget:
                break
            if not selected and chat_tokens > token_budget:
                trimmed = self._trim_text_to_token_budget(chat, token_budget)
                return trimmed, len(chats) - 1, self._estimate_text_tokens(trimmed)
            selected.append(chat)
            total_tokens += extra_tokens

        selected.reverse()
        omitted = len(chats) - len(selected)
        chats_str = separator.join(selected)
        if omitted > 0:
            omitted_notice = (
                f"[{omitted} earlier group messages omitted due to token budget]"
            )
            chats_str = f"{omitted_notice}{separator}{chats_str}"
            total_tokens += (
                self._estimate_text_tokens(omitted_notice) + separator_tokens
            )
        return chats_str, omitted, total_tokens

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
            self.session_chats[event.unified_msg_origin].append(final_message)
            if len(self.session_chats[event.unified_msg_origin]) > cfg["max_cnt"]:
                self.session_chats[event.unified_msg_origin].pop(0)

    async def on_req_llm(self, event: AstrMessageEvent, req: ProviderRequest) -> None:
        """当触发 LLM 请求前，调用此方法修改 req"""
        if event.unified_msg_origin not in self.session_chats:
            return

        cfg = self.cfg(event)
        chats_str, omitted, estimated_tokens = self._build_chats_context(
            self.session_chats[event.unified_msg_origin],
            cfg["group_icl_token_budget"],
        )
        if omitted > 0:
            logger.warning(
                "Group ICL context truncated by token budget. umo=%s, omitted=%s, estimated_tokens=%s, budget=%s",
                event.unified_msg_origin,
                omitted,
                estimated_tokens,
                cfg["group_icl_token_budget"],
            )
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
                "\nYou may receive recent group chat context in the current user message. "
                "Use it only as background for this request.\n"
            )
            req.extra_user_content_parts.append(
                TextPart(
                    text=(
                        "[Group Chat Context]\n"
                        "Recent group chat messages, newest messages are kept when truncated:\n"
                        f"{chats_str}"
                    )
                )
            )

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
            self.session_chats[event.unified_msg_origin].append(final_message)
            cfg = self.cfg(event)
            if len(self.session_chats[event.unified_msg_origin]) > cfg["max_cnt"]:
                self.session_chats[event.unified_msg_origin].pop(0)
