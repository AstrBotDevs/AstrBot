"""配置元数据国际化工具

提供配置元数据的国际化键转换功能
"""

from typing import Any, TypedDict, TypeGuard


def _is_str_keyed_dict(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict) and all(isinstance(key, str) for key in value)


class I18nGroup(TypedDict):
    name: str
    metadata: dict[str, Any]


class ConfigMetadataI18n:
    """配置元数据国际化转换器"""

    @staticmethod
    def _get_i18n_key(group: str, section: str, field: str, attr: str) -> str:
        """生成国际化键

        Args:
            group: 配置组,如 'ai_group', 'platform_group'
            section: 配置节,如 'agent_runner', 'general'
            field: 字段名,如 'enable', 'default_provider'
            attr: 属性类型,如 'description', 'hint', 'labels'

        Returns:
            国际化键,格式如: 'ai_group.agent_runner.enable.description'

        """
        if field:
            return f"{group}.{section}.{field}.{attr}"
        return f"{group}.{section}.{attr}"

    @staticmethod
    def convert_to_i18n_keys(metadata: dict[str, Any]) -> dict[str, I18nGroup]:
        """将配置元数据转换为使用国际化键

        Args:
            metadata: 原始配置元数据字典

        Returns:
            使用国际化键的配置元数据字典

        """
        result: dict[str, I18nGroup] = {}

        def convert_items(
            group: str,
            section: str,
            items: dict[str, object],
            prefix: str = "",
        ) -> dict[str, object]:
            items_result: dict[str, object] = {}

            for field_key, field_data in items.items():
                if not _is_str_keyed_dict(field_data):
                    items_result[field_key] = field_data
                    continue

                field_name = field_key
                field_path = f"{prefix}.{field_name}" if prefix else field_name

                field_result: dict[str, object] = {
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

                field_items = field_data.get("items")
                if _is_str_keyed_dict(field_items):
                    field_result["items"] = convert_items(
                        group,
                        section,
                        field_items,
                        field_path,
                    )

                template_schema = field_data.get("template_schema")
                if _is_str_keyed_dict(template_schema):
                    field_result["template_schema"] = convert_items(
                        group,
                        section,
                        template_schema,
                        f"{field_path}.template_schema",
                    )

                items_result[field_key] = field_result

            return items_result

        for group_key, group_data in metadata.items():
            if not _is_str_keyed_dict(group_data):
                continue

            group_metadata: dict[str, object] = {}
            group_result: I18nGroup = {
                "name": f"{group_key}.name",
                "metadata": group_metadata,
            }

            metadata_sections = group_data.get("metadata")
            if not _is_str_keyed_dict(metadata_sections):
                result[group_key] = group_result
                continue

            for section_key, section_data in metadata_sections.items():
                if not _is_str_keyed_dict(section_data):
                    continue

                section_result: dict[str, object] = {
                    key: value
                    for key, value in section_data.items()
                    if key not in {"description", "hint", "labels", "name"}
                }
                section_result["description"] = f"{group_key}.{section_key}.description"

                if "hint" in section_data:
                    section_result["hint"] = f"{group_key}.{section_key}.hint"

                section_items = section_data.get("items")
                if _is_str_keyed_dict(section_items):
                    section_result["items"] = convert_items(
                        group_key,
                        section_key,
                        section_items,
                    )

                group_metadata[section_key] = section_result

            result[group_key] = group_result

        return result
