"""Import smoke tests for Local booter."""

import pytest


class TestLocalBooterImports:
    """Verify local.py module can be imported and key classes exist."""

    def test_module_import(self):
        """Import the module without error."""
        from astrbot.core.computer.booters import local
        assert local is not None

    def test_local_booter_class(self):
        """LocalBooter is present and subclasses ComputerBooter."""
        from astrbot.core.computer.booters.base import ComputerBooter
        from astrbot.core.computer.booters.local import LocalBooter
        assert LocalBooter is not None
        assert issubclass(LocalBooter, ComputerBooter)

    def test_local_shell_component(self):
        """LocalShellComponent is present."""
        from astrbot.core.computer.booters.local import LocalShellComponent
        assert LocalShellComponent is not None

    def test_local_python_component(self):
        """LocalPythonComponent is present."""
        from astrbot.core.computer.booters.local import LocalPythonComponent
        assert LocalPythonComponent is not None

    def test_local_filesystem_component(self):
        """LocalFileSystemComponent is present."""
        from astrbot.core.computer.booters.local import LocalFileSystemComponent
        assert LocalFileSystemComponent is not None

    def test_utility_functions(self):
        """Key utility functions are importable."""
        from astrbot.core.computer.booters.local import (
            _is_safe_command,
            _ensure_safe_path,
            _decode_bytes_with_fallback,
        )
        assert callable(_is_safe_command)
        assert callable(_ensure_safe_path)
        assert callable(_decode_bytes_with_fallback)
