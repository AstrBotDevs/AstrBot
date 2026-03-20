from __future__ import annotations

from pathlib import Path

import pytest
from astrbot_sdk._plugin_ids import resolve_plugin_data_dir, validate_plugin_id


def test_validate_plugin_id_accepts_safe_identifiers() -> None:
    assert validate_plugin_id("plugin-1.alpha_beta") == "plugin-1.alpha_beta"


@pytest.mark.parametrize(
    "plugin_id",
    ["", "../escape", "bad/name", r"bad\\name", "bad.", "CON"],
)
def test_validate_plugin_id_rejects_unsafe_values(plugin_id: str) -> None:
    with pytest.raises(ValueError):
        validate_plugin_id(plugin_id)


def test_resolve_plugin_data_dir_stays_within_root(tmp_path: Path) -> None:
    resolved = resolve_plugin_data_dir(tmp_path, "plugin-a")

    assert resolved == tmp_path.resolve() / "plugin-a"
