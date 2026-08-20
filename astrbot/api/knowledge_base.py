"""Public contracts for pluggable knowledge base backends."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class KnowledgeBaseRef:
    """Identify a knowledge base exposed by one backend.

    Args:
        backend_id: Globally unique backend identifier.
        knowledge_base_id: Backend-local knowledge base identifier.
    """

    backend_id: str
    knowledge_base_id: str


@dataclass(frozen=True, slots=True)
class KnowledgeBaseInfo:
    """Describe one knowledge base exposed by a backend.

    Args:
        ref: Backend and knowledge base reference.
        name: Human-readable knowledge base name.
        description: Optional knowledge base description.
        metadata: Backend-specific public metadata.
    """

    ref: KnowledgeBaseRef
    name: str
    description: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class KnowledgeBaseQuery:
    """Represent a backend-independent knowledge base query.

    Args:
        query: User query text.
        top_k: Maximum number of results requested from the backend.
        score_threshold: Optional backend-local relevance threshold.
        filters: Optional backend-specific metadata filters.
        umo: Optional unified message origin for session-aware retrieval.
    """

    query: str
    top_k: int = 5
    score_threshold: float | None = None
    filters: dict[str, Any] = field(default_factory=dict)
    umo: str | None = None


@dataclass(slots=True)
class KnowledgeBaseHit:
    """Represent one standardized knowledge base result.

    Args:
        ref: Backend and knowledge base that produced the result.
        content: Retrieved text content.
        source: Human-readable result source.
        rank: Result rank assigned by the backend, starting from one.
        score: Optional backend-local relevance score.
        document_id: Optional backend document identifier.
        chunk_id: Optional backend chunk identifier.
        source_uri: Optional URI for the original content.
        metadata: Backend-specific result metadata.
    """

    ref: KnowledgeBaseRef
    content: str
    source: str
    rank: int
    score: float | None = None
    document_id: str | None = None
    chunk_id: str | None = None
    source_uri: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class KnowledgeBaseResponse:
    """Represent one backend retrieval response.

    Args:
        hits: Results ordered from most to least relevant.
        warnings: Non-fatal backend warnings.
    """

    hits: list[KnowledgeBaseHit]
    warnings: list[str] = field(default_factory=list)


class KnowledgeBaseError(Exception):
    """Base exception for standardized knowledge base operations."""


class KnowledgeBaseBackendError(KnowledgeBaseError):
    """Raised when a knowledge base backend request fails."""


class KnowledgeBaseAuthenticationError(KnowledgeBaseBackendError):
    """Raised when a knowledge base backend rejects authentication."""


class KnowledgeBaseRateLimitError(KnowledgeBaseBackendError):
    """Raised when a knowledge base backend rate limit is reached."""


class KnowledgeBaseNotFoundError(KnowledgeBaseError):
    """Raised when a requested knowledge base does not exist."""


class KnowledgeBaseTimeoutError(KnowledgeBaseBackendError):
    """Raised when a knowledge base backend request times out."""


class BaseKnowledgeBaseBackend(ABC):
    """Define the public contract implemented by knowledge base backends."""

    @property
    @abstractmethod
    def backend_id(self) -> str:
        """Return the globally unique backend identifier."""
        raise NotImplementedError

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Return the human-readable backend name."""
        raise NotImplementedError

    @abstractmethod
    async def list_knowledge_bases(
        self,
        *,
        umo: str | None = None,
    ) -> list[KnowledgeBaseInfo]:
        """List knowledge bases exposed to a caller.

        Args:
            umo: Optional unified message origin for access filtering.

        Returns:
            Knowledge bases available to the caller.
        """
        raise NotImplementedError

    @abstractmethod
    async def retrieve(
        self,
        knowledge_base_ids: list[str],
        request: KnowledgeBaseQuery,
    ) -> KnowledgeBaseResponse:
        """Retrieve from selected backend knowledge bases.

        Args:
            knowledge_base_ids: Backend-local knowledge base identifiers.
            request: Standardized retrieval request.

        Returns:
            Standardized retrieval response.
        """
        raise NotImplementedError


__all__ = [
    "BaseKnowledgeBaseBackend",
    "KnowledgeBaseAuthenticationError",
    "KnowledgeBaseBackendError",
    "KnowledgeBaseError",
    "KnowledgeBaseHit",
    "KnowledgeBaseInfo",
    "KnowledgeBaseNotFoundError",
    "KnowledgeBaseQuery",
    "KnowledgeBaseRateLimitError",
    "KnowledgeBaseRef",
    "KnowledgeBaseResponse",
    "KnowledgeBaseTimeoutError",
]
