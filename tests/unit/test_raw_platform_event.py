"""Tests for RawPlatformEvent: stop_event pipeline interception and plugin_set filtering."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core.platform.platform import PlatformStatus
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.platform.raw_platform_event import RawPlatformEvent
from astrbot.core.star.star import StarMetadata
from astrbot.core.star.star_handler import EventType, StarHandlerMetadata


def _make_platform_meta(
    name: str = "qq_official_webhook", platform_id: str = "qq1"
) -> PlatformMetadata:
    return PlatformMetadata(name=name, description="test", id=platform_id)


def _make_handler(
    handler_fn: AsyncMock | None = None,
    module_path: str = "test_module",
    extras: dict | None = None,
) -> StarHandlerMetadata:
    if handler_fn is None:
        handler_fn = AsyncMock()
    return StarHandlerMetadata(
        event_type=EventType.OnRawPlatformEvent,
        handler_full_name=f"{module_path}_{handler_fn.__name__ or 'handler'}",
        handler_name=handler_fn.__name__ or "handler",
        handler_module_path=module_path,
        handler=handler_fn,
        event_filters=[],
        extras_configs=extras or {},
    )


def _make_star_metadata(
    name: str = "test-plugin",
    module_path: str = "test_module",
    activated: bool = True,
    reserved: bool = False,
) -> StarMetadata:
    return StarMetadata(
        name=name,
        module_path=module_path,
        activated=activated,
        reserved=reserved,
    )


class TestCallRawPlatformEventHook:
    """Tests for call_raw_platform_event_hook in context_utils."""

    @pytest.mark.asyncio
    async def test_basic_handler_called(self):
        """Scene 1: Handler is called with correct event."""
        handler_fn = AsyncMock()
        handler = _make_handler(handler_fn)
        star_meta = _make_star_metadata()

        mock_registry = MagicMock()
        mock_registry.get_handlers_by_event_type.return_value = [handler]

        event = RawPlatformEvent(
            payload={"op": 0, "t": "MESSAGE_CREATE", "d": {"content": "hello"}},
            platform_meta=_make_platform_meta(),
            meta={"event_type": "MESSAGE_CREATE"},
        )

        with (
            patch(
                "astrbot.core.pipeline.context_utils.star_handlers_registry",
                mock_registry,
            ),
            patch(
                "astrbot.core.pipeline.context_utils.star_map",
                {"test_module": star_meta},
            ),
        ):
            from astrbot.core.pipeline.context_utils import (
                call_raw_platform_event_hook,
            )

            result = await call_raw_platform_event_hook(event)

        handler_fn.assert_called_once_with(event)
        assert result is False

    @pytest.mark.asyncio
    async def test_stop_event_blocks_subsequent_handlers(self):
        """Scene 2: stop_event() prevents lower-priority handlers from running."""

        async def stopping_handler(event):
            event.stop_event()

        high_priority_fn = AsyncMock(side_effect=stopping_handler)
        low_priority_fn = AsyncMock()

        handler_high = _make_handler(high_priority_fn, module_path="mod_a")
        handler_low = _make_handler(low_priority_fn, module_path="mod_b")
        star_a = _make_star_metadata(name="plugin-a", module_path="mod_a")
        star_b = _make_star_metadata(name="plugin-b", module_path="mod_b")

        mock_registry = MagicMock()
        mock_registry.get_handlers_by_event_type.return_value = [
            handler_high,
            handler_low,
        ]

        event = RawPlatformEvent(
            payload={"op": 0},
            platform_meta=_make_platform_meta(),
        )

        with (
            patch(
                "astrbot.core.pipeline.context_utils.star_handlers_registry",
                mock_registry,
            ),
            patch(
                "astrbot.core.pipeline.context_utils.star_map",
                {"mod_a": star_a, "mod_b": star_b},
            ),
        ):
            from astrbot.core.pipeline.context_utils import (
                call_raw_platform_event_hook,
            )

            result = await call_raw_platform_event_hook(event)

        high_priority_fn.assert_called_once()
        low_priority_fn.assert_not_called()
        assert result is True

    @pytest.mark.asyncio
    async def test_platform_name_filter(self):
        """Scene 3: Handler with raw_platform_name filters non-matching events."""
        handler_fn = AsyncMock()
        handler = _make_handler(
            handler_fn, extras={"raw_platform_name": "qq_official_webhook"}
        )
        star_meta = _make_star_metadata()

        mock_registry = MagicMock()
        mock_registry.get_handlers_by_event_type.return_value = [handler]

        event = RawPlatformEvent(
            payload={},
            platform_meta=_make_platform_meta(name="telegram"),
        )

        with (
            patch(
                "astrbot.core.pipeline.context_utils.star_handlers_registry",
                mock_registry,
            ),
            patch(
                "astrbot.core.pipeline.context_utils.star_map",
                {"test_module": star_meta},
            ),
        ):
            from astrbot.core.pipeline.context_utils import (
                call_raw_platform_event_hook,
            )

            result = await call_raw_platform_event_hook(event)

        handler_fn.assert_not_called()
        assert result is False

    @pytest.mark.asyncio
    async def test_platform_id_filter(self):
        """Scene 4: Handler with raw_platform_id filters non-matching events."""
        handler_fn = AsyncMock()
        handler = _make_handler(handler_fn, extras={"raw_platform_id": "qq1"})
        star_meta = _make_star_metadata()

        mock_registry = MagicMock()
        mock_registry.get_handlers_by_event_type.return_value = [handler]

        event = RawPlatformEvent(
            payload={},
            platform_meta=_make_platform_meta(platform_id="qq2"),
        )

        with (
            patch(
                "astrbot.core.pipeline.context_utils.star_handlers_registry",
                mock_registry,
            ),
            patch(
                "astrbot.core.pipeline.context_utils.star_map",
                {"test_module": star_meta},
            ),
        ):
            from astrbot.core.pipeline.context_utils import (
                call_raw_platform_event_hook,
            )

            result = await call_raw_platform_event_hook(event)

        handler_fn.assert_not_called()
        assert result is False

    @pytest.mark.asyncio
    async def test_event_type_filter(self):
        """Scene 5: Handler with raw_event_type filters non-matching events."""
        handler_fn = AsyncMock()
        handler = _make_handler(
            handler_fn, extras={"raw_event_type": "GROUP_AT_MESSAGE_CREATE"}
        )
        star_meta = _make_star_metadata()

        mock_registry = MagicMock()
        mock_registry.get_handlers_by_event_type.return_value = [handler]

        event = RawPlatformEvent(
            payload={},
            platform_meta=_make_platform_meta(),
            meta={"event_type": "INTERACTION_CREATE"},
        )

        with (
            patch(
                "astrbot.core.pipeline.context_utils.star_handlers_registry",
                mock_registry,
            ),
            patch(
                "astrbot.core.pipeline.context_utils.star_map",
                {"test_module": star_meta},
            ),
        ):
            from astrbot.core.pipeline.context_utils import (
                call_raw_platform_event_hook,
            )

            result = await call_raw_platform_event_hook(event)

        handler_fn.assert_not_called()
        assert result is False


class TestEmitRawPlatformEventPluginSet:
    """Tests for Platform.emit_raw_platform_event plugin_set filtering."""

    def _make_platform(self, astrbot_config: dict | None = None):
        """Create a concrete Platform subclass for testing."""
        from astrbot.core.platform.platform import Platform

        class TestPlatform(Platform):
            async def run(self):
                pass

            def meta(self):
                return _make_platform_meta()

        inst = TestPlatform.__new__(TestPlatform)
        inst.config = {}
        inst._event_queue = asyncio.Queue()
        inst.client_self_id = "test"
        inst._status = PlatformStatus.PENDING
        inst._errors = []
        inst._started_at = None
        inst._astrbot_config = astrbot_config
        return inst

    @pytest.mark.asyncio
    async def test_plugin_set_whitelist_passes(self):
        """Scene 6: Plugin in whitelist — handler called."""
        platform = self._make_platform({"plugin_set": ["test-plugin"]})

        with patch(
            "astrbot.core.pipeline.context_utils.call_raw_platform_event_hook",
            new_callable=AsyncMock,
            return_value=False,
        ) as mock_hook:
            await platform.emit_raw_platform_event({"data": 1})

            event = mock_hook.call_args[0][0]
            assert event.plugins_name == ["test-plugin"]

    @pytest.mark.asyncio
    async def test_plugin_set_whitelist_blocks(self):
        """Scene 7: Plugin not in whitelist — plugins_name set to filter."""
        platform = self._make_platform({"plugin_set": ["other-plugin"]})

        with patch(
            "astrbot.core.pipeline.context_utils.call_raw_platform_event_hook",
            new_callable=AsyncMock,
            return_value=False,
        ) as mock_hook:
            await platform.emit_raw_platform_event({"data": 1})

            event = mock_hook.call_args[0][0]
            assert event.plugins_name == ["other-plugin"]

    @pytest.mark.asyncio
    async def test_plugin_set_wildcard_no_filter(self):
        """Scene 8: plugin_set=["*"] — plugins_name is None (no filtering)."""
        platform = self._make_platform({"plugin_set": ["*"]})

        with patch(
            "astrbot.core.pipeline.context_utils.call_raw_platform_event_hook",
            new_callable=AsyncMock,
            return_value=False,
        ) as mock_hook:
            await platform.emit_raw_platform_event({"data": 1})

            event = mock_hook.call_args[0][0]
            assert event.plugins_name is None

    @pytest.mark.asyncio
    async def test_no_astrbot_config_no_filter(self):
        """Scene 9: _astrbot_config=None — plugins_name is None (no filtering)."""
        platform = self._make_platform(None)

        with patch(
            "astrbot.core.pipeline.context_utils.call_raw_platform_event_hook",
            new_callable=AsyncMock,
            return_value=False,
        ) as mock_hook:
            await platform.emit_raw_platform_event({"data": 1})

            event = mock_hook.call_args[0][0]
            assert event.plugins_name is None

    @pytest.mark.asyncio
    async def test_explicit_plugins_name_overrides_config(self):
        """Scene 10: Explicit plugins_name takes precedence over config."""
        platform = self._make_platform({"plugin_set": ["*"]})

        with patch(
            "astrbot.core.pipeline.context_utils.call_raw_platform_event_hook",
            new_callable=AsyncMock,
            return_value=False,
        ) as mock_hook:
            await platform.emit_raw_platform_event(
                {"data": 1}, plugins_name=["specific"]
            )

            event = mock_hook.call_args[0][0]
            assert event.plugins_name == ["specific"]
