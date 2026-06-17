from __future__ import annotations

from astrbot.core.db import BaseDatabase

PREFERENCE_SCOPE = "global"
PREFERENCE_SCOPE_ID = "global"
PREFERENCE_KEY = "plugin_pinned_extensions"


class PluginPreferenceService:
    """Dashboard 插件全局偏好服务。

    当前仅用于持久化插件置顶顺序。数据存储在 preferences 表中，
    使用 global scope，因此是 Dashboard 全局偏好，不按登录用户隔离。
    """

    def __init__(self, db: BaseDatabase) -> None:
        """初始化服务。

        Args:
            db: 数据库访问对象，直接使用 BaseDatabase 的 preference 方法。
        """
        self.db = db

    @staticmethod
    def normalize_pinned_extensions(value: object) -> list[str]:
        """将任意输入归一化为置顶插件名称列表。

        过滤规则：
        - 仅保留非空字符串；
        - 去除首尾空白；
        - 按出现顺序去重；
        - 脏数据或非列表输入兜底为空列表。

        Args:
            value: 待归一化的原始值。

        Returns:
            归一化后的插件名称列表。
        """
        if not isinstance(value, list):
            return []

        seen: set[str] = set()
        result: list[str] = []
        for item in value:
            if not isinstance(item, str):
                continue
            name = item.strip()
            if not name or name in seen:
                continue
            seen.add(name)
            result.append(name)
        return result

    async def get_pinned_extensions(self) -> tuple[list[str], bool]:
        """从数据库读取置顶插件列表。

        Returns:
            已归一化的置顶插件名称列表，以及该偏好记录是否存在。
        """
        preference = await self.db.get_preference(
            PREFERENCE_SCOPE,
            PREFERENCE_SCOPE_ID,
            PREFERENCE_KEY,
        )

        preference_exists = preference is not None
        if not preference_exists or not isinstance(preference.value, dict):
            return [], preference_exists

        return self.normalize_pinned_extensions(preference.value.get("val")), True

    async def set_pinned_extensions(self, names: object) -> list[str]:
        """保存置顶插件列表到数据库。

        Args:
            names: 待保存的插件名称列表，可为任意内容，会先归一化。

        Returns:
            归一化后实际保存的插件名称列表。
        """
        normalized = self.normalize_pinned_extensions(names)
        await self.db.insert_preference_or_update(
            PREFERENCE_SCOPE,
            PREFERENCE_SCOPE_ID,
            PREFERENCE_KEY,
            {"val": normalized},
        )
        return normalized
