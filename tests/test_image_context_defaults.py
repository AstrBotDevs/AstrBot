"""Default configuration enables managed image history without overriding opt-outs."""

import json

import pytest

from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.config.default import DEFAULT_CONFIG


@pytest.mark.parametrize(
    "existing",
    [
        None,
        {},
        {"provider_settings": {}},
        {"provider_settings": {"image_context_enabled": False}},
    ],
)
def test_new_and_existing_profiles_default_to_managed_images(tmp_path, existing):
    path = tmp_path / "config.json"
    if existing is not None:
        path.write_text(json.dumps(existing))
    config = AstrBotConfig(config_path=str(path))
    expected = (
        (existing or {}).get("provider_settings", {}).get("image_context_enabled", True)
    )
    assert DEFAULT_CONFIG["provider_settings"]["image_context_enabled"] is True
    assert config["provider_settings"]["image_context_enabled"] is expected
    saved = json.loads(path.read_text(encoding="utf-8-sig"))
    assert saved["provider_settings"]["image_context_enabled"] is expected
