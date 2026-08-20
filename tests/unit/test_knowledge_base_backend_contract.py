from dataclasses import FrozenInstanceError

import pytest

from astrbot.api.knowledge_base import (
    KNOWLEDGE_BASE_BACKEND_API_VERSION,
    BaseKnowledgeBaseBackend,
    KnowledgeBaseBackendError,
    KnowledgeBaseHit,
    KnowledgeBaseInfo,
    KnowledgeBaseQuery,
    KnowledgeBaseRef,
    KnowledgeBaseResponse,
)


class ExampleBackend(BaseKnowledgeBaseBackend):
    """Minimal backend implementation used to verify the public contract."""

    @property
    def backend_id(self) -> str:
        """Return the test backend identifier."""
        return "example"

    @property
    def display_name(self) -> str:
        """Return the test backend name."""
        return "Example"

    async def list_knowledge_bases(
        self,
        *,
        umo: str | None = None,
    ) -> list[KnowledgeBaseInfo]:
        """Return one test knowledge base.

        Args:
            umo: Optional unified message origin.

        Returns:
            One knowledge base descriptor.
        """
        return [
            KnowledgeBaseInfo(
                ref=KnowledgeBaseRef(self.backend_id, "kb-1"),
                name="Test KB",
                metadata={"umo": umo},
            )
        ]

    async def retrieve(
        self,
        knowledge_base_ids: list[str],
        request: KnowledgeBaseQuery,
    ) -> KnowledgeBaseResponse:
        """Return one test hit.

        Args:
            knowledge_base_ids: Selected knowledge base identifiers.
            request: Standardized query.

        Returns:
            One result containing the query.
        """
        return KnowledgeBaseResponse(
            hits=[
                KnowledgeBaseHit(
                    content=request.query,
                    source=knowledge_base_ids[0],
                    rank=1,
                )
            ]
        )


@pytest.mark.asyncio
async def test_backend_contract_supports_listing_and_retrieval() -> None:
    backend = ExampleBackend()

    knowledge_bases = await backend.list_knowledge_bases(umo="session-1")
    response = await backend.retrieve(
        ["kb-1"],
        KnowledgeBaseQuery(query="AstrBot", umo="session-1"),
    )

    assert backend.api_version == KNOWLEDGE_BASE_BACKEND_API_VERSION
    assert knowledge_bases[0].ref == KnowledgeBaseRef("example", "kb-1")
    assert knowledge_bases[0].metadata == {"umo": "session-1"}
    assert response.hits[0].content == "AstrBot"
    assert response.hits[0].source == "kb-1"


def test_query_and_references_are_immutable() -> None:
    query = KnowledgeBaseQuery(query="AstrBot")
    reference = KnowledgeBaseRef("example", "kb-1")

    with pytest.raises(FrozenInstanceError):
        query.query = "changed"
    with pytest.raises(FrozenInstanceError):
        reference.backend_id = "changed"


def test_backend_error_is_part_of_public_error_hierarchy() -> None:
    error = KnowledgeBaseBackendError("backend failed")

    assert str(error) == "backend failed"


def test_backend_contract_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        BaseKnowledgeBaseBackend()
