"""Shared session overrides used by commands, configuration and the dashboard."""

import asyncio
from copy import deepcopy
from typing import Any

from astrbot.core import sp
from astrbot.core.config_bindings import BINDING_KEY

OVERRIDE_KEY = "config_overrides"
PROVIDER_PATHS = {
    "chat_completion": "agent.config.model.provider_id",
    "speech_to_text": "provider_stt_settings.provider_id",
    "text_to_speech": "provider_tts_settings.provider_id",
}
# Only fields whose consumers resolve session configuration are exposed.
OVERRIDE_TYPES = {
    "wake_prefix": list,
    "provider_settings.enable": bool,
    "provider_stt_settings.enable": bool,
    "provider_tts_settings.enable": bool,
    **dict.fromkeys(PROVIDER_PATHS.values(), str),
    "agent.config.persona.persona_id": str,
    "agent.config.persona_id": str,
    "plugin_set": list,
    "disabled_plugins": list,
    "kb_names": list,
    "kb_final_top_k": int,
    "platform_settings.id_blacklist": list,
}
_locks = [asyncio.Lock() for _ in range(64)]


def apply_overrides(config: dict, overrides: dict) -> dict:
    """Apply explicit field values without changing the shared profile.

    Args:
        config: Base profile configuration.
        overrides: Dotted configuration paths mapped to replacement values.

    Returns:
        An independent configuration with whole-list replacement semantics.
    """
    result = deepcopy(dict(config))
    for path, value in overrides.items():
        if path not in OVERRIDE_TYPES:
            continue
        target = result
        parts = path.split(".")
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        target[parts[-1]] = deepcopy(value)
    return result


async def get_overrides(umo: str) -> dict:
    """Read the explicit fields of a session binding.

    Args:
        umo: Exact unified message origin.

    Returns:
        The session's explicit field values.
    """
    binding = await sp.session_get(umo, BINDING_KEY, {}) or {}
    return binding.get("overrides", {})


async def update_overrides(
    umo: str,
    changes: dict[str, Any],
    *,
    profile_id: str | None = None,
    update_profile: bool = False,
    clear_overrides: bool = False,
) -> dict:
    """Atomically patch explicit overrides, using None to restore inheritance.

    Args:
        umo: Unified message origin.
        changes: Supported dotted paths and values; None removes a path.
        profile_id: Explicit base profile, or None to follow routing.
        update_profile: Whether to also update the base profile selection.
        clear_overrides: Whether to remove all existing overrides before patching.

    Returns:
        The persisted overrides after applying the patch.

    Raises:
        ValueError: If a path, value type, or retrieval count is invalid.
    """
    for path, value in changes.items():
        expected = OVERRIDE_TYPES.get(path)
        if expected is None:
            raise ValueError(f"Unsupported override: {path}")
        if value is None:
            continue
        if type(value) is not expected:
            raise ValueError(f"Invalid value for {path}")
        if expected is list and any(not isinstance(item, str) for item in value):
            raise ValueError(f"Expected a list of strings for {path}")
        if path == "kb_final_top_k" and not 1 <= value <= 1000:
            raise ValueError("Retrieval count must be between 1 and 1000")
    async with _locks[hash(umo) % len(_locks)]:
        binding = await sp.session_get(umo, BINDING_KEY, {}) or {}
        binding.setdefault("profile_id", None)
        if update_profile:
            binding["profile_id"] = profile_id
        overrides = {} if clear_overrides else deepcopy(binding.get("overrides", {}))
        for path, value in changes.items():
            if value is None:
                overrides.pop(path, None)
            else:
                overrides[path] = deepcopy(value)
        binding["overrides"] = overrides
        if overrides or binding["profile_id"] is not None:
            await sp.session_put(umo, BINDING_KEY, binding)
        else:
            await sp.session_remove(umo, BINDING_KEY)
        return overrides
