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
        """Convert config metadata text fields to i18n keys.

        Replaces ``description``, ``hint``, ``labels``, and ``name`` with i18n
        keys. Other fields, including ``docs``, are copied through unchanged.
        Unknown top-level tab-group fields are also preserved.

        Args:
            metadata: Raw configuration metadata dictionary.

        Returns:
            Metadata dictionary whose translatable fields are i18n keys.
        """
        result = {}

        def convert_items(
            group: str, section: str, items: dict[str, Any], prefix: str = ""
        ) -> dict[str, Any]:
            items_result: dict[str, Any] = {}

            for field_key, field_data in items.items():
                if not isinstance(field_data, dict):
                    items_result[field_key] = field_data
                    continue

                field_name = field_key
                field_path = f"{prefix}.{field_name}" if prefix else field_name

                field_result = {
                    key: value
                    for key, value in field_data.items()
                    if key not in {"description", "hint", "labels", "name"}
                }

                if "description" in field_data:
                    field_result["description"] = (
                        f"{group}.{section}.{field_path}.description"
                    )
                if "hint" in field_data:
                    field_result["hint"] = f"{group}.{section}.{field_path}.hint"
                if "labels" in field_data:
                    field_result["labels"] = f"{group}.{section}.{field_path}.labels"
                if "name" in field_data:
                    field_result["name"] = f"{group}.{section}.{field_path}.name"

                if "items" in field_data and isinstance(field_data["items"], dict):
                    field_result["items"] = convert_items(
                        group, section, field_data["items"], field_path
                    )

                if "template_schema" in field_data and isinstance(
                    field_data["template_schema"], dict
                ):
                    field_result["template_schema"] = convert_items(
                        group,
                        section,
                        field_data["template_schema"],
                        f"{field_path}.template_schema",
                    )

                items_result[field_key] = field_result

            return items_result

        for group_key, group_data in metadata.items():
            if not isinstance(group_data, dict):
                result[group_key] = group_data
                continue

            group_result = {
                key: value
                for key, value in group_data.items()
                if key not in {"name", "metadata"}
            }
            group_result["name"] = f"{group_key}.name"
            group_result["metadata"] = {}

            for section_key, section_data in group_data.get("metadata", {}).items():
                section_result = {
                    key: value
                    for key, value in section_data.items()
                    if key not in {"description", "hint", "labels", "name"}
                }
                section_result["description"] = f"{group_key}.{section_key}.description"

                if "hint" in section_data:
                    section_result["hint"] = f"{group_key}.{section_key}.hint"

                if "items" in section_data and isinstance(section_data["items"], dict):
                    section_result["items"] = convert_items(
                        group_key, section_key, section_data["items"]
                    )

                group_result["metadata"][section_key] = section_result

            result[group_key] = group_result

        return result
