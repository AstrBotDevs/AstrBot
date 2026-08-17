from astrbot.core.platform.sources.webchat.request_flags import (
    resolve_webchat_request_flags,
)


def test_webchat_request_flags_use_defaults():
    flags = resolve_webchat_request_flags({})

    assert flags == {
        "enable_inline_genui": True,
        "enable_default_system_prompt": True,
        "enable_streaming": True,
    }


def test_webchat_request_flags_prefer_nested_flags():
    flags = resolve_webchat_request_flags(
        {
            "enable_streaming": False,
            "flags": {
                "enable_inline_genui": False,
                "enable_default_system_prompt": False,
                "enable_streaming": True,
            },
        }
    )

    assert flags == {
        "enable_inline_genui": False,
        "enable_default_system_prompt": False,
        "enable_streaming": True,
    }


def test_webchat_request_flags_keep_legacy_streaming_fallback():
    flags = resolve_webchat_request_flags({"enable_streaming": False})

    assert flags["enable_streaming"] is False
