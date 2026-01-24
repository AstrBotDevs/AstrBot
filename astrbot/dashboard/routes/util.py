"""Dashboard 路由工具集。

这里放一些 dashboard routes 可复用的小工具函数。

目前主要用于「配置文件上传（file 类型配置项）」功能：
- 清洗/规范化用户可控的文件名与相对路径
- 将配置 key 映射到配置项独立子目录
- 在保存配置时应用暂存区文件变更（移动/删除/迁移旧路径）
"""

from __future__ import annotations

import os
from typing import Any

from astrbot.core.utils.io import remove_dir


def get_schema_item(schema: dict | None, key_path: str) -> dict | None:
    """按 dot-path 获取 schema 的节点。

    同时支持：
    - 扁平 schema（直接 key 命中）
    - 嵌套 object schema（{type: "object", items: {...}}）
    """

    if not isinstance(schema, dict) or not key_path:
        return None
    if key_path in schema:
        return schema.get(key_path)

    current = schema
    parts = key_path.split(".")
    for idx, part in enumerate(parts):
        if part not in current:
            return None
        meta = current.get(part)
        if idx == len(parts) - 1:
            return meta
        if not isinstance(meta, dict) or meta.get("type") != "object":
            return None
        current = meta.get("items", {})
    return None


def sanitize_filename(name: str) -> str:
    """清洗上传文件名，避免路径穿越与非法名称。

    - 丢弃目录部分，仅保留 basename
    - 将路径分隔符替换为下划线
    - 拒绝空字符串 / "." / ".."
    """

    cleaned = os.path.basename(name).strip()
    if not cleaned or cleaned in {".", ".."}:
        return ""
    for sep in (os.sep, os.altsep):
        if sep:
            cleaned = cleaned.replace(sep, "_")
    return cleaned


def sanitize_path_segment(segment: str) -> str:
    """清洗目录片段（URL/path 安全，避免穿越）。

    仅保留 [A-Za-z0-9_-]，其余替换为 "_"
    """

    cleaned = []
    for ch in segment:
        if ("a" <= ch <= "z") or ("A" <= ch <= "Z") or ch.isdigit() or ch in {
            "-",
            "_",
        }:
            cleaned.append(ch)
        else:
            cleaned.append("_")
    result = "".join(cleaned).strip("_")
    return result or "_"


def config_key_to_folder(key_path: str) -> str:
    """将 dot-path 的配置 key 转成稳定的文件夹路径。"""

    parts = [sanitize_path_segment(p) for p in key_path.split(".") if p]
    return "/".join(parts) if parts else "_"


def normalize_rel_path(rel_path: str | None) -> str | None:
    """规范化用户传入的相对路径，并阻止路径穿越。"""

    if not isinstance(rel_path, str):
        return None
    rel = rel_path.replace("\\", "/").lstrip("/")
    if not rel:
        return None
    parts = [p for p in rel.split("/") if p]
    if any(part in {".", ".."} for part in parts):
        return None
    if rel.startswith("../") or "/../" in rel:
        return None
    return "/".join(parts)


def get_value_by_path(data: dict, key_path: str):
    """按 dot-path 获取嵌套 dict 的值（也支持直接 key 命中）。"""

    if key_path in data:
        return data.get(key_path)
    current = data
    for part in key_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current.get(part)
    return current


def set_value_by_path(data: dict, key_path: str, value) -> None:
    """按 dot-path 设置嵌套 dict 的值（也支持直接 key 命中）。"""

    if key_path in data:
        data[key_path] = value
        return
    current = data
    parts = key_path.split(".")
    for part in parts[:-1]:
        if part not in current or not isinstance(current[part], dict):
            current[part] = {}
        current = current[part]
    current[parts[-1]] = value


def collect_file_keys(schema: dict, prefix: str = "") -> list[str]:
    """收集 schema 中所有 type == 'file' 的配置项 key_path。"""

    keys: list[str] = []
    for key, meta in schema.items():
        if not isinstance(meta, dict):
            continue
        meta_type = meta.get("type")
        if meta_type == "file":
            keys.append(f"{prefix}{key}" if prefix else key)
        elif meta_type == "object":
            child_prefix = f"{prefix}{key}." if prefix else f"{key}."
            keys.extend(collect_file_keys(meta.get("items", {}), child_prefix))
    return keys


def normalize_file_list(value: Any, key_path: str) -> tuple[list[str], bool]:
    """规范化某个 file 类型配置项的值（list[str]）。

    强制配置项隔离（每个配置项一个子目录）：
      files/<key-folder>/<filename>

    同时支持迁移旧格式：
      files/<filename>
    """

    if value is None:
        return [], False
    if not isinstance(value, list):
        raise ValueError(f"Invalid file list for {key_path}")

    folder = config_key_to_folder(key_path)
    expected_prefix = f"files/{folder}/"

    results: list[str] = []
    changed = False
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"Invalid file entry for {key_path}")
        rel = normalize_rel_path(item)
        if not rel or not rel.startswith("files/"):
            raise ValueError(f"Invalid file path: {item}")

        if rel.startswith(expected_prefix):
            results.append(rel)
            continue

        # 兼容旧格式：files/<filename> -> files/<key-folder>/<filename>
        if rel.count("/") == 1:
            filename = rel.split("/", 1)[1]
            if not filename:
                raise ValueError(f"Invalid file path: {item}")
            results.append(f"{expected_prefix}{filename}")
            changed = True
            continue

        raise ValueError(f"Invalid file path: {item}")

    return results, changed


def apply_config_file_ops(
    *,
    schema: dict | None,
    old_config: dict,
    post_configs: dict,
    storage_root: str,
    staging_root: str,
) -> None:
    """根据配置变更应用暂存区文件操作。

    对于每个 `type: "file"` 的配置项，配置值为 `list[str]`，每一项是相对路径：
      files/<key-folder>/<filename>

    该函数会：
    1) 规范化配置中的路径（并迁移旧格式 files/<filename>）。
    2) 将暂存上传从 `staging_root/<rel_path>` 移动到 `storage_root/<rel_path>`。
    3) 删除配置中已移除的文件（在 `storage_root` 下）。
    4) 清理暂存目录。
    """

    if not isinstance(schema, dict):
        return

    file_keys = collect_file_keys(schema)
    if not file_keys:
        return

    storage_root_abs = os.path.abspath(storage_root)
    staging_root_abs = os.path.abspath(staging_root)

    new_file_set: set[str] = set()
    old_file_set: set[str] = set()

    for key_path in file_keys:
        new_list, new_changed = normalize_file_list(
            get_value_by_path(post_configs, key_path),
            key_path,
        )
        if new_changed:
            set_value_by_path(post_configs, key_path, new_list)

        old_list, _ = normalize_file_list(
            get_value_by_path(old_config, key_path),
            key_path,
        )

        new_file_set.update(new_list)
        old_file_set.update(old_list)

    # 1) Materialize referenced files (staged -> final, or keep existing).
    for rel_path in sorted(new_file_set):
        final_path = os.path.abspath(os.path.join(storage_root_abs, rel_path))
        if not final_path.startswith(storage_root_abs + os.sep):
            raise ValueError(f"Invalid file path: {rel_path}")

        staged_path = os.path.abspath(os.path.join(staging_root_abs, rel_path))
        if not staged_path.startswith(staging_root_abs + os.sep):
            raise ValueError(f"Invalid staged path: {rel_path}")

        if os.path.exists(staged_path):
            os.makedirs(os.path.dirname(final_path), exist_ok=True)
            os.replace(staged_path, final_path)
            continue

        # 兼容旧路径：storage_root/files/<basename> -> storage_root/<rel_path>
        legacy_path = os.path.join(
            storage_root_abs,
            "files",
            os.path.basename(rel_path),
        )
        if os.path.isfile(legacy_path):
            os.makedirs(os.path.dirname(final_path), exist_ok=True)
            os.replace(legacy_path, final_path)
            continue

        if not os.path.exists(final_path):
            raise ValueError(f"Missing staged file: {rel_path}")

    # 2) 删除配置里被移除的文件。
    for rel_path in sorted(old_file_set - new_file_set):
        final_path = os.path.abspath(os.path.join(storage_root_abs, rel_path))
        if not final_path.startswith(storage_root_abs + os.sep):
            continue
        if os.path.isfile(final_path):
            os.remove(final_path)
            continue

        legacy_path = os.path.join(
            storage_root_abs,
            "files",
            os.path.basename(rel_path),
        )
        if os.path.isfile(legacy_path):
            os.remove(legacy_path)

    # 3) 保存后清理该 scope 的暂存目录。
    if os.path.isdir(staging_root_abs):
        remove_dir(staging_root_abs)
