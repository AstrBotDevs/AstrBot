"""Sparse per-session overrides for plugin configuration.

Every plugin with a _conf_schema.json owns exactly one AstrBotConfig instance
(metadata.config), which is shared by all platforms, groups and private chats.
This module adds an optional override layer on top of that global config,
keyed by UMO patterns, without changing the plugin singleton model:

- data/config/<plugin>_config.json is still the global plugin config.
- data/config/<plugin>_config.overrides.json optionally maps UMO patterns to
  partial configs.
- resolve_plugin_config() merges the first matching override on top of the
  global config and returns a snapshot. The global config object is never
  mutated, so concurrent handlers for different sessions cannot interfere.

The override file is a JSON object:

    {
      "version": 1,
      "scopes": {
        "aiocqhttp:group:123456": {"reply_style": "concise"},
        "aiocqhttp:group:*": {"enable_tts": false}
      }
    }

Scope keys use the same "platform_id:message_type:session_id" syntax as
UmopConfigRouter, where an empty segment or a value with wildcards matches
anything. The first matching scope in file order wins, and unlisted keys
inherit the global config.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

from astrbot.core.umop_config_router import is_umo_pattern_match, split_umo

logger = logging.getLogger("astrbot")

OVERRIDES_SUFFIX = ".overrides.json"
SCOPES_KEY = "scopes"

_SAVE_LOCK = threading.Lock()


def overrides_path_for(config_path: str | os.PathLike[str]) -> Path:
    """Return the override file path that belongs to a plugin config file.

    Args:
        config_path: Path of the plugin config file (*_config.json).

    Returns:
        A sibling path named "<name>.overrides.json". The override file is not
        required to exist.

    Raises:
        ValueError: If config_path is empty.
    """
    path = Path(config_path)
    if not path.name:
        raise ValueError("config_path must point to a plugin config file")
    stem = path.name[:-5] if path.name.endswith(".json") else path.name
    return path.with_name(f"{stem}{OVERRIDES_SUFFIX}")


def load_plugin_config_overrides(
    path: str | os.PathLike[str] | None,
) -> dict[str, dict]:
    """Load the override scopes of one plugin.

    Args:
        path: Override file path, usually from overrides_path_for().

    Returns:
        Mapping of UMO pattern to partial config. Missing, unreadable or
        malformed files yield an empty mapping so a broken override file never
        prevents a plugin from loading.
    """
    if not path:
        return {}
    file_path = Path(path)
    if not file_path.is_file():
        return {}
    try:
        data = json.loads(file_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        logger.warning(
            f"Failed to load plugin config overrides from {file_path}: {exc}"
        )
        return {}

    if not isinstance(data, dict):
        logger.warning(
            f"Ignoring plugin config overrides in {file_path}: "
            "root must be a JSON object"
        )
        return {}

    raw_scopes = data.get(SCOPES_KEY)
    if not isinstance(raw_scopes, dict):
        logger.warning(
            f"Ignoring plugin config overrides in {file_path}: missing "
            f"'{SCOPES_KEY}' object"
        )
        return {}

    scopes: dict[str, dict] = {}
    for pattern, override in raw_scopes.items():
        if not isinstance(pattern, str) or not isinstance(override, dict):
            logger.warning(
                f"Ignoring invalid scope {pattern!r} in plugin config overrides "
                f"{file_path}: scope keys must be strings and values must be objects"
            )
            continue
        if split_umo(pattern) is None:
            logger.warning(
                f"Ignoring invalid scope {pattern!r} in plugin config overrides "
                f"{file_path}: scope keys must use the "
                "'platform:message_type:session_id' UMO syntax"
            )
            continue
        scopes[pattern] = override
    return scopes


def save_plugin_config_overrides(
    path: str | os.PathLike[str],
    scopes: dict[str, dict],
) -> None:
    """Persist override scopes atomically.

    Args:
        path: Override file path, usually from overrides_path_for().
        scopes: Mapping of UMO pattern to partial config.

    Raises:
        ValueError: If a scope key or value has an invalid type, or a scope
            key is not a valid UMO pattern.
        OSError: If the file cannot be written.
    """
    for pattern, override in scopes.items():
        if not isinstance(pattern, str) or not isinstance(override, dict):
            raise ValueError("scopes must map UMO pattern strings to objects")
        if split_umo(pattern) is None:
            raise ValueError(
                f"Invalid scope key {pattern!r}: expected the "
                "'platform:message_type:session_id' UMO syntax"
            )

    payload = {"version": 1, SCOPES_KEY: scopes}
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = file_path.with_name(f"{file_path.name}.tmp")
    with _SAVE_LOCK:
        tmp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp_path, file_path)


def resolve_plugin_config_overrides(
    scopes: dict[str, dict],
    umo: str | None,
) -> dict[str, Any]:
    """Pick the override that applies to one session.

    Args:
        scopes: Mapping of UMO pattern to partial config.
        umo: Unified message origin of the session, or None for the global
            config.

    Returns:
        The first matching partial config in file order, or an empty dict when
        no scope matches. The returned object is a deep copy.
    """
    if not umo or not scopes:
        return {}
    for pattern, override in scopes.items():
        if is_umo_pattern_match(pattern, umo):
            return copy.deepcopy(override)
    return {}


def resolve_plugin_config(
    base: dict[str, Any] | None,
    scopes: dict[str, dict],
    umo: str | None,
) -> dict[str, Any]:
    """Merge the matching override on top of a plugin's global config.

    Nested objects are merged recursively, while lists and scalar values are
    replaced, matching how a sparse override is expected to read.

    Args:
        base: The plugin's global config.
        scopes: Mapping of UMO pattern to partial config.
        umo: Unified message origin of the session, or None for the global
            config.

    Returns:
        A new dict. base is never mutated.
    """
    merged = copy.deepcopy(base or {})
    override = resolve_plugin_config_overrides(scopes, umo)
    return _deep_merge(merged, override)


def _deep_merge(target: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    for key, value in override.items():
        current = target.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            _deep_merge(current, value)
        else:
            target[key] = copy.deepcopy(value)
    return target
