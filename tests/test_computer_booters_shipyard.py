"""Shipyard runtime extraction smoke tests."""

import importlib.util


class TestShipyardBooterExtraction:
    """Concrete Shipyard runtimes are provided by plugins, not core."""

    def test_core_shipyard_modules_are_absent(self):
        assert (
            importlib.util.find_spec("astrbot.core.computer.booters.shipyard") is None
        )
        assert (
            importlib.util.find_spec("astrbot.core.computer.booters.shipyard_neo")
            is None
        )
        assert importlib.util.find_spec("astrbot.core.computer.booters.boxlite") is None

    def test_core_shipyard_tool_modules_are_absent(self):
        assert (
            importlib.util.find_spec("astrbot.core.tools.computer_tools.shipyard_neo")
            is None
        )
