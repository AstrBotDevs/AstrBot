from asyncio import Queue

import pytest

from astrbot.core.config.default import CONFIG_METADATA_2
from astrbot.core.config.agent import get_runtime_config_default
from astrbot.core.platform.platform import Platform
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.platform.proxy import create_platform_client_session
from astrbot.core.utils.migra_helper import migrate_config_on_load
from astrbot.dashboard.services.config_service import validate_config


class _ProxyTestPlatform(Platform):
    def run(self):
        raise NotImplementedError

    def meta(self):
        return PlatformMetadata("test", "test", "test")


def test_adapter_proxy_url_preserves_legacy_disabled_behavior():
    adapter = _ProxyTestPlatform({}, Queue())
    assert adapter.proxy_url is None

    adapter.config["proxy"] = {
        "mode": "custom",
        "type": "socks5",
        "address": "127.0.0.1:7891",
    }
    assert adapter.proxy_url == "socks5://127.0.0.1:7891"


def test_adapter_proxy_url_accepts_a_complete_url():
    adapter = _ProxyTestPlatform(
        {
            "proxy": {
                "mode": "custom",
                "type": "http",
                "address": "http://127.0.0.1:7890",
            }
        },
        Queue(),
    )
    assert adapter.proxy_url == "http://127.0.0.1:7890"


def test_proxy_address_is_required_when_enabled():
    config = {
        "platform": [
            {
                "id": "test",
                "proxy": {"mode": "custom", "type": "http", "address": ""},
            }
        ],
        "provider_settings": {},
    }

    errors, _ = validate_config(config, CONFIG_METADATA_2, True, runtime={"os": "linux"})

    assert any("proxy.address" in error for error in errors)


@pytest.mark.parametrize("mode", ["none", None])
def test_proxy_address_is_optional_when_disabled(mode):
    config = {
        "platform": [{"id": "test", "proxy": {"mode": mode}}],
        "provider_settings": {},
    }

    errors, _ = validate_config(config, CONFIG_METADATA_2, True, runtime={"os": "linux"})

    assert not any("proxy.address" in error for error in errors)


def test_legacy_platform_config_gets_proxy_defaults(tmp_path):
    config = {
        "agent": {
            "runtime": "astrbot",
            "config": get_runtime_config_default("astrbot"),
        },
        "config_version": 6,
        "platform": [{"id": "legacy", "type": "telegram"}],
    }

    changed = migrate_config_on_load(config, tmp_path / "config.json")

    assert changed is True
    assert config["platform"][0]["proxy"] == {
        "mode": "none",
        "type": "http",
        "address": "",
    }


@pytest.mark.asyncio
async def test_platform_client_session_keeps_global_proxy_fallback():
    session = create_platform_client_session()
    try:
        assert session.trust_env is True
        assert session._default_proxy is None
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_platform_client_session_uses_adapter_proxy():
    session = create_platform_client_session("http://127.0.0.1:7890")
    try:
        assert str(session._default_proxy) == "http://127.0.0.1:7890"
    finally:
        await session.close()
