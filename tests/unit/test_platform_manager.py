import asyncio

import pytest

from astrbot.core.platform.manager import PlatformManager
from astrbot.core.platform.platform import Platform
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.platform.register import platform_cls_map


class DummyAstrBotConfig(dict):
    def save_config(self, replace_config: dict | None = None) -> None:
        if replace_config is not None:
            self.clear()
            self.update(replace_config)


class DummyPlatform(Platform):
    instances: list["DummyPlatform"] = []

    def __init__(self, platform_config: dict, platform_settings: dict, event_queue):
        super().__init__(platform_config, event_queue)
        self.platform_settings = platform_settings
        self.terminated = False
        self._stop_event = asyncio.Event()
        self.__class__.instances.append(self)

    async def _run(self) -> None:
        await self._stop_event.wait()

    def run(self):
        return self._run()

    async def terminate(self) -> None:
        self.terminated = True
        self._stop_event.set()

    def meta(self) -> PlatformMetadata:
        return PlatformMetadata(
            name="dummy",
            description="dummy platform",
            id=self.config["id"],
            support_proactive_message=False,
        )


@pytest.fixture
def manager(monkeypatch: pytest.MonkeyPatch) -> PlatformManager:
    DummyPlatform.instances.clear()
    monkeypatch.setitem(platform_cls_map, "dummy", DummyPlatform)
    config = DummyAstrBotConfig({"platform": [], "platform_settings": {}})
    return PlatformManager(config, asyncio.Queue())


@pytest.mark.asyncio
async def test_load_platform_replaces_existing_same_id(manager: PlatformManager):
    config = {"id": "default", "type": "dummy", "enable": True}

    await manager.load_platform(config.copy())
    first_inst = DummyPlatform.instances[-1]

    await manager.load_platform(config.copy())
    second_inst = DummyPlatform.instances[-1]

    assert first_inst is not second_inst
    assert first_inst.terminated is True
    assert second_inst.terminated is False
    assert manager._inst_map["default"]["inst"] is second_inst
    assert manager.platform_insts == [second_inst]


@pytest.mark.asyncio
async def test_terminate_platform_cleans_orphaned_instances(manager: PlatformManager):
    config = {"id": "default", "type": "dummy", "enable": True}

    await manager.load_platform(config.copy())
    tracked_inst = DummyPlatform.instances[-1]

    orphan_inst = DummyPlatform(config.copy(), {}, asyncio.Queue())
    manager.platform_insts.append(orphan_inst)
    manager._start_platform_task("orphan_default", orphan_inst)

    await manager.terminate_platform("default")

    assert tracked_inst.terminated is True
    assert orphan_inst.terminated is True
    assert manager.platform_insts == []
    assert "default" not in manager._inst_map
