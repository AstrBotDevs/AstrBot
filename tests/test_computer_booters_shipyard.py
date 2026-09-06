"""Import smoke tests for Shipyard booter."""

import pytest


class TestShipyardBooterImports:
    """Verify shipyard.py module can be imported and key classes exist."""

    def test_module_import(self):
        """Import the module without error."""
        from astrbot.core.computer.booters import shipyard
        assert shipyard is not None

    def test_shipyard_booter_class(self):
        """ShipyardBooter is present and subclasses ComputerBooter."""
        from astrbot.core.computer.booters.base import ComputerBooter
        from astrbot.core.computer.booters.shipyard import ShipyardBooter
        assert ShipyardBooter is not None
        assert issubclass(ShipyardBooter, ComputerBooter)

    def test_shipyard_shell_wrapper(self):
        """ShipyardShellWrapper is present."""
        from astrbot.core.computer.booters.shipyard import ShipyardShellWrapper
        assert ShipyardShellWrapper is not None

    def test_shipyard_filesystem_wrapper(self):
        """ShipyardFileSystemWrapper is present."""
        from astrbot.core.computer.booters.shipyard import ShipyardFileSystemWrapper
        assert ShipyardFileSystemWrapper is not None

    def test_default_tools_method(self):
        """ShipyardBooter.get_default_tools exists and returns a list."""
        from astrbot.core.computer.booters.shipyard import ShipyardBooter
        assert hasattr(ShipyardBooter, "get_default_tools")
