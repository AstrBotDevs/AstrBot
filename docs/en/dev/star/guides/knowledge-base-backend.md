# Integrate an External Knowledge Base

The knowledge base backend API lets a plugin connect a remote service, an existing database, or another retrieval system to AstrBot. The Agent can then consume external knowledge through the same retrieval path used for built-in knowledge bases.

The API standardizes discovery and read-only retrieval only. It does not manage knowledge base creation, document uploads, chunks, credentials, or backups. Those management capabilities remain the responsibility of the plugin or external system.

## Implement a backend

A plugin must extend `BaseKnowledgeBaseBackend` and implement these members:

| Member | Purpose |
| --- | --- |
| `backend_id` | Globally unique backend identifier. It must contain 1–128 characters and may only use ASCII letters, numbers, `-`, `_`, `.`, and `:` |
| `display_name` | Human-readable name used in logs and errors |
| `list_knowledge_bases()` | Return knowledge bases available to the current session |
| `retrieve()` | Retrieve standardized results from selected knowledge bases |

The following example shows a complete plugin structure. Its remote paths and response fields are illustrative; adapt them to your service.

```python
from typing import Any

import httpx

from astrbot.api import (
    BaseKnowledgeBaseBackend,
    KnowledgeBaseHit,
    KnowledgeBaseInfo,
    KnowledgeBaseQuery,
    KnowledgeBaseRef,
    KnowledgeBaseResponse,
)
from astrbot.api.star import Context, Star


class RemoteKnowledgeBaseBackend(BaseKnowledgeBaseBackend):
    """Expose a remote retrieval service to AstrBot."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        """Initialize the remote backend.

        Args:
            client: Configured client for the remote knowledge base service.
        """
        self.client = client

    @property
    def backend_id(self) -> str:
        """Return the globally unique backend identifier."""
        return "example:remote"

    @property
    def display_name(self) -> str:
        """Return the human-readable backend name."""
        return "Example Remote Knowledge Base"

    async def list_knowledge_bases(
        self,
        *,
        umo: str | None = None,
    ) -> list[KnowledgeBaseInfo]:
        """List knowledge bases visible to the current session.

        Args:
            umo: Unified message origin used for access filtering.

        Returns:
            Knowledge bases that the current session may query.
        """
        response = await self.client.get(
            "/knowledge-bases",
            params={"umo": umo} if umo else None,
        )
        response.raise_for_status()
        return [
            KnowledgeBaseInfo(
                ref=KnowledgeBaseRef(self.backend_id, item["id"]),
                name=item["name"],
                description=item.get("description"),
                metadata=item.get("metadata", {}),
            )
            for item in response.json()["items"]
        ]

    async def retrieve(
        self,
        knowledge_base_ids: list[str],
        request: KnowledgeBaseQuery,
    ) -> KnowledgeBaseResponse:
        """Retrieve relevant content from selected knowledge bases.

        Args:
            knowledge_base_ids: Backend-local knowledge base identifiers.
            request: Standardized retrieval request.

        Returns:
            Ranked retrieval results and non-fatal warnings.
        """
        payload: dict[str, Any] = {
            "knowledge_base_ids": knowledge_base_ids,
            "query": request.query,
            "top_k": request.top_k,
            "umo": request.umo,
        }
        if request.score_threshold is not None:
            payload["score_threshold"] = request.score_threshold
        if request.filters:
            payload["filters"] = request.filters

        response = await self.client.post("/retrieve", json=payload)
        response.raise_for_status()
        data = response.json()
        return KnowledgeBaseResponse(
            hits=[
                KnowledgeBaseHit(
                    ref=KnowledgeBaseRef(
                        self.backend_id,
                        item["knowledge_base_id"],
                    ),
                    content=item["content"],
                    source=item.get("source", self.display_name),
                    rank=index,
                    score=item.get("score"),
                    document_id=item.get("document_id"),
                    chunk_id=item.get("chunk_id"),
                    source_uri=item.get("source_uri"),
                    metadata=item.get("metadata", {}),
                )
                for index, item in enumerate(data["hits"], start=1)
            ],
            warnings=data.get("warnings", []),
        )


class Main(Star):
    """Register the remote knowledge base backend."""

    def __init__(self, context: Context) -> None:
        """Initialize the plugin.

        Args:
            context: AstrBot plugin context.
        """
        super().__init__(context)
        self.client = httpx.AsyncClient(
            base_url="https://knowledge.example.com/api",
            timeout=10,
        )
        self.backend = RemoteKnowledgeBaseBackend(self.client)

    async def initialize(self) -> None:
        """Register the backend when the plugin starts."""
        self.context.register_knowledge_base_backend(self.backend)

    async def terminate(self) -> None:
        """Unregister the backend before releasing its resources."""
        self.context.unregister_knowledge_base_backend(self.backend.backend_id)
        await self.client.aclose()
```

The plugin owns the backend and all network connections, threads, and other resources it uses. AstrBot calls `terminate()` when the plugin is disabled or reloaded. The plugin must unregister its backend before closing those resources. Repeatedly unregistering the same `backend_id` is safe.

## Query semantics

`KnowledgeBaseQuery` provides these fields:

| Field | Semantics |
| --- | --- |
| `query` | User query text |
| `top_k` | Maximum number of results retained for the complete retrieval request |
| `score_threshold` | Optional backend-local relevance threshold |
| `filters` | Optional backend-specific metadata filters |
| `umo` | Unified message origin for session, tenant, or permission filtering |

`score_threshold` and `filters` are optional hints. A backend may ignore unsupported hints, but its own documentation should make that limitation clear. AstrBot's default Agent retrieval currently supplies only `query`, `top_k`, and `umo`.

Every `KnowledgeBaseHit` must include a `ref` belonging to the current backend and one of the knowledge bases selected for that request. AstrBot discards a hit with a mismatched reference. `rank` starts at 1, and a lower value means a better backend-local rank.

Scores from different backends are not necessarily comparable, so AstrBot does not sort cross-backend results directly by `score`. It merges results by each backend's `rank` and then applies the global `top_k`. Use `metadata` only for backend-specific information; put identity, source, and ranking data in their standard fields.

## Discovery and access control

When external backends are registered, the Agent calls each backend's `list_knowledge_bases(umo=...)` before retrieval and queries every knowledge base it returns. Therefore:

- `list_knowledge_bases()` must return only knowledge bases that the current `umo` may access and should use.
- Return an empty list when a session should not use the backend.
- Do not expose unauthorized knowledge bases and rely only on a second check in `retrieve()`.
- Listing and retrieval may run concurrently, so avoid shared mutable request state in backend implementations.

## Error handling

A backend may raise `KnowledgeBaseAuthenticationError`, `KnowledgeBaseRateLimitError`, `KnowledgeBaseNotFoundError`, `KnowledgeBaseTimeoutError`, or the general `KnowledgeBaseBackendError`. Multi-backend retrieval isolates an individual backend failure, records it as a warning, and continues with other available results.

When partial results are available, return them and describe non-fatal issues in `KnowledgeBaseResponse.warnings`. AstrBot ignores responses with invalid types and hits with empty content, invalid ranks, or mismatched knowledge base references.

## Current scope

The API intentionally remains small and covers only:

- Backend registration and unregistration
- Discovery of knowledge bases available to the current session
- Standardized read-only retrieval requests and results
- Concurrent backend calls, failure isolation, and result merging
- Injection of external retrieval results into the Agent context

Knowledge base creation, document upload and deletion, chunk management, indexing, statistics, backups, credential configuration, and WebUI management are outside this API. A plugin can expose commands, configuration, or Plugin Pages for those capabilities.
