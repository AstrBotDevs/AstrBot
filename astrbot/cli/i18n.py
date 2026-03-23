"""Internationalization support for AstrBot CLI.

This module provides i18n support with Chinese and English languages.
Language is auto-detected from environment or can be set manually.
"""

from __future__ import annotations

import os
from enum import Enum
from functools import lru_cache


class Language(Enum):
    """Supported languages."""

    ZH = "zh"
    EN = "en"


# Translation dictionaries
_TRANSLATIONS: dict[Language, dict[str, str]] = {
    Language.ZH: {
        # CLI welcome and general
        "cli_welcome": "欢迎使用 AstrBot CLI!",
        "cli_version": "AstrBot CLI 版本: {version}",
        "cli_unknown_command": "未知命令: {command}",
        "cli_help_available": "使用 astrbot help --all 查看所有命令",

        # Dashboard commands
        "dashboard_bundled": "Dashboard 已打包在安装包中 - 跳过下载",
        "dashboard_not_installed": "Dashboard 未安装",
        "dashboard_install_confirm": "是否安装 Dashboard?",
        "dashboard_installing": "正在安装 Dashboard...",
        "dashboard_install_success": "Dashboard 安装成功",
        "dashboard_install_failed": "Dashboard 安装失败: {error}",
        "dashboard_not_needed": "Dashboard 不需要安装",
        "dashboard_declined": "Dashboard 安装已取消",
        "dashboard_already_up_to_date": "Dashboard 已是最新版本",
        "dashboard_version": "Dashboard 版本: {version}",
        "dashboard_download_failed": "Dashboard 下载失败: {error}",
        "dashboard_init_dir": "正在初始化 Dashboard 目录...",
        "dashboard_init_success": "Dashboard 初始化成功",

        # Plugin commands
        "plugin_installing": "正在安装插件: {name}",
        "plugin_install_success": "插件安装成功: {name}",
        "plugin_install_failed": "插件安装失败: {name}",
        "plugin_uninstall_confirm": "确定要卸载插件 {name} 吗?",
        "plugin_uninstall_success": "插件卸载成功: {name}",
        "plugin_uninstall_failed": "插件卸载失败: {name}",
        "plugin_list_empty": "未安装任何插件",
        "plugin_already_installed": "插件已安装: {name}",
        "plugin_not_found": "插件未找到: {name}",
        "plugin_already_exists": "插件已存在: {name}",
        "plugin_not_found_or_installed": "插件未找到或已安装: {name}",
        "plugin_uninstall_failed_ex": "插件卸载失败 {name}: {error}",
        "plugin_no_update_needed": "没有需要更新的插件",
        "plugin_found_update": "发现 {count} 个插件需要更新",
        "plugin_updating": "正在更新插件 {name}...",
        "plugin_search_no_result": "未找到匹配 '{query}' 的插件",
        "plugin_search_results": "搜索结果: '{query}'",

        # Config commands
        "config_show": "显示配置",
        "config_set_success": "配置项已更新: {key} = {value}",
        "config_set_failed": "配置项更新失败: {key}",
        "config_set_failed_ex": "设置配置失败: {error}",
        "config_get_success": "{key} = {value}",
        "config_get_not_found": "配置项未找到: {key}",
        "config_reset_confirm": "确定要重置所有配置吗?",
        "config_reset_success": "配置已重置",

        # Config validators
        "config_log_level_invalid": "日志级别必须是 DEBUG/INFO/WARNING/ERROR/CRITICAL 之一",
        "config_port_must_be_number": "端口必须是数字",
        "config_port_range_invalid": "端口必须在 1-65535 范围内",
        "config_username_empty": "用户名不能为空",
        "config_password_empty": "密码不能为空",
        "config_timezone_invalid": "无效的时区: {value}。请使用有效的 IANA 时区名称",
        "config_callback_invalid": "回调 API 基础路径必须以 http:// 或 https:// 开头",
        "config_key_unsupported": "不支持的配置项: {key}",
        "config_key_unknown": "未知的配置项: {key}",
        "config_updated": "配置已更新: {key}",

        # Init command
        "init_creating": "正在创建配置目录...",
        "init_created": "配置目录已创建: {path}",
        "init_copying": "正在复制配置文件...",
        "init_copied": "配置文件已复制",
        "init_success": "AstrBot 初始化完成!",
        "init_failed": "初始化失败: {error}",

        # Run command
        "run_starting": "正在启动 AstrBot...",
        "run_started": "AstrBot 已启动!",
        "run_backend_only": "以无界面模式启动",
        "run_failed": "启动失败: {error}",
        "run_stopped": "AstrBot 已停止",

        # TUI command
        "tui_starting": "正在启动 TUI...",
        "tui_started": "TUI 已启动",
        "tui_failed": "TUI 启动失败: {error}",

        # Common
        "yes": "是",
        "no": "否",
        "cancel": "取消",
        "confirm": "确认",
        "error": "错误",
        "success": "成功",
        "warning": "警告",
        "info": "信息",
        "loading": "加载中...",
        "done": "完成",
        "failed": "失败",
        "retry": "重试",
        "exit": "退出",
        "continue": "继续",
    },
    Language.EN: {
        # CLI welcome and general
        "cli_welcome": "Welcome to AstrBot CLI!",
        "cli_version": "AstrBot CLI version: {version}",
        "cli_unknown_command": "Unknown command: {command}",
        "cli_help_available": "Use astrbot help --all to see all commands",

        # Dashboard commands
        "dashboard_bundled": "Dashboard is bundled with the package - skipping download",
        "dashboard_not_installed": "Dashboard is not installed",
        "dashboard_install_confirm": "Install Dashboard?",
        "dashboard_installing": "Installing Dashboard...",
        "dashboard_install_success": "Dashboard installed successfully",
        "dashboard_install_failed": "Failed to install dashboard: {error}",
        "dashboard_not_needed": "Dashboard not needed",
        "dashboard_declined": "Dashboard installation declined.",
        "dashboard_already_up_to_date": "Dashboard is already up to date",
        "dashboard_version": "Dashboard version: {version}",
        "dashboard_download_failed": "Failed to download dashboard: {error}",
        "dashboard_init_dir": "Initializing dashboard directory...",
        "dashboard_init_success": "Dashboard initialized successfully",

        # Plugin commands
        "plugin_installing": "Installing plugin: {name}",
        "plugin_install_success": "Plugin installed successfully: {name}",
        "plugin_install_failed": "Failed to install plugin: {name}",
        "plugin_uninstall_confirm": "Uninstall plugin {name}?",
        "plugin_uninstall_success": "Plugin uninstalled successfully: {name}",
        "plugin_uninstall_failed": "Failed to uninstall plugin: {name}",
        "plugin_list_empty": "No plugins installed",
        "plugin_already_installed": "Plugin already installed: {name}",
        "plugin_not_found": "Plugin not found: {name}",
        "plugin_already_exists": "Plugin {name} already exists",
        "plugin_not_found_or_installed": "Plugin {name} not found or already installed",
        "plugin_uninstall_failed_ex": "Failed to uninstall plugin {name}: {error}",
        "plugin_no_update_needed": "No plugins need updating",
        "plugin_found_update": "Found {count} plugin(s) needing update",
        "plugin_updating": "Updating plugin {name}...",
        "plugin_search_no_result": "No plugins matching '{query}' found",
        "plugin_search_results": "Search results: '{query}'",

        # Config commands
        "config_show": "Show configuration",
        "config_set_success": "Configuration updated: {key} = {value}",
        "config_set_failed": "Failed to update configuration: {key}",
        "config_set_failed_ex": "Failed to set config: {error}",
        "config_get_success": "{key} = {value}",
        "config_get_not_found": "Configuration key not found: {key}",
        "config_reset_confirm": "Reset all configuration?",
        "config_reset_success": "Configuration reset",

        # Config validators
        "config_log_level_invalid": "Log level must be one of DEBUG/INFO/WARNING/ERROR/CRITICAL",
        "config_port_must_be_number": "Port must be a number",
        "config_port_range_invalid": "Port must be in range 1-65535",
        "config_username_empty": "Username cannot be empty",
        "config_password_empty": "Password cannot be empty",
        "config_timezone_invalid": "Invalid timezone: {value}. Please use a valid IANA timezone name",
        "config_callback_invalid": "Callback API base must start with http:// or https://",
        "config_key_unsupported": "Unsupported config key: {key}",
        "config_key_unknown": "Unknown config key: {key}",
        "config_updated": "Config updated: {key}",

        # Init command
        "init_creating": "Creating config directory...",
        "init_created": "Config directory created: {path}",
        "init_copying": "Copying config files...",
        "init_copied": "Config files copied",
        "init_success": "AstrBot initialized successfully!",
        "init_failed": "Initialization failed: {error}",

        # Run command
        "run_starting": "Starting AstrBot...",
        "run_started": "AstrBot started!",
        "run_backend_only": "Starting in backend-only mode",
        "run_failed": "Failed to start: {error}",
        "run_stopped": "AstrBot stopped",

        # TUI command
        "tui_starting": "Starting TUI...",
        "tui_started": "TUI started",
        "tui_failed": "Failed to start TUI: {error}",

        # Common
        "yes": "Yes",
        "no": "No",
        "cancel": "Cancel",
        "confirm": "Confirm",
        "error": "Error",
        "success": "Success",
        "warning": "Warning",
        "info": "Info",
        "loading": "Loading...",
        "done": "Done",
        "failed": "Failed",
        "retry": "Retry",
        "exit": "Exit",
        "continue": "Continue",
    },
}


@lru_cache(maxsize=1)
def get_current_language() -> Language:
    """Get the current language based on environment or default.

    Detection order:
    1. ASTRBOT_CLI_LANG environment variable (zh/en)
    2. LANG environment variable (if contains zh/cn)
    3. LC_ALL environment variable (if contains zh/cn)
    4. Default to Chinese (most users are Chinese)
    """
    # Check explicit override first
    explicit = os.environ.get("ASTRBOT_CLI_LANG", "").lower()
    if explicit in ("zh", "en"):
        return Language.ZH if explicit == "zh" else Language.EN

    # Check LANG/LC_ALL for Chinese
    for env_var in ("LANG", "LC_ALL"):
        lang = os.environ.get(env_var, "").lower()
        if "zh" in lang or "cn" in lang:
            return Language.ZH

    # Default to Chinese for broader appeal
    return Language.ZH


def set_language(lang: Language) -> None:
    """Set the current language (clears all translation caches)."""
    get_current_language.cache_clear()
    _t_cached.cache_clear()
    # Set environment variable for persistence
    os.environ["ASTRBOT_CLI_LANG"] = lang.value


@lru_cache(maxsize=128)
def _t_cached(key: str, lang: Language) -> str:
    """Cached translation lookup."""
    return _TRANSLATIONS.get(lang, {}).get(key, key)


def t(translation_key: str, **kwargs: str) -> str:
    """Get translation for the given key in the current language.

    Args:
        translation_key: Translation key (e.g., "cli_welcome", "plugin_installing")
        **kwargs: Format arguments for the translation string

    Returns:
        Translated string, or the key itself if not found
    """
    result = _t_cached(translation_key, get_current_language())
    if kwargs:
        result = result.format(**kwargs)
    return result


def tr(key: str, **kwargs: str) -> str:
    """Get translation (alias for t())."""
    return t(key, **kwargs)


class CLITranslations:
    """Translation accessor class for CLI contexts.

    Usage:
        translations = CLITranslations()
        print(translations.cli_welcome)
        print(translations.plugin_installing(name="my_plugin"))
    """

    def __getattr__(self, key: str) -> str:
        return t(key)

    def __call__(self, key: str, **kwargs: str) -> str:
        return t(key, **kwargs)


# Convenience instance
translations = CLITranslations()
