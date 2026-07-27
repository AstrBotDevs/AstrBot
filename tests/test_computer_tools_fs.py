"""Import smoke tests for computer filesystem tools (fs.py)."""

import pytest


class TestFsToolsImports:
    """Verify fs.py module can be imported and key classes exist."""

    def test_module_import(self):
        """Import the module without error."""
        from astrbot.core.tools.computer_tools import fs
        assert fs is not None

    def test_file_upload_tool_class(self):
        """FileUploadTool is present."""
        from astrbot.core.computer.tools.fs import FileUploadTool
        assert FileUploadTool is not None
        assert FileUploadTool.name == "astrbot_upload_file"

    def test_file_download_tool_class(self):
        """FileDownloadTool is present."""
        from astrbot.core.computer.tools.fs import FileDownloadTool
        assert FileDownloadTool is not None
        assert FileDownloadTool.name == "astrbot_download_file"
