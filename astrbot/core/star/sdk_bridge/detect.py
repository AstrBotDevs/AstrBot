from __future__ import annotations

import json
from pathlib import Path

import yaml

_BRIDGE_MODULE_PREFIX = "sdk_bridge"


def _load_yaml_dict(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        # Pass raw bytes so PyYAML detects BOM-marked encodings (e.g. UTF-16)
        # instead of crashing on non-UTF-8 metadata files.
        data = yaml.safe_load(path.read_bytes())
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


def is_sdk_plugin_dir(dir_path: str | Path) -> bool:
    """Check whether one plugin directory belongs to the SDK runtime.

    Args:
        dir_path: Candidate plugin directory containing `plugin.json` or `metadata.yaml`.

    Returns:
        True when the manifest declares `plugin.json` schemaVersion 1 or
        `metadata.yaml` schema_version 2 with `runtime.api == "sdk"`.
    """
    root = Path(dir_path)
    plugin_json = root / "plugin.json"
    if plugin_json.is_file():
        try:
            payload = json.loads(plugin_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = None
        if isinstance(payload, dict) and payload.get("schemaVersion") == 1:
            return True

    data = _load_yaml_dict(root / "metadata.yaml")
    if data is None:
        data = _load_yaml_dict(root / "metadata.yml")
    if data is None:
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
    root = Path(dir_path)
    if (root / "plugin.json").is_file():
        return False
    if overrides:
        override = overrides.get(root.name)
        if override == "isolated":
            return True
        if override == "in-process":
            return False
    data = _load_yaml_dict(root / "metadata.yaml")
    if data is None:
        data = _load_yaml_dict(root / "metadata.yml")
    if data is None or "schema_version" in data:
        return False
    runtime = data.get("runtime")
    return isinstance(runtime, dict) and bool(runtime.get("isolated"))
