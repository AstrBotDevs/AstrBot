from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageEventResult, filter
from astrbot.core.extensions import InstallResultStatus
from astrbot.core.extensions.runtime import (
    get_extension_confirm_keywords,
    get_extension_orchestrator,
    is_extension_install_enabled,
)
from astrbot.core.star.filter.custom_filter import CustomFilter


def _get_extension_confirm_keywords_from_config(
    config: dict,
) -> tuple[str, str]:
    return get_extension_confirm_keywords(config)


def _normalize_intent_text(raw_text: str) -> str:
    text = raw_text.lower()
    for ch in [",", ".", "!", "?", "，", "。", "！", "？", "；", ";", "：", ":"]:
        text = text.replace(ch, " ")
    return " ".join(text.split())


def _contains_intent_word(normalized: str, word: str) -> bool:
    if not word:
        return False
    is_ascii_word = all(
        ch.isascii() and (ch.isalnum() or ch in {"_", "-"}) for ch in word
    )
    if not is_ascii_word:
        return word in normalized
    parts = normalized.split()
    return word in parts


def _is_allowed_confirmation_role(config: dict, role: str) -> bool:
    provider_settings = config.get("provider_settings", {})
    extension_cfg = provider_settings.get("extension_install", {})
    allowed_roles = extension_cfg.get("allowed_roles", ["admin", "owner"])
    if not isinstance(allowed_roles, list):
        return False
    return role in {str(item).strip() for item in allowed_roles}


def _detect_install_intent_from_config(
    config: dict,
    raw_text: str,
    confirm_words: set[str],
    deny_words: set[str],
) -> str | None:
    normalized = _normalize_intent_text(raw_text)
    confirm_keyword, deny_keyword = _get_extension_confirm_keywords_from_config(config)

    deny_words = deny_words | {deny_keyword.lower()}
    confirm_words = confirm_words | {confirm_keyword.lower()}

    has_deny = any(_contains_intent_word(normalized, word) for word in deny_words)
    has_confirm = any(_contains_intent_word(normalized, word) for word in confirm_words)
    if has_deny and has_confirm:
        return None
    if has_deny:
        return "deny"
    if has_confirm:
        return "confirm"
    return None


class InstallConfirmationIntentFilter(CustomFilter):
    def filter(self, event: AstrMessageEvent, cfg: dict) -> bool:
        if not is_extension_install_enabled(cfg):
            return False
        if not _is_allowed_confirmation_role(cfg, event.role):
            return False
        raw_text = event.get_message_str().strip()
        if raw_text.startswith("/"):
            return False
        return (
            _detect_install_intent_from_config(
                cfg,
                raw_text,
                Main._CONFIRM_WORDS,
                Main._DENY_WORDS,
            )
            is not None
        )


class Main(star.Star):
    _DENY_WORDS = frozenset(
        {
            "deny",
            "denied",
            "reject",
            "rejected",
            "cancel",
            "abort",
            "stop",
            "no",
            "refuse",
            "拒绝",
            "取消",
            "不要",
            "不同意",
            "否认",
            "停止",
        }
    )
    _CONFIRM_WORDS = frozenset(
        {
            "confirm",
            "confirmed",
            "approve",
            "approved",
            "accept",
            "accepted",
            "allow",
            "proceed",
            "yes",
            "ok",
            "okay",
            "sure",
            "确认",
            "同意",
            "批准",
            "允许",
            "继续",
            "可以",
            "好的",
            "行",
        }
    )

    def __init__(self, context: star.Context) -> None:
        self.context = context

    def _is_extension_install_enabled(self) -> bool:
        return is_extension_install_enabled(self.context.get_config())

    def _get_extension_confirm_keywords(self) -> tuple[str, str]:
        return _get_extension_confirm_keywords_from_config(self.context.get_config())

    def _detect_install_intent(self, raw_text: str) -> str | None:
        return _detect_install_intent_from_config(
            self.context.get_config(),
            raw_text,
            self._CONFIRM_WORDS,
            self._DENY_WORDS,
        )

    def _is_install_confirmation_candidate_message(self, raw_text: str) -> bool:
        if not self._is_extension_install_enabled():
            return False
        if raw_text.startswith("/"):
            return False
        return self._detect_install_intent(raw_text) is not None

    async def _append_install_result_to_conversation(
        self,
        *,
        unified_msg_origin: str,
        user_message: str,
        assistant_message: str,
    ) -> None:
        conversation_manager = getattr(self.context, "conversation_manager", None)
        if conversation_manager is None:
            return

        conversation_id = await conversation_manager.get_curr_conversation_id(
            unified_msg_origin
        )
        if not conversation_id:
            return

        await conversation_manager.add_message_pair(
            conversation_id,
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": assistant_message},
        )

    @filter.custom_filter(InstallConfirmationIntentFilter, False)
    async def handle_install_confirmation_intent(self, event: AstrMessageEvent) -> None:
        """Natural-language intent based install confirmation/rejection."""
        message = event.get_message_str().strip()
        if not self._is_install_confirmation_candidate_message(message):
            return

        orchestrator = get_extension_orchestrator(self.context)
        pending = await orchestrator.pending_service.get_active_by_conversation(
            event.unified_msg_origin
        )
        if pending is None:
            return

        intent = self._detect_install_intent(message)
        if intent is None:
            return

        target_label = f"[{pending.kind}] {pending.target}"
        if intent == "confirm":
            result = await orchestrator.confirm_for_conversation(
                conversation_id=event.unified_msg_origin,
                actor_id=event.get_sender_id(),
                actor_role=event.role,
            )
            if result.status == InstallResultStatus.SUCCESS:
                assistant_message = f"Confirmed {target_label}, install completed."
                await self._append_install_result_to_conversation(
                    unified_msg_origin=event.unified_msg_origin,
                    user_message=message,
                    assistant_message=assistant_message,
                )
                event.set_result(MessageEventResult().message(assistant_message))
            elif result.status != InstallResultStatus.FAILED:
                assistant_message = f"Confirmation denied: {result.message}"
                await self._append_install_result_to_conversation(
                    unified_msg_origin=event.unified_msg_origin,
                    user_message=message,
                    assistant_message=assistant_message,
                )
                event.set_result(MessageEventResult().message(assistant_message))
        elif intent == "deny":
            result = await orchestrator.deny_for_conversation(
                conversation_id=event.unified_msg_origin,
                actor_id=event.get_sender_id(),
                actor_role=event.role,
                reason="rejected by chat confirmation",
            )
            if result.status == InstallResultStatus.DENIED:
                count = result.data.get("count", 1)
                assistant_message = (
                    f"Rejected {count} pending install request(s) for {target_label}."
                )
                await self._append_install_result_to_conversation(
                    unified_msg_origin=event.unified_msg_origin,
                    user_message=message,
                    assistant_message=assistant_message,
                )
                event.set_result(MessageEventResult().message(assistant_message))
