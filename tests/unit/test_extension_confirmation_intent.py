from __future__ import annotations

from astrbot.builtin_stars.builtin_extension_hub.main import Main


class _FakeContext:
    def __init__(self, cfg: dict | None = None) -> None:
        self._cfg = cfg or {}

    def get_config(self) -> dict:
        return self._cfg


def _build_main(config: dict | None = None) -> Main:
    main = Main.__new__(Main)
    main.context = _FakeContext(config)
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
