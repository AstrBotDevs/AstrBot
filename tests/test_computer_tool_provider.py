"""Import smoke tests for ComputerToolProvider."""

import pytest


class TestComputerToolProviderImports:
    """Verify the computer_tool_provider module can be imported and key classes exist."""

    def test_module_import(self):
        """Import the module without error."""
        from astrbot.core.computer import computer_tool_provider
        assert computer_tool_provider is not None

    def test_computer_tool_provider_class(self):
        """ComputerToolProvider class is present and callable."""
        from astrbot.core.computer.computer_tool_provider import ComputerToolProvider
        assert ComputerToolProvider is not None
        # Static method exists
        assert hasattr(ComputerToolProvider, "get_all_tools")
        assert callable(ComputerToolProvider.get_all_tools)

    def test_module_level_get_all_tools(self):
        """Module-level get_all_tools function exists."""
        from astrbot.core.computer.computer_tool_provider import get_all_tools
        assert callable(get_all_tools)
