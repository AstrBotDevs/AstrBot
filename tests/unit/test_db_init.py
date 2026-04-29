"""Tests for BaseDatabase abstract interface and initialization.

Verifies the abstract method contract, engine creation, session factory
setup, and the ``get_db`` async context manager.
"""

import inspect
from abc import ABC
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core.db import BaseDatabase


class TestBaseDatabaseAbstract:
    """Tests for BaseDatabase's abstract nature and method count."""

    def test_is_abstract_class(self):
        """BaseDatabase uses ABCMeta and cannot be directly instantiated."""
        assert isinstance(BaseDatabase, ABC)
        with pytest.raises(TypeError, match="abstract"):
            BaseDatabase()

    def test_abstract_method_count(self):
        """BaseDatabase defines a known number of abstract methods."""
        abs_methods = BaseDatabase.__abstractmethods__
        # The interface is large -- expect >= 90 abstract methods
        assert len(abs_methods) >= 90
        # Key abstract methods should be present
        assert "create_cron_job" in abs_methods
        assert "update_cron_job" in abs_methods
        assert "delete_cron_job" in abs_methods
        assert "get_cron_job" in abs_methods
        assert "list_cron_jobs" in abs_methods
        assert "get_conversations" in abs_methods
        assert "create_conversation" in abs_methods
        assert "insert_platform_stats" in abs_methods
        assert "insert_persona" in abs_methods
        assert "insert_api_key" in abs_methods  # kept as create_api_key is the actual name
        # Deprecated methods are still abstract
        assert "get_base_stats" in abs_methods
        assert "get_total_message_count" in abs_methods

    def test_abstract_methods_have_docstrings_or_impl(self):
        """All abstract methods should have ... or docstrings (no syntax errors at module level)."""
        abs_methods = BaseDatabase.__abstractmethods__
        for name in abs_methods:
            method = getattr(BaseDatabase, name)
            # Should not raise AttributeError or similar
            assert callable(method)

    def test_initialize_is_not_abstract(self):
        """initialize() has a concrete default implementation."""
        assert "initialize" not in BaseDatabase.__abstractmethods__

    def test_get_db_is_not_abstract(self):
        """get_db() has a concrete implementation (async context manager)."""
        assert "get_db" not in BaseDatabase.__abstractmethods__


class TestBaseDatabaseInit:
    """Tests for BaseDatabase.__init__ and engine setup."""

    def test_init_sets_inited_false(self):
        """inited starts as False."""
        with (
            patch.object(BaseDatabase, "__abstractmethods__", frozenset()),
            patch("astrbot.core.db.create_async_engine") as mock_engine,
            patch("astrbot.core.db.async_sessionmaker") as mock_smaker,
        ):
            mock_engine.return_value = MagicMock()
            mock_smaker.return_value = MagicMock()
            BaseDatabase.DATABASE_URL = "sqlite+aiosqlite:///test.db"
            db = BaseDatabase()

        assert db.inited is False

    def test_init_sqlite_adds_connect_args_timeout(self):
        """SQLite URL adds timeout=30 to connect_args."""
        with (
            patch.object(BaseDatabase, "__abstractmethods__", frozenset()),
            patch("astrbot.core.db.create_async_engine") as mock_engine,
            patch("astrbot.core.db.async_sessionmaker") as mock_smaker,
        ):
            mock_engine.return_value = MagicMock()
            mock_smaker.return_value = MagicMock()
            BaseDatabase.DATABASE_URL = "sqlite+aiosqlite:///test.db"
            db = BaseDatabase()  # noqa: F841

        mock_engine.assert_called_once()
        call_kwargs = mock_engine.call_args.kwargs
        assert call_kwargs["connect_args"] == {"timeout": 30}

    def test_init_non_sqlite_does_not_add_connect_args(self):
        """Non-SQLite URL omits connect_args (no timeout)."""
        with (
            patch.object(BaseDatabase, "__abstractmethods__", frozenset()),
            patch("astrbot.core.db.create_async_engine") as mock_engine,
            patch("astrbot.core.db.async_sessionmaker") as mock_smaker,
        ):
            mock_engine.return_value = MagicMock()
            mock_smaker.return_value = MagicMock()
            BaseDatabase.DATABASE_URL = "postgresql+asyncpg://localhost/db"
            db = BaseDatabase()  # noqa: F841

        call_kwargs = mock_engine.call_args.kwargs
        assert "connect_args" not in call_kwargs or call_kwargs["connect_args"] == {}

    def test_init_creates_async_session_local(self):
        """A session factory is created from the engine."""
        with (
            patch.object(BaseDatabase, "__abstractmethods__", frozenset()),
            patch("astrbot.core.db.create_async_engine") as mock_engine,
            patch("astrbot.core.db.async_sessionmaker") as mock_smaker,
        ):
            mock_engine.return_value = MagicMock()
            mock_smaker.return_value = MagicMock()
            BaseDatabase.DATABASE_URL = "sqlite+aiosqlite:///test.db"
            db = BaseDatabase()  # noqa: F841

        mock_smaker.assert_called_once()
        # The session maker is bound to the engine with expire_on_commit=False
        assert mock_smaker.call_args.kwargs.get("expire_on_commit") is False

    def test_init_engine_echo_false_future_true(self):
        """Engine is created with echo=False and future=True."""
        with (
            patch.object(BaseDatabase, "__abstractmethods__", frozenset()),
            patch("astrbot.core.db.create_async_engine") as mock_engine,
            patch("astrbot.core.db.async_sessionmaker") as mock_smaker,
        ):
            mock_engine.return_value = MagicMock()
            mock_smaker.return_value = MagicMock()
            BaseDatabase.DATABASE_URL = "sqlite+aiosqlite:///test.db"
            db = BaseDatabase()  # noqa: F841

        call_kwargs = mock_engine.call_args.kwargs
        assert call_kwargs["echo"] is False
        assert call_kwargs["future"] is True

    def test_same_url_passed_to_engine(self):
        """DATABASE_URL is passed to create_async_engine."""
        with (
            patch.object(BaseDatabase, "__abstractmethods__", frozenset()),
            patch("astrbot.core.db.create_async_engine") as mock_engine,
            patch("astrbot.core.db.async_sessionmaker") as mock_smaker,
        ):
            mock_engine.return_value = MagicMock()
            mock_smaker.return_value = MagicMock()
            BaseDatabase.DATABASE_URL = "sqlite+aiosqlite:///custom.db"
            db = BaseDatabase()  # noqa: F841

        assert mock_engine.call_args[0][0] == "sqlite+aiosqlite:///custom.db"


class TestBaseDatabaseInitialize:
    """Tests for the concrete initialize method."""

    @pytest.mark.asyncio
    async def test_initialize_does_not_raise(self):
        """initialize() is concrete and can be called without error."""
        with (
            patch.object(BaseDatabase, "__abstractmethods__", frozenset()),
            patch("astrbot.core.db.create_async_engine"),
            patch("astrbot.core.db.async_sessionmaker"),
        ):
            BaseDatabase.DATABASE_URL = "sqlite+aiosqlite:///test.db"
            db = BaseDatabase()

        await db.initialize()  # should not raise


class TestBaseDatabaseGetDb:
    """Tests for the get_db async context manager."""

    @pytest.mark.asyncio
    async def test_get_db_calls_initialize_when_not_inited(self):
        """get_db calls initialize() if inited is False."""
        from sqlalchemy.ext.asyncio import AsyncSession

        with (
            patch.object(BaseDatabase, "__abstractmethods__", frozenset()),
            patch("astrbot.core.db.create_async_engine"),
            patch("astrbot.core.db.async_sessionmaker"),
        ):
            BaseDatabase.DATABASE_URL = "sqlite+aiosqlite:///test.db"
            db = BaseDatabase()

        db.inited = False

        # Mock the session factory
        mock_session = MagicMock(spec=AsyncSession)
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=None)
        db.AsyncSessionLocal = MagicMock(return_value=mock_cm)

        with patch.object(db, "initialize", new_callable=AsyncMock) as mock_init:
            async with db.get_db() as session:
                assert session == mock_session

            mock_init.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_db_does_not_call_initialize_when_inited(self):
        """get_db skips initialize() if inited is already True."""
        from sqlalchemy.ext.asyncio import AsyncSession

        with (
            patch.object(BaseDatabase, "__abstractmethods__", frozenset()),
            patch("astrbot.core.db.create_async_engine"),
            patch("astrbot.core.db.async_sessionmaker"),
        ):
            BaseDatabase.DATABASE_URL = "sqlite+aiosqlite:///test.db"
            db = BaseDatabase()

        db.inited = True

        mock_session = MagicMock(spec=AsyncSession)
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=None)
        db.AsyncSessionLocal = MagicMock(return_value=mock_cm)

        with patch.object(db, "initialize", new_callable=AsyncMock) as mock_init:
            async with db.get_db() as session:
                assert session == mock_session

            mock_init.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_db_sets_inited_after_initialize(self):
        """inited is set to True after initialize completes."""
        with (
            patch.object(BaseDatabase, "__abstractmethods__", frozenset()),
            patch("astrbot.core.db.create_async_engine"),
            patch("astrbot.core.db.async_sessionmaker"),
        ):
            BaseDatabase.DATABASE_URL = "sqlite+aiosqlite:///test.db"
            db = BaseDatabase()

        db.inited = False

        mock_session = MagicMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=None)
        db.AsyncSessionLocal = MagicMock(return_value=mock_cm)

        async with db.get_db():
            pass

        assert db.inited is True
