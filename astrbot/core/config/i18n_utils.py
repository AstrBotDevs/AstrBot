"""
配置元数据国际化工具

提供配置元数据的国际化键转换功能
"""

from typing import Any


class ConfigMetadataI18n:
    """配置元数据国际化转换器"""

    @staticmethod
    def _get_i18n_key(group: str, section: str, field: str, attr: str) -> str:
        """
        生成国际化键

        Args:
            group: 配置组，如 'ai_group', 'platform_group'
            section: 配置节，如 'agent_runner', 'general'
            field: 字段名，如 'enable', 'default_provider'
            attr: 属性类型，如 'description', 'hint', 'labels'

        Returns:
            国际化键，格式如: 'ai_group.agent_runner.enable.description'
        """
        if field:
            return f"{group}.{section}.{field}.{attr}"
        else:
            return f"{group}.{section}.{attr}"

    @staticmethod
    def convert_to_i18n_keys(metadata: dict[str, Any]) -> dict[str, Any]:
        """
        将配置元数据转换为使用国际化键

        Args:
            metadata: 原始配置元数据字典

        Returns:
            使用国际化键的配置元数据字典
        """
        result = {}

        for group_key, group_data in metadata.items():
            group_result = {
                "name": f"{group_key}.name",
                "metadata": {},
            }

            for section_key, section_data in group_data.get("metadata", {}).items():
                section_result = {
                    "description": f"{group_key}.{section_key}.description",
                    "type": section_data.get("type"),
                }

                # 复制其他属性
                for key in ["items", "condition", "_special", "invisible"]:
                    if key in section_data:
                        section_result[key] = section_data[key]

                # 处理 hint
                if "hint" in section_data:
                    section_result["hint"] = f"{group_key}.{section_key}.hint"

                # 处理 items 中的字段
                if "items" in section_data and isinstance(section_data["items"], dict):
                    items_result = {}
                    for field_key, field_data in section_data["items"].items():
                        # 处理嵌套的点号字段名（如 provider_settings.enable）
                        field_name = field_key

                        field_result = {}

                        # 复制基本属性
                        for attr in [
                            "type",
                            "condition",
                            "_special",
                            "invisible",
                            "options",
                            "slider",
                        ]:
                            if attr in field_data:
                                field_result[attr] = field_data[attr]

                        # 转换文本属性为国际化键
                        if "description" in field_data:
                            field_result["description"] = (
                                f"{group_key}.{section_key}.{field_name}.description"
                            )

                        if "hint" in field_data:
                            field_result["hint"] = (
                                f"{group_key}.{section_key}.{field_name}.hint"
                            )

                        if "labels" in field_data:
                            field_result["labels"] = (
                                f"{group_key}.{section_key}.{field_name}.labels"
                            )

                        items_result[field_key] = field_result

                    section_result["items"] = items_result

                group_result["metadata"][section_key] = section_result

            result[group_key] = group_result

        return result
