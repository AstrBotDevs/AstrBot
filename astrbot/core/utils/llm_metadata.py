import asyncio
import os
from typing import Any, Literal, TypedDict
from urllib.parse import urlsplit

import aiohttp

from astrbot.core import logger
from astrbot.core.utils.http_ssl import build_tls_connector


class LLMModalities(TypedDict):
    input: list[Literal["text", "image", "audio", "video"]]
    output: list[Literal["text", "image", "audio", "video"]]


class LLMLimit(TypedDict):
    context: int
    output: int


class LLMMetadata(TypedDict, total=False):
    id: str
    reasoning: bool
    reasoning_efforts: list[str]
    reasoning_off_value: str
    tool_call: bool
    knowledge: str
    release_date: str
    modalities: LLMModalities
    open_weights: bool
    limit: LLMLimit


REASONING_EFFORT_ORDER = (
    "none",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
)
# Providers whose toggle-capable effort models are verified to accept "none".
REASONING_OFF_PROVIDERS = frozenset(
    {
        "deepseek",
        "kimi-code-plan-cn",
        "kimi-code-plan-global",
    }
)
# Models supporting both effort and thinking.type=disabled, per Anthropic:
# https://platform.claude.com/docs/en/build-with-claude/thinking-troubleshooting
ANTHROPIC_DISABLED_THINKING_MODELS = frozenset(
    {
        "claude-haiku-5-5",
        "claude-opus-4-5",
        "claude-opus-4-5-20251101",
        "claude-opus-4-6",
        "claude-opus-4-7",
        "claude-opus-4-8",
        "claude-opus-5",
        "claude-sonnet-4-6",
        "claude-sonnet-5",
    }
)
PROVIDER_TO_MODELS_DEV = {
    "aihubmix": "aihubmix",
    "anthropic": "anthropic",
    "bailian": "alibaba-cn",
    "dashscope": "alibaba-cn",
    "deepseek": "deepseek",
    "gemini": "google",
    "google": "google",
    "groq": "groq",
    "kimi-code": "kimi-code-plan-cn",
    "minimax": "minimax",
    "minimax-token-plan": "minimax-cn-coding-plan",
    "moonshot": "moonshotai",
    "openai": "openai",
    "openrouter": "openrouter",
    "siliconflow": "siliconflow",
    "volcengine": "volcengine",
    "xai": "xai",
    "xiaomi": "xiaomi",
    "xiaomi-token-plan": "xiaomi-token-plan-cn",
    "zhipu": "zhipuai",
}
ADAPTER_TO_MODELS_DEV = {
    "aihubmix_chat_completion": "aihubmix",
    "anthropic_chat_completion": "anthropic",
    "googlegenai_chat_completion": "google",
    "groq_chat_completion": "groq",
    "kimi_code_chat_completion": "kimi-code-plan-cn",
    "minimax_token_plan": "minimax-cn-coding-plan",
    "openai_chat_completion": "openai",
    "openai_responses": "openai",
    "openrouter_chat_completion": "openrouter",
    "xai_chat_completion": "xai",
    "xiaomi_chat_completion": "xiaomi",
    "xiaomi_token_plan": "xiaomi-token-plan-cn",
    "zhipu_chat_completion": "zhipuai",
}

LLM_METADATAS: dict[str, LLMMetadata] = {}
LLM_METADATAS_BY_LOWER: dict[str, LLMMetadata] = {}
LLM_PROVIDER_REASONING_EFFORTS: dict[str, dict[str, tuple[str, ...]]] = {}
LLM_METADATA_URLS = (
    "https://models.dev/api.json",
    "https://models.opencode.ai/api.json",
)


def populate_llm_metadata(data: dict[str, Any]) -> int:
    """Populate in-memory LLM metadata and reasoning effort tables from catalog data.

    Args:
        data: Parsed JSON mapping from models.dev or a compatible endpoint.

    Returns:
        Number of models stored in ``LLM_METADATAS``.
    """
    models: dict[str, LLMMetadata] = {}
    by_provider: dict[str, dict[str, tuple[str, ...]]] = {}

    for provider_id, info in data.items():
        if not isinstance(provider_id, str) or not isinstance(info, dict):
            continue
        raw_models = info.get("models")
        if not isinstance(raw_models, dict):
            continue

        provider_efforts: dict[str, tuple[str, ...]] = {}
        for model in raw_models.values():
            if not isinstance(model, dict):
                continue
            model_id = model.get("id")
            if not isinstance(model_id, str) or not model_id:
                continue

            options = model.get("reasoning_options")
            has_toggle = False
            values: list[str] = []
            if isinstance(options, list):
                for opt in options:
                    if not isinstance(opt, dict):
                        continue
                    opt_type = opt.get("type")
                    if opt_type == "toggle":
                        has_toggle = True
                    elif opt_type == "effort" and isinstance(opt.get("values"), list):
                        values = [
                            v.strip().lower()
                            for v in opt["values"]
                            if isinstance(v, str)
                            and v.strip().lower() in REASONING_EFFORT_ORDER
                        ]
            if (
                values
                and "none" not in values
                and provider_id in REASONING_OFF_PROVIDERS
                and has_toggle
            ):
                values = ["none", *values]
            value_set = set(values)
            efforts = tuple(v for v in REASONING_EFFORT_ORDER if v in value_set)
            lower_id = model_id.lower()
            bare_id = lower_id.rsplit("/", 1)[-1]
            provider_efforts[lower_id] = efforts
            provider_efforts.setdefault(bare_id, efforts)

            models[model_id] = LLMMetadata(
                id=model_id,
                reasoning=bool(model.get("reasoning", False)),
                tool_call=bool(model.get("tool_call", False)),
                knowledge=model.get("knowledge", "none"),
                release_date=model.get("release_date", ""),
                modalities=model.get("modalities", {"input": [], "output": []}),
                open_weights=bool(model.get("open_weights", False)),
                limit=model.get("limit", {"context": 0, "output": 0}),
            )

        by_provider[provider_id.lower()] = provider_efforts

    models_by_lower: dict[str, LLMMetadata] = {}
    for model_id, meta in models.items():
        lower_id = model_id.lower()
        bare_id = lower_id.rsplit("/", 1)[-1]
        models_by_lower[lower_id] = meta
        models_by_lower.setdefault(bare_id, meta)

    # Replace the global caches in-place so imported references remain valid.
    LLM_METADATAS.clear()
    LLM_METADATAS.update(models)
    LLM_METADATAS_BY_LOWER.clear()
    LLM_METADATAS_BY_LOWER.update(models_by_lower)
    LLM_PROVIDER_REASONING_EFFORTS.clear()
    LLM_PROVIDER_REASONING_EFFORTS.update(by_provider)
    return len(models)


def resolve_model_metadata(
    model_id: str,
    *,
    provider: str | None = None,
    adapter_type: str | None = None,
    api_base: str | None = None,
) -> LLMMetadata | None:
    """Resolve model metadata with provider-specific reasoning effort levels.

    Checks the configured provider catalog, then the adapter's mapped catalog.

    Args:
        model_id: Model identifier configured on the provider.
        provider: Optional provider brand name (e.g. ``deepseek``, ``openai``).
        adapter_type: Optional AstrBot adapter type (e.g. ``openai_chat_completion``).
        api_base: Configured endpoint for the selected adapter.

    Returns:
        A metadata dict with resolved ``reasoning_efforts`` when known, or ``None``.
    """
    if not isinstance(model_id, str) or not model_id:
        return None

    lower_id = model_id.lower()
    bare_id = lower_id.rsplit("/", 1)[-1]
    raw_bare_id = model_id.rsplit("/", 1)[-1]
    base_meta = (
        LLM_METADATAS.get(model_id)
        or LLM_METADATAS.get(raw_bare_id)
        or LLM_METADATAS_BY_LOWER.get(lower_id)
        or LLM_METADATAS_BY_LOWER.get(bare_id)
    )

    host = urlsplit(api_base or "").hostname or ""
    if host.startswith("ark.") and host.endswith(".volces.com"):
        provider = "volcengine"
    elif bare_id == "grok-4.3" and host == "api.x.ai":
        provider = "xai"
    catalog_providers: list[str] = []
    if isinstance(provider, str) and provider.strip():
        provider = provider.strip().lower()
        catalog_providers.append(PROVIDER_TO_MODELS_DEV.get(provider, provider))
    if isinstance(adapter_type, str) and adapter_type.strip():
        mapped = ADAPTER_TO_MODELS_DEV.get(adapter_type.strip(), "")
        if mapped and mapped not in catalog_providers:
            catalog_providers.append(mapped)

    efforts: tuple[str, ...] | None = None
    for catalog_provider in catalog_providers:
        provider_map = LLM_PROVIDER_REASONING_EFFORTS.get(catalog_provider)
        if provider_map is None:
            continue
        efforts = provider_map.get(lower_id)
        if efforts is None:
            efforts = provider_map.get(bare_id)
        if efforts is not None:
            if catalog_provider == "xai" and bare_id == "grok-4.3":
                efforts = tuple(level for level in efforts if level != "xhigh")
            if (
                catalog_provider == "anthropic"
                and efforts
                and "none" not in efforts
                and bare_id in ANTHROPIC_DISABLED_THINKING_MODELS
            ):
                efforts = ("none", *efforts)
            break

    if base_meta is None and efforts is None:
        return None

    resolved: LLMMetadata = (
        dict(base_meta)  # type: ignore[assignment]
        if base_meta is not None
        else LLMMetadata(id=model_id, reasoning=bool(efforts))
    )
    if efforts is not None:
        resolved["reasoning_efforts"] = list(efforts)
        if provider == "volcengine" and "minimal" in efforts:
            # Ark's "minimal" disables thinking, including with thinking.type=disabled.
            resolved["reasoning_off_value"] = "minimal"
    if (
        adapter_type == "openai_chat_completion"
        and lower_id in {"gpt-6.2-astra", "gpt-6.2-sol"}
        and (api_base or os.getenv("OPENAI_BASE_URL") or "").rstrip("/")
        in {"", "https://api.openai.com/v1"}
        and "max" in resolved.get("reasoning_efforts", [])
    ):
        resolved["reasoning_efforts"] = [
            level for level in resolved["reasoning_efforts"] if level != "max"
        ]
    return resolved


async def update_llm_metadata() -> None:
    """Fetch and refresh model metadata from the configured catalog endpoints."""
    last_error: Exception | None = None
    async with aiohttp.ClientSession(
        trust_env=True, connector=build_tls_connector()
    ) as session:
        for url in LLM_METADATA_URLS:
            try:
                async with session.get(url) as response:
                    response.raise_for_status()
                    data = await response.json()
                    if not isinstance(data, dict):
                        raise ValueError("LLM metadata response must be a JSON object")
            except (
                aiohttp.ClientError,
                asyncio.TimeoutError,
                ValueError,
            ) as e:
                last_error = e
                logger.warning(f"Endpoint {url} failed: {e}, trying next...")
                continue

            count = populate_llm_metadata(data)
            logger.info(f"Successfully fetched metadata for {count} LLMs from {url}.")
            return

    logger.error(f"All metadata endpoints failed: {last_error}")
