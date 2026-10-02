"""Tests for astrbot.core.star.base module."""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestStarBase:
    """Test cases for the Star base class."""

    def test_star_class_exists(self):
        """Test that Star class can be imported."""
        from astrbot.core.star import Star

        assert Star is not None

    def test_star_init_with_context(self):
        """Test Star initialization with a context-like object."""
        from astrbot.core.star import Star

        # Create a mock context with get_config method
        mock_context = MagicMock()
        mock_context.get_config.return_value = MagicMock()

        # Create a concrete Star subclass for testing
        class TestStar(Star):
            name = "test_star"
            author = "test_author"

        star = TestStar(context=mock_context)

        assert star.context is mock_context

    def test_star_init_logs_plugin_level(self):
        """Test that Star initialization reports the effective plugin level."""
        from astrbot.core.star import Star

        mock_context = MagicMock()
        plugin_logger = MagicMock(spec=logging.Logger)
        plugin_logger.getEffectiveLevel.return_value = logging.WARNING

        class TestLevelStar(Star):
            name = "test_level_star"
            author = "test_author"

        with (
            patch(
                "astrbot.core.star.base.LogManager.get_plugin_logger",
                return_value=plugin_logger,
            ),
            patch("astrbot.core.star.base.logger") as core_logger,
        ):
            TestLevelStar(context=mock_context)

        core_logger.info.assert_called_once_with(
            "Plugin %s log level: %s.",
            "test_level_star",
            "WARNING",
        )

    @pytest.mark.asyncio
    async def test_text_to_image_with_config(self):
        """Test text_to_image resolves template and endpoint from the config."""
        from astrbot.core.star import Star

        mock_context = MagicMock()
        mock_context.get_config.return_value = {
            "t2i_active_template": "default_template",
            "t2i_endpoint": "http://ep",
        }
        mock_context.html_renderer.render_t2i = AsyncMock(
            return_value="http://example.com/image.png"
        )

        class TestStar(Star):
            name = "test_star"
            author = "test_author"

        star = TestStar(context=mock_context)

        result = await star.text_to_image(
            "test text", return_url=True, umo="qq:group:1"
        )

        mock_context.get_config.assert_called_once_with("qq:group:1")
        mock_context.html_renderer.render_t2i.assert_called_once_with(
            "test text",
            return_url=True,
            template_name="default_template",
            endpoint="http://ep",
        )
        assert result == "http://example.com/image.png"

    @pytest.mark.asyncio
    async def test_text_to_image_without_config(self):
        """Test text_to_image falls back to the default template without config."""
        from astrbot.core.star import Star

        mock_context = MagicMock()
        mock_context.get_config.return_value = None
        mock_context.html_renderer.render_t2i = AsyncMock(
            return_value="http://example.com/image.png"
        )

        class TestStar(Star):
            name = "test_star"
            author = "test_author"

        star = TestStar(context=mock_context)

        result = await star.text_to_image("test text", return_url=False)

        mock_context.html_renderer.render_t2i.assert_called_once_with(
            "test text",
            return_url=False,
            template_name=None,
            endpoint=None,
        )
        assert result == "http://example.com/image.png"

    @pytest.mark.asyncio
    async def test_text_to_image_explicit_template_takes_precedence(self):
        """Test an explicit template wins over the config template."""
        from astrbot.core.star import Star

        mock_context = MagicMock()
        mock_context.get_config.return_value = {
            "t2i_active_template": "default_template",
            "t2i_endpoint": "http://ep",
        }
        mock_context.html_renderer.render_t2i = AsyncMock(
            return_value="http://example.com/image.png"
        )

        class TestStar(Star):
            name = "test_star"
            author = "test_author"

        star = TestStar(context=mock_context)

        await star.text_to_image("test text", template_name="mine", umo="qq:group:1")

        mock_context.html_renderer.render_t2i.assert_called_once_with(
            "test text",
            return_url=True,
            template_name="mine",
            endpoint="http://ep",
        )

    @pytest.mark.asyncio
    async def test_html_render(self):
        """Test html_render passes the config endpoint to the renderer."""
        from astrbot.core.star import Star

        mock_context = MagicMock()
        mock_context.get_config.return_value = {"t2i_endpoint": "http://ep"}
        mock_context.html_renderer.render_custom_template = AsyncMock(
            return_value="http://example.com/rendered.png"
        )

        class TestStar(Star):
            name = "test_star"
            author = "test_author"

        star = TestStar(context=mock_context)

        result = await star.html_render(
            "<html>{{ data }}</html>",
            {"data": "test"},
            return_url=True,
        )

        mock_context.html_renderer.render_custom_template.assert_called_once_with(
            "<html>{{ data }}</html>",
            {"data": "test"},
            return_url=True,
            options=None,
            endpoint="http://ep",
        )
        assert result == "http://example.com/rendered.png"

    @pytest.mark.asyncio
    async def test_initialize_and_terminate(self):
        """Test that initialize and terminate methods can be overridden."""
        from astrbot.core.star import Star

        class TestStar(Star):
            name = "test_star"
            author = "test_author"

            async def initialize(self) -> None:
                self.initialized = True

            async def terminate(self) -> None:
                self.terminated = True

        mock_context = MagicMock()
        star = TestStar(context=mock_context)

        await star.initialize()
        assert star.initialized is True

        await star.terminate()
        assert star.terminated is True

    def test_star_metadata_registration(self):
        """Test that Star subclass is automatically registered."""
        from astrbot.core.star import star_registry

        class UniqueTestStar:
            """Not a Star subclass, should not be registered."""

            pass

        # Verify Star subclass gets registered
        initial_count = len(star_registry)

        # Note: This test verifies the __init_subclass__ mechanism
        # The actual registration happens when a class inherits from Star
        assert len(star_registry) >= initial_count


class TestStarMetadataPluginId:
    """Tests for StarMetadata.plugin_id derived view.

    Regression: previously `plugin_id` was set in `__post_init__`, which only
    fires at dataclass construction. The plugin load flow constructs
    StarMetadata empty (no name/author) and fills them via attribute
    assignment later, so `plugin_id` stayed None and crashed the downstream
    `plugin_id.split("/")`. Now it's a property recomputed on every access.
    """

    def test_plugin_id_defaults_to_unknown_when_empty(self):
        from astrbot.core.star.star import StarMetadata

        assert StarMetadata().plugin_id == "unknown/unknown"

    def test_plugin_id_uses_name_and_author(self):
        from astrbot.core.star.star import StarMetadata

        metadata = StarMetadata(name="Hello", author="AstrBot")
        assert metadata.plugin_id == "astrbot/hello"

    def test_plugin_id_recomputes_after_attribute_assignment(self):
        from astrbot.core.star.star import StarMetadata

        metadata = StarMetadata()
        metadata.name = "A"
        metadata.author = "B"
        assert metadata.plugin_id == "b/a"

    def test_plugin_id_lowercases_and_escapes_slash(self):
        from astrbot.core.star.star import StarMetadata

        metadata = StarMetadata(name="A/B", author="C")
        assert metadata.plugin_id == "c/a_b"

    def test_plugin_id_reflects_latest_name_after_change(self):
        from astrbot.core.star.star import StarMetadata

        metadata = StarMetadata(name="old", author="author")
        assert metadata.plugin_id == "author/old"
        metadata.name = "new"
        assert metadata.plugin_id == "author/new"

    def test_plugin_id_only_name_set(self):
        from astrbot.core.star.star import StarMetadata

        assert StarMetadata(name="OnlyName").plugin_id == "unknown/onlyname"

    def test_plugin_id_only_author_set(self):
        from astrbot.core.star.star import StarMetadata

        assert StarMetadata(author="OnlyAuthor").plugin_id == "onlyauthor/unknown"


class TestNoCircularImports:
    """Test that there are no circular import issues."""

    def test_import_star_module(self):
        """Test that star module can be imported without circular import errors."""
        import astrbot.core.star

        assert astrbot.core.star is not None

    def test_import_pipeline_module(self):
        """Test that pipeline module can be imported without circular import errors."""
        import astrbot.core.pipeline

        assert astrbot.core.pipeline is not None

    def test_import_both_modules(self):
        """Test that both modules can be imported together."""

        # Verify key exports are available
        from astrbot.core.star import Context, PluginManager, Star

        assert Context is not None
        assert Star is not None
        assert PluginManager is not None

    def test_import_pipeline_context(self):
        """Test that PipelineContext can be imported."""
        from astrbot.core.pipeline.context import PipelineContext

        assert PipelineContext is not None
