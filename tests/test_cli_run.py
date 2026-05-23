from astrbot.core.utils.env_template import expand_env_placeholders


def test_expand_service_config_path_supports_defaults(monkeypatch):
    monkeypatch.delenv("ASTRBOT_INSTANCE", raising=False)

    assert (
        expand_env_placeholders("/etc/astrbot/${ASTRBOT_INSTANCE:-default}.env")
        == "/etc/astrbot/default.env"
    )


def test_expand_service_config_path_prefers_environment(monkeypatch):
    monkeypatch.setenv("ASTRBOT_INSTANCE", "light")

    assert (
        expand_env_placeholders("/etc/astrbot/${ASTRBOT_INSTANCE:-default}.env")
        == "/etc/astrbot/light.env"
    )
