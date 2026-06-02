"""Dashboard 路由工具集。

这里放一些 dashboard routes 可复用的小工具函数。

目前主要用于「配置文件上传（file 类型配置项）」功能：
- 清洗/规范化用户可控的文件名与相对路径
- 将配置 key 映射到配置项独立子目录
"""

import os


def get_schema_item(schema: dict | None, key_path: str) -> dict | None:
    """按 dot-path 获取 schema 的节点。

    同时支持：
    - 扁平 schema（直接 key 命中）
    - 嵌套 object schema（{type: "object", items: {...}}）
    - template_list schema（<field>.templates.<template>.items）
    """

    if not isinstance(schema, dict) or not key_path:
        return None
    if key_path in schema:
        return schema.get(key_path)

    parts = key_path.split(".")
    current = schema
    idx = 0
    while idx < len(parts):
        part = parts[idx]
        if part not in current:
            return None
        meta = current.get(part)
        if idx == len(parts) - 1:
            return meta
        if not isinstance(meta, dict) or meta.get("type") != "object":
            if not isinstance(meta, dict) or meta.get("type") != "template_list":
                return None
            if idx + 2 >= len(parts) or parts[idx + 1] != "templates":
                return None
            template_meta = meta.get("templates", {}).get(parts[idx + 2])
            if not isinstance(template_meta, dict):
                return None
            if idx + 2 == len(parts) - 1:
                return template_meta
            current = template_meta.get("items", {})
            idx += 3
            continue
        current = meta.get("items", {})
        idx += 1
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
        if (
            ("a" <= ch <= "z")
            or ("A" <= ch <= "Z")
            or ch.isdigit()
            or ch
            in {
                "-",
                "_",
            }
        ):
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
