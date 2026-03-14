from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.builtin_stars.builtin_extension_hub.main import (
    InstallConfirmationIntentFilter,
    Main,
)
from astrbot.core.extensions import InstallResultStatus
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.star.filter.custom_filter import CustomFilter
from astrbot.core.star.filter.permission import PermissionTypeFilter
from astrbot.core.star.star_handler import star_handlers_registry


class _FakeContext:
    def __init__(
        self,
        cfg: dict | None = None,
        conversation_manager=None,
        session_configs: dict[str, dict] | None = None,
    ) -> None:
        self._cfg = cfg or {}
        self.conversation_manager = conversation_manager
        self._session_configs = session_configs or {}

    def get_config(self, umo: str | None = None) -> dict:
        if umo is not None and umo in self._session_configs:
            return self._session_configs[umo]
        return self._cfg


def _build_main(
    config: dict | None = None,
    conversation_manager=None,
    session_configs: dict[str, dict] | None = None,
) -> Main:
    main = Main.__new__(Main)
    main.context = _FakeContext(
        config,
        conversation_manager=conversation_manager,
        session_configs=session_configs,
    )
    return main


def test_detect_confirm_intent_multilingual() -> None:
    main = _build_main()
    assert main._detect_install_intent("yes please proceed") == "confirm"
    assert main._detect_install_intent("好的，继续安装") == "confirm"


def test_detect_deny_intent_multilingual() -> None:
    main = _build_main()
    assert main._detect_install_intent("no, do not install") == "deny"
    assert main._detect_install_intent("不要安装这个") == "deny"


def test_detect_intent_with_custom_keywords() -> None:
    cfg = {
        "provider_settings": {
            "extension_install": {
                "confirm_keyword": "go ahead",
                "deny_keyword": "hold off",
            }
        }
    }
    main = _build_main(cfg)
    assert main._detect_install_intent("go ahead with this install") == "confirm"
    assert main._detect_install_intent("please hold off for now") == "deny"


def test_detect_intent_supports_legacy_keyword_list() -> None:
    cfg = {
        "provider_settings": {
            "extension_install": {
                "confirm_keywords": ["go ahead", "hold off"],
            }
        }
    }
    main = _build_main(cfg)
    assert main._detect_install_intent("go ahead with this install") == "confirm"
    assert main._detect_install_intent("please hold off for now") == "deny"


def test_detect_intent_no_false_positive_from_token() -> None:
    main = _build_main()
    token_like = "anon_token_abcdefghijklmnopqrstuvwxyz"
    assert main._detect_install_intent(token_like) is None


def test_detect_intent_ignores_generic_follow_up_replies() -> None:
    main = _build_main()
    assert main._detect_install_intent("okay, what does this plugin do first?") is None
    assert main._detect_install_intent("可以先介绍一下吗") is None
    assert main._detect_install_intent("no, show me another option") is None


def test_confirmation_candidate_requires_confirmation_intent() -> None:
    main = _build_main()
    assert main._is_install_confirmation_candidate_message(
        "yes proceed with the install"
    )
    assert main._is_install_confirmation_candidate_message("不要安装这个")
    assert not main._is_install_confirmation_candidate_message(
        "I bought a laptop today"
    )


def test_confirmation_candidate_ignored_when_extension_install_disabled() -> None:
    cfg = {
        "provider_settings": {
            "extension_install": {
                "enable": False,
            }
        }
    }
    main = _build_main(cfg)
    assert not main._is_install_confirmation_candidate_message(
        "yes proceed with the install"
    )


def test_confirmation_intent_handler_uses_custom_filter_without_permission_gate() -> None:
    handler = next(
        md
        for md in star_handlers_registry
        if md.handler_full_name.endswith("handle_install_confirmation_intent")
    )

    assert any(isinstance(filter_, CustomFilter) for filter_ in handler.event_filters)
    assert not any(
        isinstance(filter_, PermissionTypeFilter) for filter_ in handler.event_filters
    )


def test_confirmation_filter_does_not_block_short_reply_when_global_install_disabled() -> None:
    filter_ = InstallConfirmationIntentFilter()
    event = MagicMock(spec=AstrMessageEvent)
    event.get_message_str.return_value = "点头"
    event.role = "admin"

    assert filter_.filter(
        event,
        {
            "provider_settings": {
                "extension_install": {
                    "enable": False,
                }
            }
        },
    )


def test_confirmation_candidate_allows_owner_custom_keywords() -> None:
    cfg = {
        "provider_settings": {
            "extension_install": {
                "enable": True,
                "confirm_keyword": "go ahead",
                "deny_keyword": "hold off",
                "allowed_roles": ["admin", "owner"],
            }
        }
    }
    main = _build_main(cfg)
    assert main._is_install_confirmation_candidate_message("go ahead with install")


def test_confirmation_candidate_uses_session_scoped_config() -> None:
    main = _build_main(
        {
            "provider_settings": {
                "extension_install": {
                    "enable": True,
                }
            }
        },
        session_configs={
            "conv-1": {
                "provider_settings": {
                    "extension_install": {
                        "enable": False,
                    }
                }
            }
        },
    )
    assert not main._is_install_confirmation_candidate_message(
        "yes proceed with the install",
        umo="conv-1",
    )


def test_detect_intent_uses_session_scoped_keywords() -> None:
    main = _build_main(
        {
            "provider_settings": {
                "extension_install": {
                    "confirm_keyword": "确认安装",
                    "deny_keyword": "拒绝安装",
                }
            }
        },
        session_configs={
            "conv-1": {
                "provider_settings": {
                    "extension_install": {
                        "confirm_keyword": "点头",
                        "deny_keyword": "算了",
                    }
                }
            }
        },
    )
    assert main._detect_install_intent("点头", umo="conv-1") == "confirm"
    assert main._detect_install_intent("算了", umo="conv-1") == "deny"


@pytest.mark.asyncio
async def test_confirm_intent_syncs_install_result_to_conversation_history(
    monkeypatch,
) -> None:
    conversation_manager = SimpleNamespace(
        get_curr_conversation_id=AsyncMock(return_value="cid-1"),
        add_message_pair=AsyncMock(),
    )
    main = _build_main(
        {
            "provider_settings": {
                "extension_install": {
                    "enable": True,
                }
            }
        },
        conversation_manager=conversation_manager,
    )
    orchestrator = SimpleNamespace(
        pending_service=SimpleNamespace(
            get_active_by_conversation=AsyncMock(
                return_value=SimpleNamespace(
                    kind="plugin",
                    target="https://github.com/example/demo",
                )
            )
        ),
        confirm_for_conversation=AsyncMock(
            return_value=SimpleNamespace(
                status=InstallResultStatus.SUCCESS,
                message="install completed",
            )
        ),
        deny_for_conversation=AsyncMock(),
    )
    monkeypatch.setattr(
        "astrbot.builtin_stars.builtin_extension_hub.main.get_extension_orchestrator",
        lambda *args, **kwargs: orchestrator,
    )
    event = MagicMock(spec=AstrMessageEvent)
    event.get_message_str.return_value = "确认安装"
    event.unified_msg_origin = "conv-1"
    event.get_sender_id.return_value = "u1"
    event.role = "admin"

    await main.handle_install_confirmation_intent(event)

    conversation_manager.get_curr_conversation_id.assert_awaited_once_with("conv-1")
    conversation_manager.add_message_pair.assert_awaited_once()
    cid, user_message, assistant_message = (
        conversation_manager.add_message_pair.await_args.args
    )
    assert cid == "cid-1"
    assert user_message == {"role": "user", "content": "确认安装"}
    assert assistant_message == {
        "role": "assistant",
        "content": (
            "Confirmed [plugin] https://github.com/example/demo, install completed."
        ),
    }


@pytest.mark.asyncio
async def test_deny_intent_syncs_rejection_to_conversation_history(monkeypatch) -> None:
    conversation_manager = SimpleNamespace(
        get_curr_conversation_id=AsyncMock(return_value="cid-1"),
        add_message_pair=AsyncMock(),
    )
    main = _build_main(
        {
            "provider_settings": {
                "extension_install": {
                    "enable": True,
                }
            }
        },
        conversation_manager=conversation_manager,
    )
    orchestrator = SimpleNamespace(
        pending_service=SimpleNamespace(
            get_active_by_conversation=AsyncMock(
                return_value=SimpleNamespace(
                    kind="plugin",
                    target="https://github.com/example/demo",
                )
            )
        ),
        confirm_for_conversation=AsyncMock(),
        deny_for_conversation=AsyncMock(
            return_value=SimpleNamespace(
                status=InstallResultStatus.DENIED,
                data={"count": 1},
            )
        ),
    )
    monkeypatch.setattr(
        "astrbot.builtin_stars.builtin_extension_hub.main.get_extension_orchestrator",
        lambda *args, **kwargs: orchestrator,
    )
    event = MagicMock(spec=AstrMessageEvent)
    event.get_message_str.return_value = "拒绝安装"
    event.unified_msg_origin = "conv-1"
    event.get_sender_id.return_value = "u1"
    event.role = "admin"

    await main.handle_install_confirmation_intent(event)

    conversation_manager.get_curr_conversation_id.assert_awaited_once_with("conv-1")
    conversation_manager.add_message_pair.assert_awaited_once()
    cid, user_message, assistant_message = (
        conversation_manager.add_message_pair.await_args.args
    )
    assert cid == "cid-1"
    assert user_message == {"role": "user", "content": "拒绝安装"}
    assert assistant_message == {
        "role": "assistant",
        "content": (
            "Rejected 1 pending install request(s) for "
            "[plugin] https://github.com/example/demo."
        ),
    }
