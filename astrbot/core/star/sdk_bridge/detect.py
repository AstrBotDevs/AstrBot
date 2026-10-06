from __future__ import annotations

from pathlib import Path

import yaml

_BRIDGE_MODULE_PREFIX = "sdk_bridge"


def is_sdk_plugin_dir(dir_path: str | Path) -> bool:
    """Check whether one plugin directory belongs to the new SDK runtime.

    Args:
        dir_path: Candidate plugin directory containing metadata.yaml.

    Returns:
        True when the metadata declares schema_version 2 with the SDK API.
    """
    metadata_path = Path(dir_path) / "metadata.yaml"
    if not metadata_path.is_file():
        return False
    try:
        data = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return False
    if not isinstance(data, dict):
        return False
    runtime = data.get("runtime")
    return (
        data.get("schema_version") == 2
        and isinstance(runtime, dict)
        and runtime.get("api") == "sdk"
    )


def is_isolated_legacy_dir(
    dir_path: str | Path,
    overrides: dict | None = None,
) -> bool:
    """Check whether one legacy plugin opts into isolated runtime.

    Legacy plugins (no schema_version) stay in-process by default; they run
    isolated when metadata.yaml declares runtime.isolated, unless the user's
    runtime override (root dir name -> "isolated"/"in-process") says
    otherwise. The override always wins over the metadata declaration.
    """
    if overrides:
        override = overrides.get(Path(dir_path).name)
        if override == "isolated":
            return True
        if override == "in-process":
            return False
    metadata_path = Path(dir_path) / "metadata.yaml"
    if not metadata_path.is_file():
        return False
    try:
        data = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return False
    if not isinstance(data, dict) or "schema_version" in data:
        return False
    runtime = data.get("runtime")
    return isinstance(runtime, dict) and bool(runtime.get("isolated"))
