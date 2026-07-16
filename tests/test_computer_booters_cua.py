"""Import smoke tests for CUA booter."""

import pytest


class TestCuaBooterImports:
    """Verify cua.py module can be imported and key classes exist."""

    def test_module_import(self):
        """Import the module without error."""
        from astrbot.core.computer.booters import cua
        assert cua is not None

    def test_cua_booter_class(self):
        """CuaBooter is present and subclasses ComputerBooter."""
        from astrbot.core.computer.booters.cua import CuaBooter
        from astrbot.core.computer.booters.base import ComputerBooter
        assert CuaBooter is not None
        assert issubclass(CuaBooter, ComputerBooter)

    def test_cua_shell_component(self):
        """CuaShellComponent is present."""
        from astrbot.core.computer.booters.cua import CuaShellComponent
        assert CuaShellComponent is not None

    def test_cua_python_component(self):
        """CuaPythonComponent is present."""
        from astrbot.core.computer.booters.cua import CuaPythonComponent
        assert CuaPythonComponent is not None

    def test_cua_filesystem_component(self):
        """CuaFileSystemComponent is present."""
        from astrbot.core.computer.booters.cua import CuaFileSystemComponent
        assert CuaFileSystemComponent is not None

    def test_cua_gui_component(self):
        """CuaGUIComponent is present."""
        from astrbot.core.computer.booters.cua import CuaGUIComponent
        assert CuaGUIComponent is not None

    def helper_functions_exist(self):
        """Key helper functions are importable."""
        from astrbot.core.computer.booters.cua import (
            build_cua_booter_kwargs,
            _normalize_process_result,
            _screenshot_to_bytes,
        )
        assert callable(build_cua_booter_kwargs)
        assert callable(_normalize_process_result)
        assert callable(_screenshot_to_bytes)
