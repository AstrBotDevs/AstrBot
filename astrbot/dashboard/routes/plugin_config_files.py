import os
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from quart import request

from astrbot.core import logger
from astrbot.core.star.star import star_registry
from astrbot.core.star.star_tools import StarTools

from .route import Route, Response, RouteContext


def _find_plugin_md(plugin_name: str):
    for md in star_registry:
        if md.name == plugin_name:
            return md
    return None


def _resolve_field_schema(schema: Dict[str, Any], field: str) -> Optional[Dict[str, Any]]:
    """Find the schema object for a field. Support flat schema and object nesting 1-level for safety.

    Note: Current UI passes top-level field names. This supports nested paths like "a.b" as best-effort.
    """
    if field in schema:
        return schema.get(field)

    # Support dot selector for object nesting (limited depth)
    parts = field.split(".")
    curr = schema
    for idx, key in enumerate(parts):
        node = curr.get(key)
        if not isinstance(node, dict):
            return None
        if idx == len(parts) - 1:
            return node
        if node.get("type") != "object":
            return None
        curr = node.get("items", {})
    return None


def _ensure_inside_root(root: Path, target: Path) -> bool:
    try:
        root_r = root.resolve()
        tgt_r = target.resolve()
        return str(tgt_r).startswith(str(root_r))
    except Exception:
        return False


def _gen_safe_filename(tmpl: str, original_name: str) -> str:
    name, ext = os.path.splitext(original_name)
    ext = ext.lower()
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    uid = uuid.uuid4().hex

    def sanitize(text: str) -> str:
        # keep letters/numbers/underscore/dash/dot and CJK letters
        out = []
        for ch in text:
            if ch.isalnum() or ch in ("-", "_", ".", " "):
                out.append(ch)
        s = "".join(out).strip().replace(" ", "_")
        # no path traversal or separators
        s = s.replace("..", "_").replace("/", "_").replace("\\", "_")
        return s or uid  # fallback to uid if empty

    name_clean = sanitize(name)
    original_clean = f"{name_clean}{ext}"

    # Support direct original name keepers
    if tmpl.strip().lower() in ("original", "{original}", "{filename}"):
        safe = original_clean
    else:
        # Known placeholders: {timestamp} {uuid} {ext} {name} {original}
        safe = (
            tmpl.replace("{timestamp}", ts)
            .replace("{uuid}", uid)
            .replace("{ext}", ext)
            .replace("{name}", name_clean)
            .replace("{original}", original_clean)
        )
        safe = sanitize(safe)

        # Ensure extension consistency when user forgot {ext}
        if not safe.endswith(ext):
            # keep as-is; schema's accept has already validated the ext
            pass

    return safe


class PluginConfigFileFieldRoute(Route):
    """Per-plugin file field manager (list/upload/delete)."""

    def __init__(self, context: RouteContext) -> None:
        super().__init__(context)
        self.routes = {
            "/plugin/<plugin_name>/config/filefield/list": ("GET", self.list_files),
            "/plugin/<plugin_name>/config/filefield/upload": (
                "POST",
                self.upload_file,
            ),
            "/plugin/<plugin_name>/config/filefield/delete": (
                "DELETE",
                self.delete_file,
            ),
        }
        self.register_routes()

    async def _resolve_dest_dir(
        self, plugin_name: str, field: str
    ) -> Tuple[Path, Dict[str, Any]]:
        md = _find_plugin_md(plugin_name)
        if not md:
            raise ValueError(f"插件 {plugin_name} 不存在")
        if not md.config:
            raise ValueError(f"插件 {plugin_name} 没有注册配置")

        schema = md.config.schema or {}
        field_schema = _resolve_field_schema(schema, field)
        if not field_schema:
            raise ValueError(f"字段 {field} 未在 _conf_schema.json 中定义")
        if field_schema.get("type") != "file":
            raise ValueError(f"字段 {field} 不是 file 类型")

        dest_dir = field_schema.get("dest_dir")
        if not dest_dir or not isinstance(dest_dir, str):
            raise ValueError(f"字段 {field} 缺少必填 dest_dir")

        # Root is StarTools.get_data_dir(plugin_name)
        root = StarTools.get_data_dir(plugin_name)
        target_root = (root / dest_dir).resolve()
        target_root.mkdir(parents=True, exist_ok=True)
        if not _ensure_inside_root(root, target_root):
            raise ValueError("非法目录: 超出插件数据目录")
        return target_root, field_schema

    async def list_files(self, plugin_name: str):
        try:
            field = request.args.get("field", type=str)
            if not field:
                return Response().error("缺少参数 field").__dict__

            target_root, _ = await self._resolve_dest_dir(plugin_name, field)
            root = StarTools.get_data_dir(plugin_name)

            files = []
            if target_root.exists():
                for entry in target_root.iterdir():
                    if entry.is_file():
                        stat = entry.stat()
                        rel_path = str(entry.resolve()).replace(str(root.resolve()) + os.sep, "")
                        files.append(
                            {
                                "name": entry.name,
                                "rel_path": rel_path.replace("\\", "/"),
                                "size": stat.st_size,
                                "mtime": int(stat.st_mtime),
                            }
                        )

            files.sort(key=lambda x: x["mtime"], reverse=True)
            return Response().ok(files).__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(str(e)).__dict__

    async def upload_file(self, plugin_name: str):
        try:
            form = await request.form
            field = form.get("field") if form else None
            if not field:
                return Response().error("缺少参数 field").__dict__

            files = await request.files
            file = files.get("file") if files else None
            if not file:
                return Response().error("缺少文件 file").__dict__

            target_root, field_schema = await self._resolve_dest_dir(plugin_name, field)
            root = StarTools.get_data_dir(plugin_name)

            # Validate extension
            accept = field_schema.get("accept")
            orig_name = file.filename or "upload.bin"
            _, ext = os.path.splitext(orig_name)
            ext = ext.lower()
            if accept and isinstance(accept, list):
                normalized = [s.lower() for s in accept]
                if ext not in normalized:
                    return Response().error(f"非法后缀: {ext}").__dict__

            # Read content (for size check and write)
            # Quart's FileStorage.read() returns bytes (not awaitable)
            content: bytes = file.read()
            max_mb = field_schema.get("max_size_mb")
            if isinstance(max_mb, (int, float)) and max_mb > 0:
                if len(content) > max_mb * 1024 * 1024:
                    return Response().error("文件过大").__dict__

            name_tmpl = field_schema.get("name_template", "{timestamp}-{uuid}{ext}")
            safe_name = _gen_safe_filename(name_tmpl, orig_name)
            dest_path = (target_root / safe_name).resolve()
            if not _ensure_inside_root(root, dest_path):
                return Response().error("非法路径").__dict__

            with open(dest_path, "wb") as f:
                f.write(content)

            rel_path = str(dest_path).replace(str(root.resolve()) + os.sep, "").replace("\\", "/")

            # Update plugin config value
            md = _find_plugin_md(plugin_name)
            if not md or not md.config:
                return Response().error("插件配置未注册").__dict__

            # multiple=false: overwrite string; if true: append to array (not exposed in UI now)
            multiple = bool(field_schema.get("multiple", False))
            new_conf = dict(md.config)
            if multiple:
                cur = new_conf.get(field)
                if not isinstance(cur, list):
                    cur = []
                cur.append(rel_path)
                new_conf[field] = cur
            else:
                new_conf[field] = rel_path
            md.config.save_config(new_conf)

            stat = os.stat(dest_path)
            return Response().ok(
                {
                    "ok": True,
                    "path": rel_path,
                    "size": stat.st_size,
                    "mtime": int(stat.st_mtime),
                }
            ).__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(str(e)).__dict__

    async def delete_file(self, plugin_name: str):
        try:
            field = request.args.get("field", type=str)
            rel_path = request.args.get("path", type=str)
            if not field or not rel_path:
                return Response().error("缺少参数 field 或 path").__dict__

            target_root, field_schema = await self._resolve_dest_dir(plugin_name, field)
            root = StarTools.get_data_dir(plugin_name)

            target_file = (root / rel_path).resolve()
            if not _ensure_inside_root(target_root, target_file):
                return Response().error("非法路径").__dict__
            if target_file.exists() and target_file.is_file():
                target_file.unlink()

            # If current config value equals this file, clear it
            md = _find_plugin_md(plugin_name)
            if md and md.config:
                new_conf = dict(md.config)
                multiple = bool(field_schema.get("multiple", False))
                if multiple:
                    cur = new_conf.get(field)
                    if isinstance(cur, list):
                        new_conf[field] = [p for p in cur if p != rel_path]
                else:
                    if new_conf.get(field) == rel_path:
                        new_conf[field] = ""
                md.config.save_config(new_conf)

            return Response().ok({"ok": True}).__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(str(e)).__dict__
