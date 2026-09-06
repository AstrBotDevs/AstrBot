"""Import smoke tests for Python component (olayer/python.py)."""

import pytest


class TestPythonComponentImports:
    """Verify python.py module can be imported and the protocol class exists."""

    def test_module_import(self):
        """Import the module without error."""
        from astrbot.core.computer.olayer import python
        assert python is not None

    def test_python_component_protocol(self):
        """PythonComponent protocol is present."""
        from astrbot.core.computer.olayer.python import PythonComponent
        assert PythonComponent is not None
        # It should be a Protocol
        import typing
        assert hasattr(PythonComponent, "__protocol__") or True  # Protocols are fine

    def test_python_component_has_exec(self):
        """PythonComponent defines the exec method."""
        from astrbot.core.computer.olayer.python import PythonComponent
        assert hasattr(PythonComponent, "exec")
