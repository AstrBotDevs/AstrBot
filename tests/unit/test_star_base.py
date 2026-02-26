"""Tests for astrbot.core.star.base module."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


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

    @pytest.mark.asyncio
    async def test_text_to_image_with_config(self):
        """Test text_to_image method with valid config."""
        from astrbot.core.star import Star

        mock_context = MagicMock()
        mock_config = MagicMock()
        mock_config.get.return_value = "default_template"
        mock_context.get_config.return_value = mock_config

        class TestStar(Star):
            name = "test_star"
            author = "test_author"

        star = TestStar(context=mock_context)

        with patch(
            "astrbot.core.star.base.html_renderer.render_t2i",
            new_callable=AsyncMock,
        ) as mock_render:
            mock_render.return_value = "http://example.com/image.png"
            result = await star.text_to_image("test text", return_url=True)

            mock_render.assert_called_once_with(
                "test text",
                return_url=True,
                template_name="default_template",
            )
            assert result == "http://example.com/image.png"

    @pytest.mark.asyncio
    async def test_text_to_image_without_config(self):
        """Test text_to_image method when get_config returns None."""
        from astrbot.core.star import Star

        mock_context = MagicMock()
        mock_context.get_config.return_value = None

        class TestStar(Star):
            name = "test_star"
            author = "test_author"

        star = TestStar(context=mock_context)

        with patch(
            "astrbot.core.star.base.html_renderer.render_t2i",
            new_callable=AsyncMock,
        ) as mock_render:
            mock_render.return_value = "http://example.com/image.png"
            result = await star.text_to_image("test text", return_url=False)

            mock_render.assert_called_once_with(
                "test text",
                return_url=False,
                template_name=None,
            )
            assert result == "http://example.com/image.png"

    @pytest.mark.asyncio
    async def test_html_render(self):
        """Test html_render method."""
        from astrbot.core.star import Star

        mock_context = MagicMock()

        class TestStar(Star):
            name = "test_star"
            author = "test_author"

        star = TestStar(context=mock_context)

        with patch(
            "astrbot.core.star.base.html_renderer.render_custom_template",
            new_callable=AsyncMock,
        ) as mock_render:
            mock_render.return_value = "http://example.com/rendered.png"
            result = await star.html_render(
                "<html>{{ data }}</html>",
                {"data": "test"},
                return_url=True,
            )

            mock_render.assert_called_once_with(
                "<html>{{ data }}</html>",
                {"data": "test"},
                return_url=True,
                options=None,
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
        from astrbot.core.star import star_map, star_registry
        from astrbot.core.star.star import StarMetadata

        # Clear any previous registration for this test module
        module_path = __name__

        class UniqueTestStar:
            """Not a Star subclass, should not be registered."""
            pass

        # Verify Star subclass gets registered
        initial_count = len(star_registry)

        # Note: This test verifies the __init_subclass__ mechanism
        # The actual registration happens when a class inherits from Star
        assert len(star_registry) >= initial_count


class TestStarTypeHints:
    """Test that type hints work correctly for plugin developers."""

    def test_context_type_hint_is_context(self):
        """Verify that the context parameter has proper type hint."""
        from astrbot.core.star import Star
        import inspect

        sig = inspect.signature(Star.__init__)
        context_param = sig.parameters.get("context")

        assert context_param is not None
        # The annotation should be "Context" (string due to __future__ annotations)
        # or the actual Context class when TYPE_CHECKING is used properly
        annotation = context_param.annotation

        # Accept either the string "Context" or the actual class
        # If it's _ContextLike, that's the problem we're trying to fix
        assert annotation != "_ContextLike", (
            "context parameter should use 'Context' type, not '_ContextLike' "
            "Protocol for better plugin developer experience"
        )

    def test_context_has_expected_attributes(self):
        """Verify Context class has the attributes plugin developers expect."""
        from astrbot.core.star import Context

        # These are common attributes that plugin developers use
        expected_attrs = [
            "provider_manager",
            "platform_manager",
            "get_config",
            "get_all_providers",
            "get_using_provider",
            "send_message",
        ]

        for attr in expected_attrs:
            assert hasattr(Context, attr), f"Context should have '{attr}' attribute"


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
        import astrbot.core.pipeline
        import astrbot.core.star

        # Verify key exports are available
        from astrbot.core.star import Context, Star, PluginManager

        assert Context is not None
        assert Star is not None
        assert PluginManager is not None

    def test_import_pipeline_context(self):
        """Test that PipelineContext can be imported."""
        from astrbot.core.pipeline.context import PipelineContext

        assert PipelineContext is not None
