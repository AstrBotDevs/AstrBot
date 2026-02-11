from __future__ import annotations

from astrbot.core import sp

FEATURE_LLM = "llm"
FEATURE_STT = "stt"
FEATURE_TTS = "tts"
FEATURE_T2I = "t2i"

DEFAULT_CHAIN_RUNTIME_FLAGS: dict[str, bool] = {
    FEATURE_LLM: True,
    FEATURE_STT: True,
    FEATURE_TTS: True,
    FEATURE_T2I: True,
}


def _normalize_flags(raw: dict | None) -> dict[str, bool]:
    flags = dict(DEFAULT_CHAIN_RUNTIME_FLAGS)
    if not isinstance(raw, dict):
        return flags
    for key in DEFAULT_CHAIN_RUNTIME_FLAGS:
        if key in raw:
            flags[key] = bool(raw.get(key))
    return flags


async def get_chain_runtime_flags(chain_id: str | None) -> dict[str, bool]:
    if not chain_id:
        return dict(DEFAULT_CHAIN_RUNTIME_FLAGS)
    all_flags = await sp.global_get("chain_runtime_flags", {})
    if not isinstance(all_flags, dict):
        return dict(DEFAULT_CHAIN_RUNTIME_FLAGS)
    return _normalize_flags(all_flags.get(chain_id))


async def set_chain_runtime_flag(
    chain_id: str | None,
    feature: str,
    enabled: bool,
) -> dict[str, bool]:
    if not chain_id:
        return dict(DEFAULT_CHAIN_RUNTIME_FLAGS)
    if feature not in DEFAULT_CHAIN_RUNTIME_FLAGS:
        raise ValueError(f"Unsupported chain runtime feature: {feature}")

    all_flags = await sp.global_get("chain_runtime_flags", {})
    if not isinstance(all_flags, dict):
        all_flags = {}

    chain_flags = _normalize_flags(all_flags.get(chain_id))
    chain_flags[feature] = bool(enabled)
    all_flags[chain_id] = chain_flags
    await sp.global_put("chain_runtime_flags", all_flags)
    return chain_flags


async def toggle_chain_runtime_flag(chain_id: str | None, feature: str) -> bool:
    flags = await get_chain_runtime_flags(chain_id)
    next_value = not bool(flags.get(feature, True))
    await set_chain_runtime_flag(chain_id, feature, next_value)
    return next_value


async def is_chain_runtime_feature_enabled(chain_id: str | None, feature: str) -> bool:
    flags = await get_chain_runtime_flags(chain_id)
    return bool(flags.get(feature, True))
