import asyncio

import pytest


class FakeContext:
    def __init__(self, config: dict):
        self._config = config

    def get_config(self, umo: str | None = None):
        return self._config


def test_cua_sandbox_provider_builds_config_from_runtime_settings():
    from astrbot.core.computer.cua_sandbox_provider import CuaSandboxProvider

    provider = CuaSandboxProvider()
    config = provider.build_create_config(
        FakeContext(
            {
                "provider_settings": {
                    "sandbox": {
                        "cua_image": "linux",
                        "cua_os_type": "linux",
                        "cua_ttl": 123,
                        "cua_local": False,
                        "cua_api_key": "sk-test",
                    }
                }
            }
        ),
        "session-a",
    )

    assert provider.provider_id == "cua"
    assert config["image"] == "linux"
    assert config["ttl"] == 123
    assert config["local"] is False
    assert config["api_key"] == "sk-test"


@pytest.mark.asyncio
async def test_cua_sandbox_provider_creates_booter_and_syncs_skills(monkeypatch):
    from astrbot.core.computer import cua_sandbox_provider
    from astrbot.core.computer.booters import cua as cua_booter
    from astrbot.core.computer.cua_sandbox_provider import CuaSandboxProvider

    synced = []

    class FakeCuaBooter:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def boot(self, session_id: str):
            self.boot_session_id = session_id

        async def available(self):
            return True

    monkeypatch.setattr(cua_booter, "CuaBooter", FakeCuaBooter)
    monkeypatch.setattr(
        cua_sandbox_provider,
        "_sync_skills_to_sandbox",
        lambda booter: synced.append(booter) or asyncio.sleep(0),
    )

    booter = await CuaSandboxProvider().create_booter(
        FakeContext({}),
        "session-a",
        "sb-1",
        {"image": "linux", "os_type": "linux", "local": False, "ttl": 3600},
    )

    assert isinstance(booter, FakeCuaBooter)
    assert booter.sandbox_id == "sb-1"
    assert synced == [booter]


@pytest.mark.asyncio
async def test_cua_sandbox_provider_shuts_down_when_skill_sync_fails(monkeypatch):
    from astrbot.core.computer import cua_sandbox_provider
    from astrbot.core.computer.booters import cua as cua_booter
    from astrbot.core.computer.cua_sandbox_provider import CuaSandboxProvider

    shutdowns = []

    class FakeCuaBooter:
        async def boot(self, session_id: str):
            return None

        async def shutdown(self):
            shutdowns.append(True)

    async def fail_sync(booter):
        raise RuntimeError("sync failed")

    monkeypatch.setattr(cua_booter, "CuaBooter", lambda **kwargs: FakeCuaBooter())
    monkeypatch.setattr(cua_sandbox_provider, "_sync_skills_to_sandbox", fail_sync)

    with pytest.raises(RuntimeError, match="sync failed"):
        await CuaSandboxProvider().create_booter(
            FakeContext({}),
            "session-a",
            "sb-1",
            {"image": "linux", "os_type": "linux", "local": False, "ttl": 3600},
        )

    assert shutdowns == [True]
