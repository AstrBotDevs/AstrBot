from astrbot.cli.commands.cmd_run import _expand_env_parameter_value


def test_expand_service_config_path_supports_defaults(monkeypatch):
    monkeypatch.delenv("ASTRBOT_INSTANCE", raising=False)

    assert (
        _expand_env_parameter_value("/etc/astrbot/${ASTRBOT_INSTANCE:-default}.env")
        == "/etc/astrbot/default.env"
    )


def test_expand_service_config_path_prefers_environment(monkeypatch):
    monkeypatch.setenv("ASTRBOT_INSTANCE", "light")

    assert (
        _expand_env_parameter_value("/etc/astrbot/${ASTRBOT_INSTANCE:-default}.env")
        == "/etc/astrbot/light.env"
    )
