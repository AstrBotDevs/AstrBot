from astrbot.core.star.error_messages import (
    PLUGIN_ERROR_TEMPLATES,
    format_plugin_error,
)


class TestPluginErrorMessages:
    def test_templates_exist(self):
        assert "not_found_in_failed_list" in PLUGIN_ERROR_TEMPLATES
        assert "reserved_plugin_cannot_uninstall" in PLUGIN_ERROR_TEMPLATES
        assert "failed_plugin_dir_remove_error" in PLUGIN_ERROR_TEMPLATES

    def test_format_plugin_error_with_valid_key(self):
        result = format_plugin_error("not_found_in_failed_list")
        assert result == "插件不存在于失败列表中｡"

    def test_format_plugin_error_with_kwargs(self):
        result = format_plugin_error(
            "failed_plugin_dir_remove_error", error="Permission denied"
        )
        assert "Permission denied" in result

    def test_format_plugin_error_unknown_key_returns_key(self):
        result = format_plugin_error("unknown_key")
        assert result == "unknown_key"

    def test_format_plugin_error_invalid_format_ignores(self):
        result = format_plugin_error("not_found_in_failed_list", extra_arg="value")
        assert result == "插件不存在于失败列表中｡"

    def test_format_plugin_error_with_empty_kwargs(self):
        result = format_plugin_error("not_found_in_failed_list", **{})
        assert result == "插件不存在于失败列表中｡"
