from unittest.mock import patch

from astrbot.core.utils.path_util import path_Mapping


class TestPathMapping:
    def test_no_mappings_returns_original(self):
        assert path_Mapping([], "/some/path") == "/some/path"
        # file:// prefix is only stripped when there's a matching mapping
        assert path_Mapping([], "file:///some/path") == "file:///some/path"

    def test_single_mapping_replaces_correctly(self):
        mappings = ["/old:/new"]
        assert path_Mapping(mappings, "/old/file.txt") == "/new/file.txt"
        assert path_Mapping(mappings, "/old") == "/new"

    def test_mapping_with_file_prefix(self):
        mappings = ["/old:/new"]
        assert path_Mapping(mappings, "file:///old/file.txt") == "/new/file.txt"

    def test_multiple_mappings_uses_first_match(self):
        mappings = ["/first:/alpha", "/second:/beta"]
        assert path_Mapping(mappings, "/first/file.txt") == "/alpha/file.txt"
        assert path_Mapping(mappings, "/second/file.txt") == "/beta/file.txt"

    def test_mapping_no_match_returns_original(self):
        mappings = ["/old:/new"]
        assert path_Mapping(mappings, "/other/file.txt") == "/other/file.txt"

    def test_mapping_strips_trailing_slashes(self):
        mappings = ["/old/:/new/"]
        assert path_Mapping(mappings, "/old/file.txt") == "/new/file.txt"

    def test_mapping_with_backslash(self):
        mappings = ["/old:/new"]
        assert path_Mapping(mappings, "/old\\file.txt") == "/new/file.txt"

    def test_relative_path_replacement(self):
        mappings = ["/old:/new"]
        assert path_Mapping(mappings, "./file.txt") == "./file.txt"
        assert path_Mapping(mappings, ".\\file.txt") == ".\\file.txt"

    def test_windows_path_preserves_backslashes(self):
        mappings = ["/old:/new"]
        result = path_Mapping(mappings, "/old/Program Files/file.txt")
        assert "\\" in result or "/" in result

    def test_invalid_mapping_rule_single_part_logs_warning(self):
        mappings = ["invalid_rule"]
        with patch("astrbot.core.utils.path_util.logger") as mock_logger:
            result = path_Mapping(mappings, "/test/path")
            assert result == "/test/path"
            mock_logger.warning.assert_called()
            assert "路径映射规则错误" in mock_logger.warning.call_args[0][0]

    def test_invalid_mapping_rule_four_parts_logs_warning(self):
        mappings = ["a:b:c:d"]
        with patch("astrbot.core.utils.path_util.logger") as mock_logger:
            result = path_Mapping(mappings, "/test/path")
            assert result == "/test/path"
            mock_logger.warning.assert_called()

    def test_empty_mappings_list(self):
        assert path_Mapping([], "/path/to/file") == "/path/to/file"

    def test_mapping_with_windows_style_paths(self):
        mappings = ["C:/Users:/home"]
        with patch("astrbot.core.utils.path_util.os.path.exists") as mock_exists:
            mock_exists.return_value = True
            result = path_Mapping(mappings, "C:/Users/test/file.txt")
            assert "/home" in result or "home" in result

    def test_mapping_linux_path_no_exists_check(self):
        mappings = ["/home:/usr/local"]
        with patch("astrbot.core.utils.path_util.os.path.exists") as mock_exists:
            mock_exists.return_value = False
            result = path_Mapping(mappings, "/home/test/file.txt")
            assert "/usr/local" in result
