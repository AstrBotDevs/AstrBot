"""Shared plugin error message templates for star manager flows."""

PLUGIN_ERROR_TEMPLATES = {
    "not_found_in_failed_list": "插件不存在于失败列表中。",
    "reserved_plugin_cannot_uninstall": "该插件是 AstrBot 保留插件，无法卸载。",
    "failed_plugin_dir_remove_error": (
        "移除失败插件成功，但是删除插件文件夹失败: {error}。"
        "您可以手动删除该文件夹，位于 addons/plugins/ 下。"
    ),
}


def format_plugin_error(key: str, **kwargs) -> str:
    template = PLUGIN_ERROR_TEMPLATES.get(key, key)
    try:
        return template.format(**kwargs)
    except Exception:
        return template
