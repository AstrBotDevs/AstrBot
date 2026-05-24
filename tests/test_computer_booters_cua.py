"""CUA runtime extraction smoke tests."""

import importlib.util


class TestCuaBooterExtraction:
    """Concrete CUA runtime modules are provided by plugins, not core."""

    def test_core_cua_booter_module_is_absent(self):
        assert importlib.util.find_spec("astrbot.core.computer.booters.cua") is None

    def test_core_cua_tool_modules_are_absent(self):
        assert importlib.util.find_spec("astrbot.core.tools.computer_tools.cua") is None
        assert (
            importlib.util.find_spec("astrbot.core.tools.computer_tools.cua_sandbox")
            is None
        )
