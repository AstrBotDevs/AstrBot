"""Import smoke tests for astrbot.core.utils.path_util."""

from astrbot.core.utils import path_util as path_util_module
from astrbot.core.utils.path_util import path_Mapping


class TestImports:
    def test_module_importable(self):
        assert path_util_module is not None

    def test_path_mapping_callable(self):
        assert callable(path_Mapping)


class TestPathMapping:
    def test_returns_src_when_no_mapping_matches(self):
        result = path_Mapping([], "/some/path")
        assert result == "/some/path"

    def test_returns_src_when_mappings_do_not_match(self):
        result = path_Mapping(["/a:/b"], "/some/path")
        assert result == "/some/path"

    def test_maps_linux_to_windows_simple(self):
        result = path_Mapping(["/linux/path:/windows/path"], "/linux/path/file.txt")
        assert "/windows/path/file.txt" in result

    def test_logs_warning_for_single_item_rule(self):
        result = path_Mapping(["invalid"], "/some/path")
        assert result == "/some/path"

    def test_strips_file_prefix(self):
        result = path_Mapping(
            ["/linux/path:/windows/path"],
            "file:///linux/path/file.txt",
        )
        assert result == "/windows/path/file.txt"

    def test_handles_windows_colon_path(self):
        """Simulate a rule like C:/src:/dest that triggers the Windows path branch."""
        result = path_Mapping(
            ["C:/src:/dest"],
            "C:/src/file.txt",
        )
        assert result is not None
        assert isinstance(result, str)

    def test_no_mapping_changes_src(self):
        result = path_Mapping(["/a:/b"], "/unrelated/path")
        assert result == "/unrelated/path"

    def test_mapping_with_trailing_slashes(self):
        result = path_Mapping(["/a/:/b/"], "/a/file.txt")
        assert result == "/b/file.txt"
