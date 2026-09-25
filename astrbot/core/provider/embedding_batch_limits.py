"""Known per-request input limits of embedding services.

Every embedding request in AstrBot funnels through
``EmbeddingProvider.get_embeddings_batch``. Some services reject a request that
carries more than N inputs with a deterministic client error, which retrying can
never overcome; the limit therefore has to be known *before* the request is
built. This module holds the small amount of metadata AstrBot actually knows
about those limits, so adapters can declare it cheaply instead of each carrying
its own copy.

Kept dependency-free on purpose: ``provider/sources/dashscope_embedding_source``
imports the dashscope SDK and registers an adapter at import time, which makes it
a poor place to share a plain lookup table from.
"""

# Aliyun Model Studio (DashScope) caps the number of inputs accepted by one
# native embedding request. Exceeding it returns HTTP 400
# "batch size is invalid, it should not be larger than 10."
_DASHSCOPE_MAX_ITEMS: dict[str, int] = {
    "text-embedding-v1": 25,
    "text-embedding-v2": 25,
    "text-embedding-v3": 10,
    "text-embedding-v4": 10,
}
# Conservative fallback for DashScope embedding models whose limit is not
# documented per generation (e.g. the multimodal ones). Under-estimating only
# costs extra requests; over-estimating reproduces the failure.
DASHSCOPE_DEFAULT_MAX_ITEMS = 10

# Model families served by DashScope that are embeddings but carry no per-model
# entry above. Matched on substrings because these names carry version suffixes.
_DASHSCOPE_EMBEDDING_NAME_HINTS = (
    "multimodal-embedding",
    "vl-embedding",
    "tongyi-embedding-vision",
)

# Hosts serving the DashScope API, including the OpenAI-compatible mode which
# generic OpenAI endpoints are commonly pointed at.
_DASHSCOPE_HOSTS = frozenset(
    {
        "dashscope.aliyuncs.com",
        "dashscope-intl.aliyuncs.com",
    }
)


def dashscope_max_batch_items(model: str | None) -> int | None:
    """Return the DashScope input limit for ``model``, or None if not applicable.

    None means "this is not a DashScope embedding model" -- deliberately not
    "an embedding model with an unknown limit", so that a model name belonging
    to another vendor is never clamped by this table.
    """
    if not model:
        return None
    # Deployment prefixes are common ("models/text-embedding-v4").
    name = str(model).strip().lower().rsplit("/", 1)[-1]
    if name in _DASHSCOPE_MAX_ITEMS:
        return _DASHSCOPE_MAX_ITEMS[name]
    if name.startswith("text-embedding-v"):
        # A text-embedding generation newer than the table: assume the current
        # (stricter) generation's limit rather than the legacy 25.
        return DASHSCOPE_DEFAULT_MAX_ITEMS
    if any(hint in name for hint in _DASHSCOPE_EMBEDDING_NAME_HINTS):
        return DASHSCOPE_DEFAULT_MAX_ITEMS
    return None


def is_dashscope_host(hostname: str | None) -> bool:
    """Whether ``hostname`` points at the DashScope API."""
    if not hostname:
        return False
    return hostname.strip().lower() in _DASHSCOPE_HOSTS


def combine_caps(*caps: int | None) -> int | None:
    """Combine declared limits into a single effective limit.

    Only known limits participate, and the result is their minimum: a limit
    declared by the adapter can never be raised by a looser config value or by
    a second detection path.
    """
    known = [cap for cap in caps if isinstance(cap, int) and cap > 0]
    return min(known) if known else None
