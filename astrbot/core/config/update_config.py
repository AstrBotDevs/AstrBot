"""AstrBot 更新配置管理器.

管理独立的更新配置文件 data/update_config.json，支持环境变量覆盖。
优先级: 环境变量 > 配置文件 > 硬编码默认值.

作者: AstrBot Agent
时间: 2026-05-25
"""

import json
import logging
import os
from pathlib import Path
from typing import Any

from astrbot.core.utils.astrbot_path import get_astrbot_data_path

logger = logging.getLogger("astrbot")

UPDATE_CONFIG_PATH = os.path.join(get_astrbot_data_path(), "update_config.json")

# 环境变量名映射
ENV_VAR_MAP = {
    "core_update.release_api_url": "ASTRBOT_CORE_RELEASE_API_URL",
    "core_update.github_archive_url_template": "ASTRBOT_GITHUB_ARCHIVE_URL",
    "dashboard_update.registry_url_template": "ASTRBOT_DASHBOARD_REGISTRY_URL",
    "dashboard_update.github_release_api_url": "ASTRBOT_DASHBOARD_GITHUB_RELEASE_API_URL",
    "dashboard_update.github_release_download_url_template": "ASTRBOT_DASHBOARD_GITHUB_RELEASE_DOWNLOAD_URL",
    "dashboard_update.harbour_url_template": "ASTRBOT_DASHBOARD_HARBOUR_URL",
    "proxy.enabled": "ASTRBOT_UPDATE_PROXY_ENABLED",
    "proxy.url": "ASTRBOT_UPDATE_PROXY_URL",
}

DEFAULT_CONFIG: dict[str, Any] = {
    "update_config_version": 1,
    "core_update": {
        "release_api_url": "https://api.soulter.top/releases",
        "github_archive_url_template": "https://github.com/AstrBotDevs/AstrBot/archive/{version}.zip",
    },
    "dashboard_update": {
        "registry_url_template": "https://astrbot-registry.soulter.top/download/astrbot-dashboard/{version}/dist.zip",
        "github_release_api_url": "https://api.github.com/repos/AstrBotDevs/AstrBot/releases/latest",
        "github_release_download_url_template": "https://github.com/AstrBotDevs/AstrBot/releases/download/{tag}/AstrBot-{tag}-dashboard.zip",
        "harbour_url_template": "https://github.com/AstrBotDevs/astrbot-release-harbour/releases/download/release-{version}/dist.zip",
    },
    "proxy": {
        "enabled": False,
        "url": "",
    },
}


class UpdateConfig(dict):
    """更新配置管理类.

    从独立的 JSON 配置文件加载更新相关配置，支持环境变量覆盖。
    继承自 dict，支持字典式访问。
    """

    config_path: str

    def __init__(self, config_path: str = UPDATE_CONFIG_PATH) -> None:
        super().__init__()
        object.__setattr__(self, "config_path", config_path)

        config = self._load_config()
        self.update(config)

    def _load_config(self) -> dict[str, Any]:
        """加载配置文件，不存在或无效时返回默认值."""
        config_path = Path(self.config_path)

        if not config_path.exists():
            logger.info("更新配置文件不存在，创建默认配置: %s", self.config_path)
            self._save_default_config(config_path)
            return DEFAULT_CONFIG.copy()

        try:
            with open(config_path, encoding="utf-8-sig") as f:
                content = f.read()
                if content.startswith("\ufeff"):
                    content = content[1:]
                user_config = json.loads(content)

            # 合并用户配置和默认配置
            merged = self._merge_config(DEFAULT_CONFIG.copy(), user_config)
            return merged

        except json.JSONDecodeError as e:
            logger.warning(
                "更新配置文件格式错误 (%s)，使用默认配置: %s", e, self.config_path
            )
            return DEFAULT_CONFIG.copy()
        except Exception as e:
            logger.warning(
                "读取更新配置文件失败 (%s)，使用默认配置: %s", e, self.config_path
            )
            return DEFAULT_CONFIG.copy()

    @staticmethod
    def _merge_config(default: dict, user: dict) -> dict:
        """递归合并配置，用户配置覆盖默认值."""
        result = default.copy()
        for key, value in user.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = UpdateConfig._merge_config(result[key], value)
            else:
                result[key] = value
        return result

    def _save_default_config(self, config_path: Path) -> None:
        """保存默认配置到文件."""
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=4, ensure_ascii=False)

    def _get_value(self, path: str, default: Any = None) -> Any:
        """通过路径获取配置值，支持环境变量覆盖.

        Args:
            path: 配置路径，如 "core_update.release_api_url"
            default: 默认值

        Returns:
            配置值，环境变量存在时返回环境变量值
        """
        # 检查环境变量
        env_var = ENV_VAR_MAP.get(path)
        if env_var and env_var in os.environ:
            env_value = os.environ[env_var]
            # 布尔值转换
            if isinstance(default, bool):
                return env_value.lower() in ("true", "1", "yes", "on")
            return env_value

        # 从配置字典获取
        keys = path.split(".")
        value = dict(self)
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value if value is not None else default

    # --- Core Update URLs ---

    def get_core_release_api_url(self) -> str:
        """获取 Core 版本检查 API 地址."""
        return self._get_value(
            "core_update.release_api_url",
            DEFAULT_CONFIG["core_update"]["release_api_url"],
        )

    def get_github_archive_url(self, version: str) -> str:
        """获取 GitHub 归档下载地址.

        Args:
            version: 版本号或 commit hash
        """
        template = self._get_value(
            "core_update.github_archive_url_template",
            DEFAULT_CONFIG["core_update"]["github_archive_url_template"],
        )
        return template.format(version=version)

    # --- Dashboard Update URLs ---

    def get_dashboard_registry_url(self, version: str) -> str:
        """获取 Dashboard Registry 下载地址.

        Args:
            version: 版本号或 "latest"
        """
        template = self._get_value(
            "dashboard_update.registry_url_template",
            DEFAULT_CONFIG["dashboard_update"]["registry_url_template"],
        )
        return template.format(version=version)

    def get_dashboard_github_release_api_url(self) -> str:
        """获取 Dashboard GitHub Release API 地址."""
        return self._get_value(
            "dashboard_update.github_release_api_url",
            DEFAULT_CONFIG["dashboard_update"]["github_release_api_url"],
        )

    def get_dashboard_github_release_download_url(self, tag: str) -> str:
        """获取 Dashboard GitHub Release 下载地址.

        Args:
            tag: 版本标签，如 "v4.25.1"
        """
        template = self._get_value(
            "dashboard_update.github_release_download_url_template",
            DEFAULT_CONFIG["dashboard_update"]["github_release_download_url_template"],
        )
        return template.format(tag=tag)

    def get_dashboard_harbour_url(self, version: str) -> str:
        """获取 Dashboard Harbour 下载地址.

        Args:
            version: 版本号或 commit hash
        """
        template = self._get_value(
            "dashboard_update.harbour_url_template",
            DEFAULT_CONFIG["dashboard_update"]["harbour_url_template"],
        )
        return template.format(version=version)

    # --- Proxy ---

    def is_proxy_enabled(self) -> bool:
        """是否启用代理."""
        return self._get_value("proxy.enabled", DEFAULT_CONFIG["proxy"]["enabled"])

    def get_proxy_url(self) -> str:
        """获取代理地址."""
        return self._get_value("proxy.url", DEFAULT_CONFIG["proxy"]["url"])

    def get_effective_proxy_url(self) -> str:
        """获取实际生效的代理地址（考虑 enabled 状态）."""
        if self.is_proxy_enabled():
            return self.get_proxy_url()
        return ""
