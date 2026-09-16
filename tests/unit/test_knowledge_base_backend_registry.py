from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.api.knowledge_base import (
    BaseKnowledgeBaseBackend,
    KnowledgeBaseInfo,
    KnowledgeBaseQuery,
    KnowledgeBaseResponse,
)
from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager
from astrbot.core.star.context import Context


class StubBackend(BaseKnowledgeBaseBackend):
    """Minimal backend used to test registration behavior."""

    def __init__(
        self,
        backend_id: str = "example",
        display_name: str = "Example",
    ) -> None:
        self._backend_id = backend_id
        self._display_name = display_name

    @property
    def backend_id(self) -> str:
        """Return the configured test identifier."""
        return self._backend_id

    @property
    def display_name(self) -> str:
        """Return the test display name."""
        return self._display_name

    async def list_knowledge_bases(
        self,
        *,
        umo: str | None = None,
    ) -> list[KnowledgeBaseInfo]:
        """Return no knowledge bases.

        Args:
            umo: Optional unified message origin.

        Returns:
            An empty list.
        """
        return []

    async def retrieve(
        self,
        knowledge_base_ids: list[str],
        request: KnowledgeBaseQuery,
    ) -> KnowledgeBaseResponse:
        """Return an empty response.

        Args:
            knowledge_base_ids: Selected knowledge base identifiers.
            request: Standardized query.

        Returns:
            An empty response.
        """
        return KnowledgeBaseResponse(hits=[])


@pytest.fixture
def manager() -> KnowledgeBaseManager:
    return KnowledgeBaseManager(MagicMock())


@pytest.mark.asyncio
async def test_register_and_unregister_backend(manager: KnowledgeBaseManager) -> None:
    backend = StubBackend()

    manager.register_backend(backend)

    assert manager.backends["example"] is backend
    assert "builtin" in manager.backends

    await manager.unregister_backend("example")

    assert set(manager.backends) == {"builtin"}


def test_duplicate_backend_id_is_rejected(manager: KnowledgeBaseManager) -> None:
    manager.register_backend(StubBackend())

    with pytest.raises(ValueError, match="already registered"):
        manager.register_backend(StubBackend())


@pytest.mark.asyncio
async def test_backend_can_be_registered_again_after_plugin_reload(
    manager: KnowledgeBaseManager,
) -> None:
    first_backend = StubBackend()
    reloaded_backend = StubBackend()

    manager.register_backend(first_backend)
    await manager.unregister_backend("example")
    await manager.unregister_backend("example")
    manager.register_backend(reloaded_backend)

    assert manager.backends["example"] is reloaded_backend


@pytest.mark.parametrize(
    "backend_id",
    ["", " example ", "with space", "invalid/path", "中文", "x" * 129],
)
def test_invalid_backend_id_is_rejected(
    manager: KnowledgeBaseManager,
    backend_id: str,
) -> None:
    with pytest.raises(ValueError, match="backend ID"):
        manager.register_backend(StubBackend(backend_id=backend_id))


def test_empty_display_name_is_rejected(manager: KnowledgeBaseManager) -> None:
    with pytest.raises(ValueError, match="display name"):
        manager.register_backend(StubBackend(display_name=" "))


@pytest.mark.asyncio
async def test_builtin_backend_cannot_be_unregistered(
    manager: KnowledgeBaseManager,
) -> None:
    with pytest.raises(ValueError, match="cannot be unregistered"):
        await manager.unregister_backend("builtin")


@pytest.mark.asyncio
async def test_context_forwards_backend_registration() -> None:
    context = Context.__new__(Context)
    context.kb_manager = MagicMock()
    context.kb_manager.unregister_backend = AsyncMock()
    backend = StubBackend()

    context.register_knowledge_base_backend(backend)
    await context.unregister_knowledge_base_backend("example")

    context.kb_manager.register_backend.assert_called_once_with(backend)
    context.kb_manager.unregister_backend.assert_called_once_with("example")
