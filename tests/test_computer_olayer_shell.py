"""Import smoke tests for Shell component (olayer/shell.py)."""

import pytest


class TestShellComponentImports:
    """Verify shell.py module can be imported and the protocol class exists."""

    def test_module_import(self):
        """Import the module without error."""
        from astrbot.core.computer.olayer import shell
        assert shell is not None

    def test_shell_component_protocol(self):
        """ShellComponent protocol is present."""
        from astrbot.core.computer.olayer.shell import ShellComponent
        assert ShellComponent is not None

    def test_shell_component_has_exec(self):
        """ShellComponent defines the exec method."""
        from astrbot.core.computer.olayer.shell import ShellComponent
        assert hasattr(ShellComponent, "exec")
