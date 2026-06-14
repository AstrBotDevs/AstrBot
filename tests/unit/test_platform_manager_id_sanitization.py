from asyncio import Queue
from unittest.mock import MagicMock

import pytest

from astrbot.core.platform.manager import PlatformManager, platform_cls_map
from astrbot.core.platform.platform import Platform
from astrbot.core.platform.platform_metadata import PlatformMetadata


class DummyPlatform(Platform):
    def __init__(self, config: dict, settings: dict, event_queue: Queue) -> None:
        super().__init__(config, event_queue)
        self.settings = settings

    async def run(self) -> None:
        return None

    def meta(self) -> PlatformMetadata:
        return PlatformMetadata(
            name=str(self.config.get("type")),
            description="dummy",
            id=str(self.config.get("id")),
        )


@pytest.fixture
def manager() -> PlatformManager:
    config = MagicMock()
    config.__getitem__.side_effect = lambda key: {
        "platform": [],
        "platform_settings": {},
    }[key]
    return PlatformManager(config, Queue())


@pytest.mark.parametrize(
    "platform_id",
    [
        "lark-藤田琴音Bot",
        "platform_123",
    ],
)
def test_platform_id_allows_safe_values(
    manager: PlatformManager, platform_id: str
) -> None:
    assert manager._is_valid_platform_id(platform_id)
    assert manager._sanitize_platform_id(platform_id) == (platform_id, False)


@pytest.mark.parametrize(
    ("platform_id", "sanitized"),
    [
        ("lark-藤田琴音 Bot", "lark-藤田琴音Bot"),
        ("lark - 藤田琴音 Bot", "lark-藤田琴音Bot"),
        ("my:platform", "my_platform"),
        ("my!platform", "my_platform"),
        ("my platform:bad!", "myplatform_bad_"),
    ],
)
def test_platform_id_sanitizes_disallowed_chars(
    manager: PlatformManager, platform_id: str, sanitized: str
) -> None:
    assert not manager._is_valid_platform_id(platform_id)
    assert manager._sanitize_platform_id(platform_id) == (sanitized, True)


def test_empty_platform_id_is_invalid(manager: PlatformManager) -> None:
    assert not manager._is_valid_platform_id("")
    assert manager._sanitize_platform_id(None) == (None, False)


@pytest.mark.asyncio
async def test_load_platform_sanitizes_whitespace_id(
    manager: PlatformManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(platform_cls_map, "dummy", DummyPlatform)
    monkeypatch.setattr(manager, "_start_platform_task", MagicMock())
    platform_config = {
        "enable": True,
        "type": "dummy",
        "id": "lark - 藤田琴音 Bot",
    }

    await manager.load_platform(platform_config)

    assert platform_config["id"] == "lark-藤田琴音Bot"
    assert "lark-藤田琴音Bot" in manager._inst_map
    assert "lark - 藤田琴音 Bot" not in manager._inst_map
    manager.astrbot_config.save_config.assert_called_once()
