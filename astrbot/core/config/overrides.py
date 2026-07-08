from __future__ import annotations

import copy
from contextvars import ContextVar, Token
from typing import Any, NamedTuple

from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.utils.shared_preferences import SharedPreferences

CORE_CONFIG_OVERRIDE_KEY = "config_override:core"
PLUGIN_CONFIG_OVERRIDE_PREFIX = "config_override:plugin:"
CONFIG_OVERRIDE_VERSION = 1


class EffectiveConfigContext(NamedTuple):
    umo: str
    config: AstrBotConfig


_current_effective_config: ContextVar[EffectiveConfigContext | None] = ContextVar(
    "astrbot_current_effective_config",
    default=None,
)


class EffectiveAstrBotConfig(dict):
    """Per-event AstrBot config view with no persistent file writes.

    Args:
        data: Effective config data after applying override paths.
        base_config: Config instance used as the immutable base for this view.
        umo: Unified message origin this view belongs to.
    """

    def __init__(
        self,
        data: dict[str, Any],
        *,
        base_config: AstrBotConfig,
        umo: str,
    ) -> None:
        super().__init__(data)
        object.__setattr__(self, "_base_config", base_config)
        object.__setattr__(self, "_umo", umo)
        object.__setattr__(self, "config_path", base_config.config_path)
        object.__setattr__(self, "default_config", base_config.default_config)
        object.__setattr__(self, "schema", base_config.schema)

    def save_config(
        self,
        replace_config: dict | None = None,
        *,
        indent: int = 2,
    ) -> None:
        """Keep save-compatible call sites from writing an override view to disk.

        Args:
            replace_config: Optional replacement data for the in-memory view.
            indent: Preserved for API compatibility with AstrBotConfig.
        """
        _ = indent
        if replace_config:
            self.clear()
            self.update(copy.deepcopy(replace_config))

    def __getattr__(self, item: str) -> Any:
        try:
            return self[item]
        except KeyError:
            return None

    def __setattr__(self, key: str, value: Any) -> None:
        self[key] = value


def get_current_effective_config(umo: str | None = None) -> AstrBotConfig | None:
    """Return the current task's effective config, if it matches the UMO.

    Args:
        umo: Optional unified message origin to match.

    Returns:
        The current effective config, or None when outside an event override scope.
    """
    current = _current_effective_config.get()
    if current is None:
        return None
    if umo is not None and current.umo != umo:
        return None
    return current.config


def set_current_effective_config(
    umo: str,
    config: AstrBotConfig,
) -> Token[EffectiveConfigContext | None]:
    """Bind an effective config to the current async task.

    Args:
        umo: Unified message origin the config belongs to.
        config: Effective config for the current event.

    Returns:
        Context variable token used to reset the binding.
    """
    return _current_effective_config.set(EffectiveConfigContext(umo, config))


def reset_current_effective_config(token: Token[EffectiveConfigContext | None]) -> None:
    """Reset the current task's effective config binding.

    Args:
        token: Token returned by set_current_effective_config.
    """
    _current_effective_config.reset(token)


def normalize_config_override_payload(payload: Any) -> dict[str, Any]:
    """Normalize a stored override payload into path-value pairs.

    Args:
        payload: Raw preference value for a config override.

    Returns:
        A mapping from dot-separated config path to override value.
    """
    if not isinstance(payload, dict):
        return {}
    paths = payload.get("paths", payload)
    if not isinstance(paths, dict):
        return {}
    return {
        path: copy.deepcopy(value)
        for path, value in paths.items()
        if isinstance(path, str) and path.strip()
    }


async def load_core_config_override_paths(
    preferences: SharedPreferences,
    umo: str,
) -> dict[str, Any]:
    """Load core config override paths for a UMO.

    Args:
        preferences: Shared preferences storage.
        umo: Unified message origin.

    Returns:
        Path-value override mapping from the stored core override payload.
    """
    override_payload = await preferences.session_get(
        umo,
        CORE_CONFIG_OVERRIDE_KEY,
        default={},
    )
    return normalize_config_override_payload(override_payload)


def load_core_config_override_paths_sync(
    preferences: SharedPreferences,
    umo: str,
) -> dict[str, Any]:
    """Synchronously load core config override paths for a UMO.

    Args:
        preferences: Shared preferences storage.
        umo: Unified message origin.

    Returns:
        Path-value override mapping from the stored core override payload.
    """
    override_payload = preferences.get(
        CORE_CONFIG_OVERRIDE_KEY,
        default={},
        scope="umo",
        scope_id=umo,
    )
    return normalize_config_override_payload(override_payload)


async def save_core_config_override_paths(
    preferences: SharedPreferences,
    umo: str,
    paths: dict[str, Any],
) -> None:
    """Persist core config override paths for a UMO.

    Args:
        preferences: Shared preferences storage.
        umo: Unified message origin.
        paths: Dot-separated config path to override value mapping.
    """
    await preferences.session_put(
        umo,
        CORE_CONFIG_OVERRIDE_KEY,
        {
            "version": CONFIG_OVERRIDE_VERSION,
            "paths": normalize_config_override_payload(paths),
        },
    )


async def update_core_config_override_paths(
    preferences: SharedPreferences,
    umo: str,
    paths: dict[str, Any],
) -> None:
    """Merge core config override paths into the stored payload for a UMO.

    Args:
        preferences: Shared preferences storage.
        umo: Unified message origin.
        paths: Dot-separated config path to override value mapping.
    """
    override_payload = await preferences.session_get(
        umo,
        CORE_CONFIG_OVERRIDE_KEY,
        default={},
    )
    merged_paths = normalize_config_override_payload(override_payload)
    merged_paths.update(normalize_config_override_payload(paths))
    await save_core_config_override_paths(preferences, umo, merged_paths)


async def remove_core_config_override_paths(
    preferences: SharedPreferences,
    umo: str,
    paths: list[str],
) -> None:
    """Remove core config override paths from the stored payload for a UMO.

    Args:
        preferences: Shared preferences storage.
        umo: Unified message origin.
        paths: Dot-separated config paths to remove.
    """
    override_payload = await preferences.session_get(
        umo,
        CORE_CONFIG_OVERRIDE_KEY,
        default={},
    )
    merged_paths = normalize_config_override_payload(override_payload)
    for path in paths:
        merged_paths.pop(path, None)
    await save_core_config_override_paths(preferences, umo, merged_paths)


def apply_config_override_paths(
    config_data: dict[str, Any],
    paths: dict[str, Any],
) -> dict[str, Any]:
    """Apply dot-separated override paths to a config dictionary.

    Args:
        config_data: Config data to mutate.
        paths: Dot-separated config path to override value mapping.

    Returns:
        The mutated config_data object.
    """
    for path, value in paths.items():
        target = config_data
        parts = [part for part in path.split(".") if part]
        if not parts:
            continue
        for part in parts[:-1]:
            child = target.get(part)
            if not isinstance(child, dict):
                child = {}
                target[part] = child
            target = child
        target[parts[-1]] = copy.deepcopy(value)
    return config_data


async def build_effective_core_config(
    base_config: AstrBotConfig,
    preferences: SharedPreferences,
    umo: str,
) -> AstrBotConfig:
    """Build a per-event effective config by applying UMO overrides.

    Args:
        base_config: Shared config profile selected for the event.
        preferences: Shared preferences storage.
        umo: Unified message origin.

    Returns:
        A no-write config view for this single event.
    """
    config_data = copy.deepcopy(dict(base_config))
    override_paths = await load_core_config_override_paths(preferences, umo)
    apply_config_override_paths(config_data, override_paths)
    return EffectiveAstrBotConfig(config_data, base_config=base_config, umo=umo)


def build_effective_core_config_sync(
    base_config: AstrBotConfig,
    preferences: SharedPreferences,
    umo: str,
) -> AstrBotConfig:
    """Synchronously build a per-UMO effective config.

    Args:
        base_config: Shared config profile selected for the UMO.
        preferences: Shared preferences storage.
        umo: Unified message origin.

    Returns:
        A no-write config view for this UMO.
    """
    config_data = copy.deepcopy(dict(base_config))
    override_paths = load_core_config_override_paths_sync(preferences, umo)
    apply_config_override_paths(config_data, override_paths)
    return EffectiveAstrBotConfig(config_data, base_config=base_config, umo=umo)
