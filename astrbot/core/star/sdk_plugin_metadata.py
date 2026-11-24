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
        # Pass raw bytes so PyYAML detects BOM-marked encodings (e.g. UTF-16)
        # instead of crashing on non-UTF-8 metadata files.
        data = yaml.safe_load(metadata_path.read_bytes())
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
