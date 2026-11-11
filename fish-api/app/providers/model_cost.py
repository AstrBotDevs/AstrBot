"""Estimate USD model cost from token breakdown (cost_control compatible)."""

from __future__ import annotations

import importlib.util
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PRICING_PATH = (
    REPO_ROOT
    / "data"
    / "plugins"
    / "astrbot_plugin_cost_control"
    / "cost_control"
    / "default_pricing.py"
)


def _normalize_model_name(name: str) -> str:
    """Normalize model / provider ids for pricing lookup."""
    s = name.rsplit("/", 1)[-1].strip()
    s = s.replace("_", "-").replace(" ", "-").replace(".", "-")
    while "--" in s:
        s = s.replace("--", "-")
    return s.strip("-").lower()


@lru_cache(maxsize=1)
def _default_pricing_table() -> dict[str, Any]:
    """Load DEFAULT_PRICING from the Token成本控制 plugin when present."""
    path = DEFAULT_PRICING_PATH
    if not path.is_file():
        logger.warning("cost_control default_pricing.py missing: %s", path)
        return {}
    spec = importlib.util.spec_from_file_location(
        "fish_cost_control_default_pricing",
        path,
    )
    if spec is None or spec.loader is None:
        return {}
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    table = getattr(module, "DEFAULT_PRICING", None)
    return table if isinstance(table, dict) else {}


def _match_prices(model: str | None, provider_id: str | None) -> dict[str, float] | None:
    """Find per_token USD/MTok prices for a model name."""
    table = _default_pricing_table()
    if not table:
        return None
    candidates = [c for c in (model, provider_id) if c]
    for raw in candidates:
        if raw in table and isinstance(table[raw], dict):
            return _as_per_token(table[raw])
        norm = _normalize_model_name(raw)
        for key, value in table.items():
            if _normalize_model_name(str(key)) == norm and isinstance(value, dict):
                return _as_per_token(value)
    # Prefix fallback: longest normalized key that matches.
    for raw in candidates:
        norm = _normalize_model_name(raw)
        best_key = None
        best_len = -1
        for key, value in table.items():
            if not isinstance(value, dict):
                continue
            nk = _normalize_model_name(str(key))
            if norm.startswith(nk) and len(nk) > best_len:
                best_key = value
                best_len = len(nk)
        if best_key is not None:
            return _as_per_token(best_key)
    return None


def _as_per_token(rule: dict[str, Any]) -> dict[str, float] | None:
    """Accept flat per_token price dicts from DEFAULT_PRICING."""
    if rule.get("mode") not in (None, "per_token"):
        return None
    try:
        return {
            "input": float(rule.get("input", 0) or 0),
            "input_cached": float(rule.get("input_cached", 0) or 0),
            "output": float(rule.get("output", 0) or 0),
        }
    except (TypeError, ValueError):
        return None


def usd_cost_from_tokens(
    *,
    model: str | None,
    provider_id: str | None = None,
    token_input_other: int = 0,
    token_input_cached: int = 0,
    token_output: int = 0,
) -> float:
    """USD cost for one usage row using cost_control default per_token prices.

    Args:
        model: Provider model name (e.g. deepseek-flash).
        provider_id: Optional provider id (e.g. deepseek/deepseek-flash).
        token_input_other: Non-cached input tokens.
        token_input_cached: Cached input tokens.
        token_output: Output tokens.

    Returns:
        Estimated USD cost. 0.0 when pricing is missing.
    """
    prices = _match_prices(model, provider_id)
    if not prices:
        logger.warning(
            "No pricing for model=%s provider_id=%s; cost treated as 0",
            model,
            provider_id,
        )
        return 0.0
    cost = (
        int(token_input_other or 0) * prices["input"]
        + int(token_input_cached or 0) * prices["input_cached"]
        + int(token_output or 0) * prices["output"]
    ) / 1_000_000.0
    return float(cost)


def clear_pricing_cache() -> None:
    """Drop cached DEFAULT_PRICING (tests / hot reload)."""
    _default_pricing_table.cache_clear()
