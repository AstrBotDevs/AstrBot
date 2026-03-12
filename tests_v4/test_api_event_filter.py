"""
Tests for api/event/filter.py - Event filter decorators and utilities.
"""

from __future__ import annotations


from astrbot_sdk.api.event.filter import ADMIN, command, filter, permission, regex
from astrbot_sdk.decorators import get_handler_meta
from astrbot_sdk.protocol.descriptors import CommandTrigger, MessageTrigger


class TestCommandFilter:
    """Tests for command() filter function."""

    def test_command_creates_command_trigger(self):
        """command() should create a CommandTrigger."""

        @command("hello")
        async def hello_handler():
            pass

        meta = get_handler_meta(hello_handler)
        assert meta is not None
        assert isinstance(meta.trigger, CommandTrigger)
        assert meta.trigger.command == "hello"

    def test_command_is_decorator(self):
        """command() should be usable as a decorator."""

        @command("test")
        async def test_handler():
            pass

        assert hasattr(test_handler, "__astrbot_handler_meta__")


class TestRegexFilter:
    """Tests for regex() filter function."""

    def test_regex_creates_message_trigger_with_regex(self):
        """regex() should create a MessageTrigger with regex pattern."""

        @regex(r"\d+")
        async def number_handler():
            pass

        meta = get_handler_meta(number_handler)
        assert meta is not None
        assert isinstance(meta.trigger, MessageTrigger)
        assert meta.trigger.regex == r"\d+"

    def test_regex_pattern_is_stored(self):
        """regex() should store the pattern correctly."""

        @regex(r"hello\s+world")
        async def greeting_handler():
            pass

        meta = get_handler_meta(greeting_handler)
        assert meta.trigger.regex == r"hello\s+world"


class TestPermissionFilter:
    """Tests for permission() filter function."""

    def test_permission_admin_sets_require_admin(self):
        """permission(ADMIN) should set require_admin permission."""

        @permission(ADMIN)
        async def admin_handler():
            pass

        meta = get_handler_meta(admin_handler)
        assert meta is not None
        assert meta.permissions.require_admin is True

    def test_permission_non_admin_passes_through(self):
        """permission() with non-ADMIN level should pass through."""

        @permission("user")
        async def user_handler():
            pass

        # Should not set admin permission
        meta = get_handler_meta(user_handler)
        assert meta is None or not meta.permissions.require_admin

    def test_permission_can_be_combined_with_command(self):
        """permission() can be combined with other decorators."""

        @command("admin")
        @permission(ADMIN)
        async def admin_command():
            pass

        meta = get_handler_meta(admin_command)
        assert isinstance(meta.trigger, CommandTrigger)
        assert meta.trigger.command == "admin"
        assert meta.permissions.require_admin is True


class TestFilterNamespace:
    """Tests for filter namespace object."""

    def test_filter_namespace_has_command(self):
        """filter namespace should have command method."""
        assert hasattr(filter, "command")
        assert callable(filter.command)

    def test_filter_namespace_has_regex(self):
        """filter namespace should have regex method."""
        assert hasattr(filter, "regex")
        assert callable(filter.regex)

    def test_filter_namespace_has_permission(self):
        """filter namespace should have permission method."""
        assert hasattr(filter, "permission")
        assert callable(filter.permission)

    def test_filter_command_works_as_decorator(self):
        """filter.command() should work as a decorator."""

        @filter.command("ping")
        async def ping_handler():
            pass

        meta = get_handler_meta(ping_handler)
        assert meta.trigger.command == "ping"

    def test_filter_regex_works_as_decorator(self):
        """filter.regex() should work as a decorator."""

        @filter.regex(r"test")
        async def test_handler():
            pass

        meta = get_handler_meta(test_handler)
        assert meta.trigger.regex == r"test"

    def test_filter_permission_admin_works(self):
        """filter.permission(ADMIN) should set admin permission."""

        @filter.permission(ADMIN)
        async def admin_handler():
            pass

        meta = get_handler_meta(admin_handler)
        assert meta.permissions.require_admin is True


class TestAdminConstant:
    """Tests for ADMIN constant."""

    def test_admin_constant_value(self):
        """ADMIN constant should be 'admin'."""
        assert ADMIN == "admin"


class TestModuleExports:
    """Tests for module exports."""

    def test_all_exports(self):
        """Module should export expected names."""
        from astrbot_sdk.api.event.filter import __all__

        assert "ADMIN" in __all__
        assert "command" in __all__
        assert "regex" in __all__
        assert "permission" in __all__
        assert "filter" in __all__
