from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageEventResult, filter
from astrbot.core.extensions import InstallResultStatus
from astrbot.core.extensions.runtime import (
    get_extension_orchestrator,
    is_extension_install_enabled,
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
        config = self.context.get_config()
        provider_settings = config.get("provider_settings", {})
        extension_cfg = provider_settings.get("extension_install", {})
        keywords = extension_cfg.get("confirm_keywords", [])
        if isinstance(keywords, list) and len(keywords) >= 2:
            confirm_keyword = str(keywords[0]).strip() or "确认安装"
            deny_keyword = str(keywords[1]).strip() or "拒绝安装"
            return confirm_keyword, deny_keyword
        return "确认安装", "拒绝安装"

    @staticmethod
    def _normalize_intent_text(raw_text: str) -> str:
        text = raw_text.lower()
        for ch in [",", ".", "!", "?", "，", "。", "！", "？", "；", ";", "：", ":"]:
            text = text.replace(ch, " ")
        return " ".join(text.split())

    @staticmethod
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

    def _detect_install_intent(self, raw_text: str) -> str | None:
        normalized = self._normalize_intent_text(raw_text)
        confirm_keyword, deny_keyword = self._get_extension_confirm_keywords()

        deny_words = self._DENY_WORDS | {deny_keyword.lower()}
        confirm_words = self._CONFIRM_WORDS | {confirm_keyword.lower()}

        has_deny = any(
            self._contains_intent_word(normalized, word) for word in deny_words
        )
        has_confirm = any(
            self._contains_intent_word(normalized, word) for word in confirm_words
        )
        if has_deny and has_confirm:
            return None
        if has_deny:
            return "deny"
        if has_confirm:
            return "confirm"
        return None

    def _is_install_confirmation_candidate_message(self, raw_text: str) -> bool:
        if not self._is_extension_install_enabled():
            return False
        if raw_text.startswith("/"):
            return False
        return self._detect_install_intent(raw_text) is not None

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.regex(r"^.+$")
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
                event.set_result(
                    MessageEventResult().message(
                        f"Confirmed {target_label}, install completed."
                    )
                )
            elif result.status != InstallResultStatus.FAILED:
                event.set_result(
                    MessageEventResult().message(
                        f"Confirmation denied: {result.message}"
                    )
                )
        elif intent == "deny":
            result = await orchestrator.deny_for_conversation(
                conversation_id=event.unified_msg_origin,
                actor_id=event.get_sender_id(),
                actor_role=event.role,
                reason="rejected by chat confirmation",
            )
            if result.status == InstallResultStatus.DENIED:
                count = result.data.get("count", 1)
                event.set_result(
                    MessageEventResult().message(
                        f"Rejected {count} pending install request(s) for {target_label}."
                    )
                )
