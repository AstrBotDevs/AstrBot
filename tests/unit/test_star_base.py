"""The plugin SDK delegates rendering and keeps registry state test-local."""

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from astrbot.api.star import Context as PublicContext
from astrbot.api.star import Star as PublicStar
from astrbot.core.star import base
from astrbot.core.star.context import Context
from astrbot.core.star.star import StarMetadata


@pytest.fixture(autouse=True)
def isolated_registration(monkeypatch):
    monkeypatch.setattr(base, "star_map", {})
    monkeypatch.setattr(base, "star_registry", [])


@pytest.fixture
def context():
    return SimpleNamespace(
        get_config=Mock(
            return_value={
                "t2i_active_template": "default_template",
                "t2i_endpoint": "https://renderer.invalid",
            }
        ),
        html_renderer=SimpleNamespace(
            render_t2i=AsyncMock(return_value="rendered.png"),
            render_custom_template=AsyncMock(return_value="custom.png"),
        ),
    )


@pytest.fixture
def plugin(context):
    class TestPlugin(base.Star):
        name = "test_plugin"
        author = "test_author"

    return TestPlugin(context)


def test_sdk_exports_reference_the_real_implementation():
    assert PublicStar is base.Star
    assert PublicContext is Context


def test_plugin_initialization_registers_metadata_and_preserves_context(
    plugin, context
):
    assert plugin.context is context
    metadata = base.star_map[type(plugin).__module__]
    assert metadata.star_cls_type is type(plugin)
    assert base.star_registry == [metadata]


def test_plugin_initialization_logs_the_effective_level(monkeypatch, context):
    plugin_logger = Mock(spec=logging.Logger)
    plugin_logger.getEffectiveLevel.return_value = logging.WARNING
    factory, core_logger = Mock(return_value=plugin_logger), Mock()
    monkeypatch.setattr(base.LogManager, "get_plugin_logger", factory)
    monkeypatch.setattr(base, "logger", core_logger)

    class LevelPlugin(base.Star):
        name = "level_plugin"

    plugin = LevelPlugin(context)
    assert plugin.logger is plugin_logger
    factory.assert_called_once_with("level_plugin")
    core_logger.info.assert_called_once_with(
        "Plugin %s log level: %s.", "level_plugin", "WARNING"
    )


def test_plugin_with_read_only_logger_keeps_its_logger(context):
    custom_logger = logging.getLogger("test.read_only_plugin")

    class CustomLoggerPlugin(base.Star):
        @property
        def logger(self):
            return custom_logger

    assert CustomLoggerPlugin(context).logger is custom_logger


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("config", "template", "expected_template", "expected_endpoint"),
    [
        (
            {
                "t2i_active_template": "default_template",
                "t2i_endpoint": "https://renderer.invalid",
            },
            None,
            "default_template",
            "https://renderer.invalid",
        ),
        (
            {
                "t2i_active_template": "default_template",
                "t2i_endpoint": "https://renderer.invalid",
            },
            "mine",
            "mine",
            "https://renderer.invalid",
        ),
        (None, None, None, None),
        ({"t2i_endpoint": ""}, None, None, None),
    ],
)
@pytest.mark.parametrize("return_url", [True, False])
async def test_text_rendering_uses_session_configuration(
    plugin, context, config, template, expected_template, expected_endpoint, return_url
):
    context.get_config.return_value = config
    result = await plugin.text_to_image(
        "text",
        return_url=return_url,
        template_name=template,
        umo="test:GroupMessage:one",
    )
    assert result == "rendered.png"
    context.get_config.assert_called_once_with("test:GroupMessage:one")
    context.html_renderer.render_t2i.assert_awaited_once_with(
        "text",
        return_url=return_url,
        template_name=expected_template,
        endpoint=expected_endpoint,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("config", "endpoint"),
    [
        (None, None),
        ({"t2i_endpoint": "https://renderer.invalid"}, "https://renderer.invalid"),
    ],
)
async def test_html_renderer_receives_data_options_and_session_endpoint(
    plugin, context, config, endpoint
):
    context.get_config.return_value = config
    data, options = {"data": "text"}, {"width": 400}
    result = await plugin.html_render(
        "<p>{{ data }}</p>",
        data,
        return_url=False,
        options=options,
        umo="test:FriendMessage:one",
    )
    assert result == "custom.png"
    context.get_config.assert_called_once_with("test:FriendMessage:one")
    context.html_renderer.render_custom_template.assert_awaited_once_with(
        "<p>{{ data }}</p>",
        data,
        return_url=False,
        options=options,
        endpoint=endpoint,
    )


@pytest.mark.asyncio
async def test_base_lifecycle_is_awaitable_and_override_can_track_resources(context):
    assert await base.Star(context).initialize() is None
    assert await base.Star(context).terminate() is None
    events = []

    class LifecyclePlugin(base.Star):
        async def initialize(self):
            events.append("open")

        async def terminate(self):
            events.append("close")

    plugin = LifecyclePlugin(context)
    await plugin.initialize()
    await plugin.terminate()
    assert events == ["open", "close"]


@pytest.mark.parametrize(
    ("name", "author", "expected"),
    [
        (None, None, "unknown/unknown"),
        ("Hello", "AstrBot", "astrbot/hello"),
        ("A/B", "C", "c/a_b"),
        ("OnlyName", None, "unknown/onlyname"),
        (None, "OnlyAuthor", "onlyauthor/unknown"),
    ],
)
def test_plugin_identity_is_computed_after_metadata_is_loaded(name, author, expected):
    metadata = StarMetadata()
    metadata.name, metadata.author = name, author
    assert metadata.plugin_id == expected
    metadata.name, metadata.author = "new", "author"
    assert metadata.plugin_id == "author/new"
