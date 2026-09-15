"""OrcaRouter model catalog discovery and capability filtering.

The authoritative catalog is ``GET {api_base}/models`` on the configured
inference origin. Live discovery is bounded and validated; when it fails the
caller keeps a small verified seed so a fresh installation still works.

Model IDs are returned verbatim — OrcaRouter namespaces them as
``vendor/model`` and that namespace is preserved everywhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import httpx

from astrbot import logger

Capability = Literal["chat", "embedding", "image", "video", "rerank"]

#: Endpoint types this client can actually speak through its OpenAI-compatible
#: transport. A catalog record advertising only something else is not usable.
SUPPORTED_ENDPOINT_TYPES = frozenset(
    {"openai", "openai-response", "anthropic", "gemini"}
)

#: Endpoint types that mark a record as *not* a general text chat model.
NON_TEXT_ENDPOINT_TYPES = frozenset(
    {"image-generation", "openai-video", "jina-rerank", "embedding", "embeddings"}
)

# Bounds so a hostile or broken catalog response cannot exhaust memory.
MAX_CATALOG_ITEMS = 2000
MAX_CATALOG_BYTES = 4 * 1024 * 1024
CATALOG_TIMEOUT_SECONDS = 15.0


@dataclass
class CatalogModel:
    """One validated entry from the OrcaRouter model catalog."""

    id: str
    endpoint_types: frozenset[str] = field(default_factory=frozenset)
    input_modalities: frozenset[str] = field(default_factory=frozenset)
    output_modalities: frozenset[str] = field(default_factory=frozenset)
    context_length: int = 0
    max_completion_tokens: int = 0
    name: str = ""
    verified: bool = False
    """True when the entry comes from the small offline-verified seed rather
    than from live discovery."""

    def supports_text_chat(self) -> bool:
        """Report whether this record can serve a text chat request.

        Returns:
            True when the record advertises a speakable endpoint type and is
            not a dedicated non-text model.
        """
        if not (self.endpoint_types & SUPPORTED_ENDPOINT_TYPES):
            return False
        if self.endpoint_types <= NON_TEXT_ENDPOINT_TYPES:
            return False
        return True

    def supports_input(self, modality: str) -> bool:
        """Report whether the record explicitly declares an input modality.

        Models that do not declare modalities at all are treated as text-only,
        so an undeclared capability never leaks into a multimodal picker.

        Args:
            modality: One of ``image``, ``audio``, ``video``.

        Returns:
            True only when the modality is explicitly declared.
        """
        return modality in self.input_modalities

    def to_metadata(self) -> dict[str, Any]:
        """Render the dashboard-facing metadata payload for this record.

        Returns:
            A JSON-serialisable dict matching the shape the dashboard already
            consumes for model metadata.
        """
        limit: dict[str, int] = {"context": self.context_length}
        if self.max_completion_tokens:
            limit["output"] = self.max_completion_tokens
        return {
            "id": self.id,
            "modalities": {
                "input": sorted(self.input_modalities),
                "output": sorted(self.output_modalities),
            },
            "limit": limit,
            "context_length": self.context_length,
            "endpoint_types": sorted(self.endpoint_types),
            "verified": self.verified,
        }


def _as_str_set(value: Any) -> frozenset[str]:
    """Coerce a catalog field into a set of non-empty strings.

    Args:
        value: Raw field value from the catalog record.

    Returns:
        The accepted string members.
    """
    if not isinstance(value, list):
        return frozenset()
    return frozenset(item for item in value if isinstance(item, str) and item)


def _as_int(value: Any) -> int:
    """Coerce a catalog field into a non-negative int.

    Args:
        value: Raw field value from the catalog record.

    Returns:
        The parsed value, or 0 when unusable.
    """
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return parsed if parsed > 0 else 0


def parse_catalog(payload: Any) -> list[CatalogModel]:
    """Validate and normalise a ``GET /models`` response.

    Unusable records are dropped rather than raising, so one malformed entry
    cannot take out the whole picker.

    Args:
        payload: Decoded JSON body from the catalog endpoint.

    Returns:
        The accepted records, in response order.
    """
    if isinstance(payload, dict):
        records = payload.get("data")
    else:
        records = payload
    if not isinstance(records, list):
        return []

    models: list[CatalogModel] = []
    for record in records[:MAX_CATALOG_ITEMS]:
        if not isinstance(record, dict):
            continue
        model_id = record.get("id")
        if not isinstance(model_id, str) or not model_id.strip():
            continue
        architecture = record.get("architecture")
        if not isinstance(architecture, dict):
            architecture = {}
        models.append(
            CatalogModel(
                id=model_id.strip(),
                endpoint_types=_as_str_set(record.get("supported_endpoint_types")),
                input_modalities=_as_str_set(architecture.get("input_modalities")),
                output_modalities=_as_str_set(architecture.get("output_modalities")),
                context_length=_as_int(record.get("context_length")),
                max_completion_tokens=_as_int(record.get("max_completion_tokens")),
                name=str(record.get("name") or ""),
            )
        )
    return models


def filter_models(
    models: list[CatalogModel], capability: Capability
) -> list[CatalogModel]:
    """Select the records usable for one entry point.

    Args:
        models: Catalog records, live or seed.
        capability: The capability the consuming entry point needs.

    Returns:
        The compatible subset, preserving input order.
    """
    if capability == "chat":
        return [model for model in models if model.supports_text_chat()]
    if capability == "embedding":
        return [
            model
            for model in models
            if model.endpoint_types & {"embedding", "embeddings"}
        ]
    if capability == "image":
        return [model for model in models if "image-generation" in model.endpoint_types]
    if capability == "video":
        return [model for model in models if "openai-video" in model.endpoint_types]
    if capability == "rerank":
        return [model for model in models if "jina-rerank" in model.endpoint_types]
    return []


def filter_for_multimodal(
    models: list[CatalogModel], modalities: set[str]
) -> list[CatalogModel]:
    """Select chat models that explicitly accept every required modality.

    Args:
        models: Catalog records.
        modalities: Non-text input modalities the entry point will actually
            upload, e.g. ``{"image"}``.

    Returns:
        Chat-capable records declaring every requested modality. Records with
        no declared modalities are excluded.
    """
    required = {m for m in modalities if m and m != "text"}
    selected = filter_models(models, "chat")
    if not required:
        return selected
    return [
        model
        for model in selected
        if all(model.supports_input(modality) for modality in required)
    ]


async def fetch_live_catalog(
    api_base_url: str, api_key: str, timeout: float = CATALOG_TIMEOUT_SECONDS
) -> list[CatalogModel]:
    """Fetch and validate the authoritative catalog from the inference origin.

    Args:
        api_base_url: Inference origin including ``/v1``.
        api_key: The user's OrcaRouter key. Sent only to this origin.
        timeout: Request timeout in seconds.

    Returns:
        The parsed catalog records.

    Raises:
        httpx.HTTPError: The catalog could not be retrieved.
        ValueError: The response was not a usable catalog.
    """
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(
            f"{api_base_url}/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        response.raise_for_status()
        if len(response.content) > MAX_CATALOG_BYTES:
            raise ValueError("OrcaRouter catalog response exceeded the size bound")
        payload = response.json()

    models = parse_catalog(payload)
    if not models:
        raise ValueError("OrcaRouter catalog contained no usable model records")
    return models


#: Small, offline-verified fallback so a fresh install survives a catalog
#: outage. Only ever used when live discovery fails; a successful live fetch is
#: authoritative and is never mixed with these entries.
VERIFIED_SEED: tuple[CatalogModel, ...] = (
    CatalogModel(
        id="openai/gpt-5.5",
        endpoint_types=frozenset({"openai", "openai-response"}),
        input_modalities=frozenset({"text", "image"}),
        output_modalities=frozenset({"text"}),
        context_length=400000,
        max_completion_tokens=128000,
        name="OpenAI: GPT-5.5",
        verified=True,
    ),
    CatalogModel(
        id="anthropic/claude-opus-4.8",
        endpoint_types=frozenset({"openai", "anthropic"}),
        input_modalities=frozenset({"text", "image"}),
        output_modalities=frozenset({"text"}),
        context_length=200000,
        max_completion_tokens=64000,
        name="Anthropic: Claude Opus 4.8",
        verified=True,
    ),
    CatalogModel(
        id="google/gemini-3.5-flash",
        endpoint_types=frozenset({"openai", "gemini"}),
        input_modalities=frozenset({"text", "image", "audio", "video"}),
        output_modalities=frozenset({"text"}),
        context_length=1000000,
        max_completion_tokens=65536,
        name="Google: Gemini 3.5 Flash",
        verified=True,
    ),
    CatalogModel(
        id="deepseek/deepseek-v4-pro",
        endpoint_types=frozenset({"openai", "openai-response"}),
        input_modalities=frozenset({"text"}),
        output_modalities=frozenset({"text"}),
        context_length=1048576,
        max_completion_tokens=384000,
        name="DeepSeek: DeepSeek V4 Pro",
        verified=True,
    ),
    CatalogModel(
        id="orcarouter/auto",
        endpoint_types=frozenset({"openai", "openai-response", "anthropic", "gemini"}),
        input_modalities=frozenset({"text"}),
        output_modalities=frozenset({"text"}),
        name="OrcaRouter: Auto",
        verified=True,
    ),
)

#: Reasoning-effort ladder verified for the GPT-5.5 seed entry. Carried
#: separately because the catalog endpoint does not report it.
VERIFIED_REASONING_EFFORTS: dict[str, tuple[str, ...]] = {
    "openai/gpt-5.5": ("low", "medium", "high", "xhigh"),
}


def seed_catalog() -> list[CatalogModel]:
    """Return a copy of the verified fallback catalog.

    Returns:
        The seed records, safe for the caller to mutate.
    """
    return [
        CatalogModel(
            id=model.id,
            endpoint_types=model.endpoint_types,
            input_modalities=model.input_modalities,
            output_modalities=model.output_modalities,
            context_length=model.context_length,
            max_completion_tokens=model.max_completion_tokens,
            name=model.name,
            verified=True,
        )
        for model in VERIFIED_SEED
    ]


@dataclass
class CatalogResult:
    """The catalog a caller should use, plus how it was obtained."""

    models: list[CatalogModel]
    source: Literal["live", "seed", "last_known_good"]
    degraded: bool = False

    def model_ids(self) -> list[str]:
        """Return the model IDs in catalog order.

        Returns:
            The IDs, unchanged from the catalog.
        """
        return [model.id for model in self.models]

    def metadata_map(self) -> dict[str, dict[str, Any]]:
        """Build the dashboard metadata payload for this catalog.

        Returns:
            A mapping of model ID to metadata dict.
        """
        return {model.id: model.to_metadata() for model in self.models}


async def discover_catalog(
    api_base_url: str,
    api_key: str,
    *,
    last_known_good: list[CatalogModel] | None = None,
    timeout: float = CATALOG_TIMEOUT_SECONDS,
) -> CatalogResult:
    """Discover the catalog, degrading safely when the endpoint is unavailable.

    Args:
        api_base_url: Inference origin including ``/v1``.
        api_key: The user's OrcaRouter key.
        last_known_good: Previously discovered live records to prefer over the
            static seed when this attempt fails.
        timeout: Request timeout in seconds.

    Returns:
        A :class:`CatalogResult` describing the records and their provenance.
    """
    try:
        models = await fetch_live_catalog(api_base_url, api_key, timeout=timeout)
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning(
            "OrcaRouter model discovery failed (%s); falling back to a verified "
            "catalog",
            type(exc).__name__,
        )
        if last_known_good:
            return CatalogResult(
                models=last_known_good, source="last_known_good", degraded=True
            )
        return CatalogResult(models=seed_catalog(), source="seed", degraded=True)
    return CatalogResult(models=models, source="live", degraded=False)
