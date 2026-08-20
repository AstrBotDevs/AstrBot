from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.api.knowledge_base import (
    BaseKnowledgeBaseBackend,
    KnowledgeBaseHit,
    KnowledgeBaseInfo,
    KnowledgeBaseQuery,
    KnowledgeBaseRef,
    KnowledgeBaseResponse,
)
from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager


class MockBackend(BaseKnowledgeBaseBackend):
    """Configurable backend used to test manager orchestration."""

    def __init__(self, backend_id: str) -> None:
        self._backend_id = backend_id
        self.list_mock = AsyncMock(return_value=[])
        self.retrieve_mock = AsyncMock(return_value=KnowledgeBaseResponse(hits=[]))

    @property
    def backend_id(self) -> str:
        """Return the configured backend identifier."""
        return self._backend_id

    @property
    def display_name(self) -> str:
        """Return the configured backend name."""
        return self._backend_id.title()

    async def list_knowledge_bases(
        self,
        *,
        umo: str | None = None,
    ) -> list[KnowledgeBaseInfo]:
        """Delegate listing to the test mock.

        Args:
            umo: Optional unified message origin.

        Returns:
            Configured knowledge base descriptors.
        """
        return await self.list_mock(umo=umo)

    async def retrieve(
        self,
        knowledge_base_ids: list[str],
        request: KnowledgeBaseQuery,
    ) -> KnowledgeBaseResponse:
        """Delegate retrieval to the test mock.

        Args:
            knowledge_base_ids: Selected knowledge base identifiers.
            request: Standardized query.

        Returns:
            Configured retrieval response.
        """
        return await self.retrieve_mock(knowledge_base_ids, request)


@pytest.fixture
def manager() -> KnowledgeBaseManager:
    manager = KnowledgeBaseManager(MagicMock())
    manager.backends.clear()
    return manager


@pytest.mark.asyncio
async def test_list_registered_knowledge_bases_isolates_backend_failures(
    manager: KnowledgeBaseManager,
) -> None:
    available = MockBackend("available")
    available.list_mock.return_value = [
        KnowledgeBaseInfo(
            ref=KnowledgeBaseRef("available", "kb-1"),
            name="Available KB",
        )
    ]
    failing = MockBackend("failing")
    failing.list_mock.side_effect = RuntimeError("offline")
    manager.register_backend(available)
    manager.register_backend(failing)

    result = await manager.list_registered_knowledge_bases(umo="session-1")

    assert [item.name for item in result] == ["Available KB"]
    available.list_mock.assert_awaited_once_with(umo="session-1")


@pytest.mark.asyncio
async def test_list_registered_knowledge_bases_filters_backends(
    manager: KnowledgeBaseManager,
) -> None:
    selected = MockBackend("selected")
    skipped = MockBackend("skipped")
    manager.register_backend(selected)
    manager.register_backend(skipped)

    await manager.list_registered_knowledge_bases(backend_ids={"selected"})

    selected.list_mock.assert_awaited_once_with(umo=None)
    skipped.list_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_retrieve_groups_refs_and_merges_by_backend_rank(
    manager: KnowledgeBaseManager,
) -> None:
    first = MockBackend("first")
    first.retrieve_mock.return_value = KnowledgeBaseResponse(
        hits=[
            KnowledgeBaseHit(
                ref=KnowledgeBaseRef("first", "kb-1"),
                content="first-1",
                source="first",
                rank=1,
            ),
            KnowledgeBaseHit(
                ref=KnowledgeBaseRef("first", "kb-1"),
                content="first-2",
                source="first",
                rank=2,
            ),
        ]
    )
    second = MockBackend("second")
    second.retrieve_mock.return_value = KnowledgeBaseResponse(
        hits=[
            KnowledgeBaseHit(
                ref=KnowledgeBaseRef("second", "kb-2"),
                content="second-1",
                source="second",
                rank=1,
            ),
            KnowledgeBaseHit(
                ref=KnowledgeBaseRef("second", "kb-2"),
                content="second-2",
                source="second",
                rank=2,
            ),
        ],
        warnings=["partial response"],
    )
    manager.register_backend(first)
    manager.register_backend(second)
    request = KnowledgeBaseQuery(query="AstrBot", top_k=3)

    response = await manager.retrieve_from_backends(
        [
            KnowledgeBaseRef("first", "kb-1"),
            KnowledgeBaseRef("first", "kb-1"),
            KnowledgeBaseRef("second", "kb-2"),
        ],
        request,
    )

    first.retrieve_mock.assert_awaited_once_with(["kb-1"], request)
    second.retrieve_mock.assert_awaited_once_with(["kb-2"], request)
    assert [hit.content for hit in response.hits] == [
        "first-1",
        "second-1",
        "first-2",
    ]
    assert response.hits[0].ref == KnowledgeBaseRef("first", "kb-1")
    assert response.warnings == ["Second: partial response"]


@pytest.mark.asyncio
async def test_retrieve_isolates_unknown_and_failing_backends(
    manager: KnowledgeBaseManager,
) -> None:
    available = MockBackend("available")
    available.retrieve_mock.return_value = KnowledgeBaseResponse(
        hits=[
            KnowledgeBaseHit(
                ref=KnowledgeBaseRef("available", "kb-1"),
                content="result",
                source="available",
                rank=1,
            )
        ]
    )
    failing = MockBackend("failing")
    failing.retrieve_mock.side_effect = RuntimeError("offline")
    manager.register_backend(available)
    manager.register_backend(failing)

    response = await manager.retrieve_from_backends(
        [
            KnowledgeBaseRef("available", "kb-1"),
            KnowledgeBaseRef("failing", "kb-2"),
            KnowledgeBaseRef("missing", "kb-3"),
        ],
        KnowledgeBaseQuery(query="AstrBot"),
    )

    assert [hit.content for hit in response.hits] == ["result"]
    assert len(response.warnings) == 2
    assert "not registered" in response.warnings[0]
    assert "offline" in response.warnings[1]


@pytest.mark.asyncio
async def test_retrieve_rejects_invalid_backend_response(
    manager: KnowledgeBaseManager,
) -> None:
    invalid = MockBackend("invalid")
    invalid.retrieve_mock.return_value = object()
    manager.register_backend(invalid)

    response = await manager.retrieve_from_backends(
        [KnowledgeBaseRef("invalid", "kb-1")],
        KnowledgeBaseQuery(query="AstrBot"),
    )

    assert response.hits == []
    assert "invalid response" in response.warnings[0]


@pytest.mark.asyncio
async def test_retrieve_filters_invalid_hits(
    manager: KnowledgeBaseManager,
) -> None:
    backend = MockBackend("example")
    backend.retrieve_mock.return_value = KnowledgeBaseResponse(
        hits=[
            KnowledgeBaseHit(
                ref=KnowledgeBaseRef("example", "kb-1"),
                content="",
                source="empty",
                rank=1,
            ),
            KnowledgeBaseHit(
                ref=KnowledgeBaseRef("example", "kb-1"),
                content="valid",
                source="docs",
                rank=1,
            ),
        ]
    )
    manager.register_backend(backend)

    response = await manager.retrieve_from_backends(
        [KnowledgeBaseRef("example", "kb-1")],
        KnowledgeBaseQuery(query="AstrBot"),
    )

    assert [hit.content for hit in response.hits] == ["valid"]
    assert "invalid result" in response.warnings[0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ref",
    [
        KnowledgeBaseRef("other", "kb-1"),
        KnowledgeBaseRef("example", "not-selected"),
    ],
)
async def test_retrieve_filters_hits_with_mismatched_references(
    manager: KnowledgeBaseManager,
    ref: KnowledgeBaseRef,
) -> None:
    backend = MockBackend("example")
    backend.retrieve_mock.return_value = KnowledgeBaseResponse(
        hits=[
            KnowledgeBaseHit(
                ref=ref,
                content="mismatched",
                source="docs",
                rank=1,
            )
        ]
    )
    manager.register_backend(backend)

    response = await manager.retrieve_from_backends(
        [KnowledgeBaseRef("example", "kb-1")],
        KnowledgeBaseQuery(query="AstrBot"),
    )

    assert response.hits == []
    assert "invalid result" in response.warnings[0]
