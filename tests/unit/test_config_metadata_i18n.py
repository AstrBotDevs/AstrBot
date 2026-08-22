"""Ensure Dashboard config-metadata i18n keys cover runtime metadata."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from astrbot.core.config.default import (
    CONFIG_METADATA_2,
    CONFIG_METADATA_3,
    CONFIG_METADATA_3_SYSTEM,
)
from astrbot.core.config.i18n_utils import ConfigMetadataI18n
from astrbot.core.platform.sources.line.line_adapter import (
    LINE_CONFIG_METADATA,
    LINE_I18N_RESOURCES,
)
from astrbot.core.platform.sources.napcat.napcat_platform_adapter import (
    NAPCAT_CONFIG_METADATA,
    NAPCAT_I18N_RESOURCES,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
I18N_DIR = REPO_ROOT / "dashboard" / "src" / "i18n" / "locales"
I18N_ATTRS = frozenset({"description", "hint", "labels", "name"})
LOCALES = ("zh-CN", "en-US")


def _flatten(obj: Any, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(obj, dict):
        for key, value in obj.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            out.update(_flatten(value, path))
        return out
    if prefix:
        out[prefix] = obj
    return out


def _load_locale(locale: str) -> dict[str, Any]:
    path = I18N_DIR / locale / "features" / "config-metadata.json"
    return _flatten(json.loads(path.read_text(encoding="utf-8")))


def _collect_converted_i18n_keys(metadata: dict[str, Any]) -> set[str]:
    converted = ConfigMetadataI18n.convert_to_i18n_keys(metadata)
    keys: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if (
                    key in I18N_ATTRS
                    and isinstance(value, str)
                    and value.endswith(f".{key}")
                ):
                    keys.add(value)
                else:
                    walk(value)
            return
        if isinstance(node, list):
            for item in node:
                walk(item)

    walk(converted)
    return keys


def _adapter_i18n_keys(name: str, metadata: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for field, field_meta in metadata.items():
        if not isinstance(field_meta, dict):
            continue
        for attr in I18N_ATTRS:
            if attr in field_meta:
                keys.add(f"platform_group.platform.{name}.{field}.{attr}")
    return keys


def _provider_template_hint_keys() -> set[str]:
    templates = CONFIG_METADATA_2["provider_group"]["metadata"]["provider"][
        "config_template"
    ]
    keys: set[str] = set()
    for template in templates.values():
        if not isinstance(template, dict):
            continue
        hint = template.get("hint")
        if isinstance(hint, str) and hint.startswith("provider_group.provider."):
            keys.add(hint)
    return keys


def _required_config_metadata_keys() -> set[str]:
    keys = set()
    keys.update(_collect_converted_i18n_keys(CONFIG_METADATA_3))
    keys.update(_collect_converted_i18n_keys(CONFIG_METADATA_3_SYSTEM))
    keys.update(
        _collect_converted_i18n_keys(
            {
                "platform_group": {
                    "metadata": {
                        "platform": CONFIG_METADATA_2["platform_group"]["metadata"][
                            "platform"
                        ]
                    }
                }
            }
        )
    )
    keys.update(_adapter_i18n_keys("line", LINE_CONFIG_METADATA))
    keys.update(_adapter_i18n_keys("napcat", NAPCAT_CONFIG_METADATA))
    keys.update(_provider_template_hint_keys())
    return keys


def test_config_metadata_i18n_covers_runtime_keys() -> None:
    required = _required_config_metadata_keys()
    missing: dict[str, list[str]] = {}
    for locale in LOCALES:
        actual = _load_locale(locale)
        locale_missing = sorted(key for key in required if key not in actual)
        if locale_missing:
            missing[locale] = locale_missing
    assert missing == {}, missing


def test_config_metadata_locale_trees_match() -> None:
    zh_keys = set(_load_locale("zh-CN"))
    en_keys = set(_load_locale("en-US"))
    assert sorted(zh_keys - en_keys) == []
    assert sorted(en_keys - zh_keys) == []


def test_platform_adapter_i18n_resources_cover_metadata_fields() -> None:
    for name, metadata, resources in (
        ("line", LINE_CONFIG_METADATA, LINE_I18N_RESOURCES),
        ("napcat", NAPCAT_CONFIG_METADATA, NAPCAT_I18N_RESOURCES),
    ):
        for locale in LOCALES:
            assert locale in resources, f"{name} missing {locale} i18n resources"
            locale_data = resources[locale]
            for field, field_meta in metadata.items():
                if not isinstance(field_meta, dict):
                    continue
                for attr in I18N_ATTRS:
                    if attr not in field_meta:
                        continue
                    value = locale_data.get(field, {}).get(attr)
                    assert value, f"{name}.{locale}.{field}.{attr} is empty"
