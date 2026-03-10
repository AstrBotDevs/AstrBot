import asyncio
import hashlib
import json
import mimetypes
import os
import posixpath
import re
import ssl
import traceback
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

import aiofiles
import aiohttp
import certifi
import jwt
from aiofiles import ospath as aio_ospath
from quart import Response as QuartResponse
from quart import g, make_response, request

from astrbot.api import sp
from astrbot.core import DEMO_MODE, file_token_service, logger
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.filter.command_group import CommandGroupFilter
from astrbot.core.star.filter.permission import PermissionTypeFilter
from astrbot.core.star.filter.regex import RegexFilter
from astrbot.core.star.star import StarMetadata
from astrbot.core.star.star_handler import EventType, star_handlers_registry
from astrbot.core.star.star_manager import (
    PluginManager,
    PluginVersionIncompatibleError,
)
from astrbot.core.utils.astrbot_path import (
    get_astrbot_data_path,
    get_astrbot_temp_path,
)

from .route import Response, Route, RouteContext

PLUGIN_UPDATE_CONCURRENCY = (
    3  # limit concurrent updates to avoid overwhelming plugin sources
)
_PLUGIN_WEBUI_BRIDGE_FILE = (
    Path(__file__).resolve().parent.parent / "plugin_webui_bridge.js"
)
_HTML_ASSET_ATTR_RE = re.compile(
    r"(?P<attr>src|href)=(?P<quote>[\"\'])(?P<url>.*?)(?P=quote)",
    re.IGNORECASE,
)
_CSS_URL_RE = re.compile(
    r"url\(\s*(?P<quote>[\"\']?)(?P<url>.*?)(?P=quote)\s*\)",
    re.IGNORECASE,
)
_JS_DYNAMIC_IMPORT_RE = re.compile(
    r"(?P<prefix>\bimport\s*\(\s*)(?P<quote>[\"\'])(?P<url>.*?)(?P=quote)(?P<suffix>\s*\))",
    re.IGNORECASE,
)
_JS_MODULE_FROM_RE = re.compile(
    r"(?P<prefix>\b(?:import|export)\s+(?:[^;]*?\s+from\s+))(?P<quote>[\"\'])(?P<url>.*?)(?P=quote)",
    re.IGNORECASE | re.DOTALL,
)
_JS_SIDE_EFFECT_IMPORT_RE = re.compile(
    r"(?P<prefix>\bimport\s+)(?P<quote>[\"\'])(?P<url>[^\"'\r\n]+)(?P=quote)",
    re.IGNORECASE,
)
_PLUGIN_WEBUI_ASSET_TOKEN_TYPE = "plugin_webui_asset"
_PLUGIN_WEBUI_ASSET_TOKEN_TTL_SECONDS = 60


def _normalize_plugin_webui_asset_path(asset_path: str) -> str:
    return PluginRoute._normalize_plugin_webui_path(asset_path, allow_empty=True)


@dataclass
class RegistrySource:
    urls: list[str]
    cache_file: str
    md5_url: str | None  # None means "no remote MD5, always treat cache as stale"


class PluginRoute(Route):
    def __init__(
        self,
        context: RouteContext,
        core_lifecycle: AstrBotCoreLifecycle,
        plugin_manager: PluginManager,
    ) -> None:
        super().__init__(context)
        self.routes = {
            "/plugin/get": ("GET", self.get_plugins),
            "/plugin/check-compat": ("POST", self.check_plugin_compatibility),
            "/plugin/install": ("POST", self.install_plugin),
            "/plugin/install-upload": ("POST", self.install_plugin_upload),
            "/plugin/update": ("POST", self.update_plugin),
            "/plugin/update-all": ("POST", self.update_all_plugins),
            "/plugin/uninstall": ("POST", self.uninstall_plugin),
            "/plugin/uninstall-failed": ("POST", self.uninstall_failed_plugin),
            "/plugin/market_list": ("GET", self.get_online_plugins),
            "/plugin/off": ("POST", self.off_plugin),
            "/plugin/on": ("POST", self.on_plugin),
            "/plugin/reload-failed": ("POST", self.reload_failed_plugins),
            "/plugin/reload": ("POST", self.reload_plugins),
            "/plugin/readme": ("GET", self.get_plugin_readme),
            "/plugin/changelog": ("GET", self.get_plugin_changelog),
            "/plugin/source/get": ("GET", self.get_custom_source),
            "/plugin/source/save": ("POST", self.save_custom_source),
            "/plugin/source/get-failed-plugins": ("GET", self.get_failed_plugins),
        }
        self.core_lifecycle = core_lifecycle
        self.plugin_manager = plugin_manager
        self.register_routes()
        self.app.add_url_rule(
            "/api/plugin/webui/content/<plugin_name>/",
            endpoint="plugin_webui_content_entry",
            view_func=self.get_plugin_webui_entry,
            methods=["GET"],
        )
        self.app.add_url_rule(
            "/api/plugin/webui/content/<plugin_name>/<path:asset_path>",
            endpoint="plugin_webui_content_asset",
            view_func=self.get_plugin_webui_asset,
            methods=["GET"],
        )
        self.app.add_url_rule(
            "/api/plugin/webui/bridge-sdk.js",
            endpoint="plugin_webui_bridge_sdk",
            view_func=self.get_plugin_webui_bridge_sdk,
            methods=["GET"],
        )

        self.translated_event_type = {
            EventType.AdapterMessageEvent: "平台消息下发时",
            EventType.OnLLMRequestEvent: "LLM 请求时",
            EventType.OnLLMResponseEvent: "LLM 响应后",
            EventType.OnDecoratingResultEvent: "回复消息前",
            EventType.OnCallingFuncToolEvent: "函数工具",
            EventType.OnAfterMessageSentEvent: "发送消息后",
            EventType.OnPluginErrorEvent: "插件报错时",
        }

        self._logo_cache = {}

    async def get_plugin_webui_entry(self, plugin_name: str):
        return await self._serve_plugin_webui_content(plugin_name, "")

    async def get_plugin_webui_asset(
        self,
        plugin_name: str,
        asset_path: str,
    ):
        return await self._serve_plugin_webui_content(plugin_name, asset_path)

    async def get_plugin_webui_bridge_sdk(self):
        if not await aio_ospath.isfile(str(_PLUGIN_WEBUI_BRIDGE_FILE)):
            return await self._plugin_webui_error_response(
                404, "Plugin WebUI bridge SDK not found"
            )
        bridge_js = await self._read_plugin_webui_binary(_PLUGIN_WEBUI_BRIDGE_FILE)
        response = cast(
            QuartResponse,
            await make_response(
                bridge_js, {"Content-Type": "application/javascript; charset=utf-8"}
            ),
        )
        return self._apply_plugin_webui_security_headers(response)

    def _get_plugin_metadata_by_name(self, plugin_name: str) -> StarMetadata | None:
        for plugin in self.plugin_manager.context.get_all_stars():
            if plugin.name == plugin_name:
                return plugin
        return None

    @staticmethod
    def _normalize_plugin_webui_path(
        raw_path: str,
        *,
        base_dir: str | None = None,
        allow_empty: bool = False,
    ) -> str:
        path = raw_path.replace("\\", "/").strip()
        if base_dir:
            path = posixpath.join(base_dir, path)
        normalized = posixpath.normpath(path)
        if normalized in {"", "."}:
            if allow_empty:
                return ""
            raise ValueError("Invalid plugin WebUI asset path")
        if (
            normalized.startswith("../")
            or normalized == ".."
            or normalized.startswith("/")
        ):
            raise ValueError("Invalid plugin WebUI asset path")
        return normalized

    def _get_plugin_root_dir(self, plugin: StarMetadata) -> Path:
        if not plugin.root_dir_name:
            raise FileNotFoundError("Plugin directory metadata is missing")

        base_dir = Path(
            self.plugin_manager.reserved_plugin_path
            if plugin.reserved
            else self.plugin_manager.plugin_store_path
        ).resolve(strict=False)
        plugin_root = (base_dir / plugin.root_dir_name).resolve(strict=False)
        plugin_root.relative_to(base_dir)
        return plugin_root

    async def _resolve_plugin_webui_root(
        self,
        plugin: StarMetadata,
    ) -> Path:
        page = plugin.webui
        if not page:
            raise FileNotFoundError("Plugin WebUI metadata is missing")

        plugin_root = self._get_plugin_root_dir(plugin)
        page_root = (plugin_root / page.root_dir).resolve(strict=False)
        page_root.relative_to(plugin_root)
        if page_root == plugin_root:
            raise FileNotFoundError("Plugin WebUI root directory is invalid")
        if not await aio_ospath.isdir(str(page_root)):
            raise FileNotFoundError("Plugin WebUI root directory does not exist")
        return page_root

    async def _resolve_plugin_webui_file(
        self,
        plugin: StarMetadata,
        asset_path: str,
    ) -> Path:
        page = plugin.webui
        if not page:
            raise FileNotFoundError("Plugin WebUI metadata is missing")

        page_root = await self._resolve_plugin_webui_root(plugin)
        target_name = _normalize_plugin_webui_asset_path(asset_path) or page.entry_file
        target_path = (page_root / target_name).resolve(strict=False)
        target_path.relative_to(page_root)
        if not await aio_ospath.isfile(str(target_path)):
            raise FileNotFoundError("Plugin WebUI asset not found")
        return target_path

    @staticmethod
    def _is_rewritable_asset_url(raw_url: str) -> bool:
        value = raw_url.strip()
        lower = value.lower()
        if not value:
            return False
        if value.startswith(("#", "/#")):
            return False
        if lower.startswith(
            (
                "http://",
                "https://",
                "//",
                "data:",
                "javascript:",
                "mailto:",
                "tel:",
                "blob:",
            )
        ):
            return False
        return True

    @staticmethod
    def _resolve_referenced_asset_path(
        base_asset_path: str,
        referenced_url: str,
    ) -> str:
        parts = urlsplit(referenced_url)
        referenced_path = parts.path.strip()
        if not referenced_path:
            raise ValueError("Plugin WebUI referenced asset path is empty")
        base_dir = posixpath.dirname(base_asset_path) if base_asset_path else ""
        normalized = PluginRoute._normalize_plugin_webui_path(
            referenced_path,
            base_dir=base_dir,
        )
        if not normalized:
            raise ValueError("Plugin WebUI referenced asset path is invalid")
        return normalized

    def _build_plugin_webui_asset_url(
        self,
        plugin_name: str,
        asset_path: str,
        original_query: str = "",
        original_fragment: str = "",
        extra_query_params: dict[str, str] | None = None,
    ) -> str:
        path = self._build_plugin_webui_content_path(plugin_name, asset_path)
        query_dict = dict(parse_qsl(original_query, keep_blank_values=True))
        if extra_query_params:
            for key, value in extra_query_params.items():
                if value:
                    query_dict[key] = value
        query = urlencode(query_dict)
        return urlunsplit(
            (
                "",
                "",
                path,
                query,
                original_fragment,
            )
        )

    @staticmethod
    def _build_plugin_webui_content_path(
        plugin_name: str,
        asset_path: str = "",
    ) -> str:
        encoded_plugin_name = quote(plugin_name, safe="")
        if not asset_path:
            return f"/api/plugin/webui/content/{encoded_plugin_name}/"
        safe_asset_path = _normalize_plugin_webui_asset_path(asset_path)
        encoded_path = "/".join(
            quote(part, safe="") for part in safe_asset_path.split("/")
        )
        return f"/api/plugin/webui/content/{encoded_plugin_name}/{encoded_path}"

    @staticmethod
    def _get_plugin_webui_bridge_sdk_url(
        extra_query_params: dict[str, str] | None = None,
    ) -> str:
        query = urlencode(extra_query_params or {})
        return urlunsplit(
            (
                "",
                "",
                "/api/plugin/webui/bridge-sdk.js",
                query,
                "",
            )
        )

    @staticmethod
    def _is_js_relative_module_specifier(raw_url: str) -> bool:
        value = raw_url.strip()
        return value.startswith(("./", "../", "/"))

    def _rewrite_relative_asset_url(
        self,
        raw_url: str,
        base_asset_path: str,
        plugin_name: str,
        extra_query_params: dict[str, str] | None = None,
    ) -> str | None:
        candidate = raw_url.strip()
        if not self._is_rewritable_asset_url(candidate):
            return None
        parts = urlsplit(candidate)
        asset_path = self._resolve_referenced_asset_path(base_asset_path, candidate)
        return self._build_plugin_webui_asset_url(
            plugin_name,
            asset_path,
            original_query=parts.query,
            original_fragment=parts.fragment,
            extra_query_params=extra_query_params,
        )

    def _rewrite_plugin_webui_html(
        self,
        html_text: str,
        plugin_name: str,
        entry_asset_path: str,
        extra_query_params: dict[str, str] | None = None,
    ) -> str:
        def replace_attr(match: re.Match[str]) -> str:
            raw_url = match.group("url")
            attr = match.group("attr")
            quote_char = match.group("quote")

            if raw_url.strip() == "/api/plugin/webui/bridge-sdk.js":
                url = self._get_plugin_webui_bridge_sdk_url(extra_query_params)
                return f"{attr}={quote_char}{url}{quote_char}"

            if not self._is_rewritable_asset_url(raw_url):
                return match.group(0)

            try:
                rewritten_url = self._rewrite_relative_asset_url(
                    raw_url,
                    entry_asset_path,
                    plugin_name,
                    extra_query_params=extra_query_params,
                )
                if not rewritten_url:
                    return match.group(0)
                return f"{attr}={quote_char}{rewritten_url}{quote_char}"
            except ValueError:
                return match.group(0)

        rewritten_html = _HTML_ASSET_ATTR_RE.sub(replace_attr, html_text)
        if "/api/plugin/webui/bridge-sdk.js" not in rewritten_html:
            bridge_tag = f'<script src="{self._get_plugin_webui_bridge_sdk_url(extra_query_params)}"></script>'
            if "</body>" in rewritten_html:
                rewritten_html = rewritten_html.replace(
                    "</body>", f"{bridge_tag}</body>", 1
                )
            else:
                rewritten_html += bridge_tag
        return rewritten_html

    def _rewrite_plugin_webui_css(
        self,
        css_text: str,
        plugin_name: str,
        css_asset_path: str,
        extra_query_params: dict[str, str] | None = None,
    ) -> str:
        def replace_url(match: re.Match[str]) -> str:
            raw_url = match.group("url").strip()
            quote_char = match.group("quote") or ""
            try:
                rewritten_url = self._rewrite_relative_asset_url(
                    raw_url,
                    css_asset_path,
                    plugin_name,
                    extra_query_params=extra_query_params,
                )
                if not rewritten_url:
                    return match.group(0)
                return f"url({quote_char}{rewritten_url}{quote_char})"
            except ValueError:
                return match.group(0)

        return _CSS_URL_RE.sub(replace_url, css_text)

    def _rewrite_plugin_webui_js(
        self,
        js_text: str,
        plugin_name: str,
        js_asset_path: str,
        extra_query_params: dict[str, str] | None = None,
    ) -> str:
        def rewrite_specifier(raw_url: str) -> str:
            if not self._is_js_relative_module_specifier(raw_url):
                return raw_url
            if not self._is_rewritable_asset_url(raw_url):
                return raw_url
            rewritten = self._rewrite_relative_asset_url(
                raw_url,
                js_asset_path,
                plugin_name,
                extra_query_params=extra_query_params,
            )
            return rewritten or raw_url

        def replace_dynamic(match: re.Match[str]) -> str:
            raw_url = match.group("url")
            try:
                rewritten = rewrite_specifier(raw_url)
            except ValueError:
                return match.group(0)
            return (
                f"{match.group('prefix')}{match.group('quote')}{rewritten}"
                f"{match.group('quote')}{match.group('suffix')}"
            )

        def replace_from(match: re.Match[str]) -> str:
            raw_url = match.group("url")
            try:
                rewritten = rewrite_specifier(raw_url)
            except ValueError:
                return match.group(0)
            return f"{match.group('prefix')}{match.group('quote')}{rewritten}{match.group('quote')}"

        rewritten_js = _JS_DYNAMIC_IMPORT_RE.sub(replace_dynamic, js_text)
        rewritten_js = _JS_MODULE_FROM_RE.sub(replace_from, rewritten_js)

        def replace_side_effect(match: re.Match[str]) -> str:
            raw_url = match.group("url")
            if raw_url.startswith(("{", "*")):
                return match.group(0)
            try:
                rewritten = rewrite_specifier(raw_url)
            except ValueError:
                return match.group(0)
            return f"{match.group('prefix')}{match.group('quote')}{rewritten}{match.group('quote')}"

        return _JS_SIDE_EFFECT_IMPORT_RE.sub(replace_side_effect, rewritten_js)

    @staticmethod
    async def _read_plugin_webui_text(file_path: Path) -> str:
        async with aiofiles.open(file_path, encoding="utf-8") as file:
            return await file.read()

    @staticmethod
    async def _read_plugin_webui_binary(file_path: Path) -> bytes:
        async with aiofiles.open(file_path, mode="rb") as file:
            return await file.read()

    @staticmethod
    def _guess_plugin_webui_mime_type(file_path: Path) -> str:
        return mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"

    async def _serialize_plugin_webui(self, plugin: StarMetadata) -> dict | None:
        page = plugin.webui
        if not page:
            return None
        plugin_name = plugin.name.strip() if isinstance(plugin.name, str) else ""
        if not plugin_name:
            return None
        try:
            await self._resolve_plugin_webui_file(plugin, "")
        except (FileNotFoundError, ValueError):
            return None

        return {
            "display_name": page.display_name,
            "content_path": self._build_plugin_webui_content_path(plugin_name),
        }

    def _issue_plugin_webui_asset_token(self, plugin_name: str) -> str | None:
        jwt_secret = self.config.get("dashboard", {}).get("jwt_secret")
        if not isinstance(jwt_secret, str) or not jwt_secret.strip():
            return None

        username = getattr(g, "username", None)
        if not isinstance(username, str) or not username.strip():
            return None

        now = datetime.now(timezone.utc)
        payload = {
            "username": username,
            "token_type": _PLUGIN_WEBUI_ASSET_TOKEN_TYPE,
            "plugin_name": plugin_name,
            "iat": now,
            "exp": now + timedelta(seconds=_PLUGIN_WEBUI_ASSET_TOKEN_TTL_SECONDS),
        }
        return cast(str, jwt.encode(payload, jwt_secret, algorithm="HS256"))

    def _prepare_plugin_webui_query_params(
        self,
        plugin_name: str,
    ) -> dict[str, str] | None:
        asset_token = request.args.get("asset_token", "").strip()
        if not asset_token:
            asset_token = self._issue_plugin_webui_asset_token(plugin_name) or ""
        return {"asset_token": asset_token} if asset_token else None

    @staticmethod
    async def _plugin_webui_error_response(status_code: int, message: str):
        response = await make_response(message, status_code)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Type"] = "text/plain; charset=utf-8"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @staticmethod
    def _apply_plugin_webui_security_headers(response: QuartResponse) -> QuartResponse:
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Cross-Origin-Resource-Policy"] = "cross-origin"
        response.headers["Content-Security-Policy"] = (
            "frame-ancestors 'self'; object-src 'none'; base-uri 'self'"
        )
        return response

    async def _serve_plugin_webui_html_asset(
        self,
        file_path: Path,
        plugin_name: str,
        asset_path: str,
        extra_query_params: dict[str, str] | None,
    ):
        html_text = await self._read_plugin_webui_text(file_path)
        rewritten_html = self._rewrite_plugin_webui_html(
            html_text,
            plugin_name,
            asset_path,
            extra_query_params=extra_query_params,
        )
        response = cast(
            QuartResponse,
            await make_response(
                rewritten_html, {"Content-Type": "text/html; charset=utf-8"}
            ),
        )
        return self._apply_plugin_webui_security_headers(response)

    async def _serve_plugin_webui_css_asset(
        self,
        file_path: Path,
        plugin_name: str,
        asset_path: str,
        extra_query_params: dict[str, str] | None,
    ):
        css_text = await self._read_plugin_webui_text(file_path)
        rewritten_css = self._rewrite_plugin_webui_css(
            css_text,
            plugin_name,
            asset_path,
            extra_query_params=extra_query_params,
        )
        response = cast(
            QuartResponse,
            await make_response(
                rewritten_css, {"Content-Type": "text/css; charset=utf-8"}
            ),
        )
        return self._apply_plugin_webui_security_headers(response)

    async def _serve_plugin_webui_js_asset(
        self,
        file_path: Path,
        plugin_name: str,
        asset_path: str,
        extra_query_params: dict[str, str] | None,
    ):
        js_text = await self._read_plugin_webui_text(file_path)
        rewritten_js = self._rewrite_plugin_webui_js(
            js_text,
            plugin_name,
            asset_path,
            extra_query_params=extra_query_params,
        )
        response = cast(
            QuartResponse,
            await make_response(
                rewritten_js,
                {"Content-Type": "application/javascript; charset=utf-8"},
            ),
        )
        return self._apply_plugin_webui_security_headers(response)

    async def _serve_plugin_webui_static_asset(self, file_path: Path):
        raw_bytes = await self._read_plugin_webui_binary(file_path)
        response = cast(
            QuartResponse,
            await make_response(
                raw_bytes,
                {"Content-Type": self._guess_plugin_webui_mime_type(file_path)},
            ),
        )
        return self._apply_plugin_webui_security_headers(response)

    async def _serve_plugin_webui_content(
        self,
        plugin_name: str,
        asset_path: str,
    ):
        plugin = self._get_plugin_metadata_by_name(plugin_name)
        if not plugin:
            return await self._plugin_webui_error_response(404, "Plugin not found")
        if not plugin.activated:
            return await self._plugin_webui_error_response(403, "Plugin is disabled")

        if not plugin.webui:
            return await self._plugin_webui_error_response(
                404, "Plugin WebUI entry not found"
            )

        try:
            file_path = await self._resolve_plugin_webui_file(plugin, asset_path)
        except (FileNotFoundError, ValueError):
            return await self._plugin_webui_error_response(
                404, "Plugin WebUI asset not found"
            )

        extra_query_params = self._prepare_plugin_webui_query_params(plugin_name)
        served_asset_path = asset_path or plugin.webui.entry_file
        suffix = file_path.suffix.lower()
        handlers = {
            ".html": self._serve_plugin_webui_html_asset,
            ".css": self._serve_plugin_webui_css_asset,
            ".js": self._serve_plugin_webui_js_asset,
            ".mjs": self._serve_plugin_webui_js_asset,
        }
        handler = handlers.get(suffix)
        if handler:
            return await handler(
                file_path,
                plugin_name,
                served_asset_path,
                extra_query_params,
            )
        return await self._serve_plugin_webui_static_asset(file_path)

    async def check_plugin_compatibility(self):
        try:
            data = await request.get_json()
            version_spec = data.get("astrbot_version", "")
            is_valid, message = self.plugin_manager._validate_astrbot_version_specifier(
                version_spec
            )
            return (
                Response()
                .ok(
                    {
                        "compatible": is_valid,
                        "message": message,
                        "astrbot_version": version_spec,
                    }
                )
                .__dict__
            )
        except Exception as e:
            return Response().error(str(e)).__dict__

    async def reload_failed_plugins(self):
        if DEMO_MODE:
            return (
                Response()
                .error("You are not permitted to do this operation in demo mode")
                .__dict__
            )
        try:
            data = await request.get_json()
            dir_name = data.get("dir_name")  # 这里拿的是目录名，不是插件名

            if not dir_name:
                return Response().error("缺少插件目录名").__dict__

            # 调用 star_manager.py 中的函数
            # 注意：传入的是目录名
            success, err = await self.plugin_manager.reload_failed_plugin(dir_name)

            if success:
                return Response().ok(None, f"插件 {dir_name} 重载成功。").__dict__
            else:
                return Response().error(f"重载失败: {err}").__dict__

        except Exception as e:
            logger.error(f"/api/plugin/reload-failed: {traceback.format_exc()}")
            return Response().error(str(e)).__dict__

    async def reload_plugins(self):
        if DEMO_MODE:
            return (
                Response()
                .error("You are not permitted to do this operation in demo mode")
                .__dict__
            )

        data = await request.get_json()
        plugin_name = data.get("name", None)
        try:
            success, message = await self.plugin_manager.reload(plugin_name)
            if not success:
                return Response().error(message or "插件重载失败").__dict__
            return Response().ok(None, "重载成功。").__dict__
        except Exception as e:
            logger.error(f"/api/plugin/reload: {traceback.format_exc()}")
            return Response().error(str(e)).__dict__

    async def get_online_plugins(self):
        custom = request.args.get("custom_registry")
        force_refresh = request.args.get("force_refresh", "false").lower() == "true"

        # 构建注册表源信息
        source = self._build_registry_source(custom)

        # 如果不是强制刷新，先检查缓存是否有效
        cached_data = None
        if not force_refresh:
            # 先检查MD5是否匹配，如果匹配则使用缓存
            if await self._is_cache_valid(source):
                cached_data = self._load_plugin_cache(source.cache_file)
                if cached_data:
                    logger.debug("缓存MD5匹配，使用缓存的插件市场数据")
                    return Response().ok(cached_data).__dict__

        # 尝试获取远程数据
        remote_data = None
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        connector = aiohttp.TCPConnector(ssl=ssl_context)

        for url in source.urls:
            try:
                async with (
                    aiohttp.ClientSession(
                        trust_env=True,
                        connector=connector,
                    ) as session,
                    session.get(url) as response,
                ):
                    if response.status == 200:
                        try:
                            remote_data = await response.json()
                        except aiohttp.ContentTypeError:
                            remote_text = await response.text()
                            remote_data = json.loads(remote_text)

                        # 检查远程数据是否为空
                        if not remote_data or (
                            isinstance(remote_data, dict) and len(remote_data) == 0
                        ):
                            logger.warning(f"远程插件市场数据为空: {url}")
                            continue  # 继续尝试其他URL或使用缓存

                        logger.info(
                            f"成功获取远程插件市场数据，包含 {len(remote_data)} 个插件"
                        )
                        # 获取最新的MD5并保存到缓存
                        current_md5 = await self._fetch_remote_md5(source.md5_url)
                        self._save_plugin_cache(
                            source.cache_file,
                            remote_data,
                            current_md5,
                        )
                        return Response().ok(remote_data).__dict__
                    logger.error(f"请求 {url} 失败，状态码：{response.status}")
            except Exception as e:
                logger.error(f"请求 {url} 失败，错误：{e}")

        # 如果远程获取失败，尝试使用缓存数据
        if not cached_data:
            cached_data = self._load_plugin_cache(source.cache_file)

        if cached_data:
            logger.warning("远程插件市场数据获取失败，使用缓存数据")
            return Response().ok(cached_data, "使用缓存数据，可能不是最新版本").__dict__

        return Response().error("获取插件列表失败，且没有可用的缓存数据").__dict__

    def _build_registry_source(self, custom_url: str | None) -> RegistrySource:
        """构建注册表源信息"""
        data_dir = get_astrbot_data_path()
        if custom_url:
            # 对自定义URL生成一个安全的文件名
            url_hash = hashlib.md5(custom_url.encode()).hexdigest()[:8]
            cache_file = os.path.join(data_dir, f"plugins_custom_{url_hash}.json")

            # 更安全的后缀处理方式
            if custom_url.endswith(".json"):
                md5_url = custom_url[:-5] + "-md5.json"
            else:
                md5_url = custom_url + "-md5.json"

            urls = [custom_url]
        else:
            cache_file = os.path.join(data_dir, "plugins.json")
            md5_url = "https://api.soulter.top/astrbot/plugins-md5"
            urls = [
                "https://api.soulter.top/astrbot/plugins",
                "https://github.com/AstrBotDevs/AstrBot_Plugins_Collection/raw/refs/heads/main/plugin_cache_original.json",
            ]
        return RegistrySource(urls=urls, cache_file=cache_file, md5_url=md5_url)

    def _load_cached_md5(self, cache_file: str) -> str | None:
        """从缓存文件中加载MD5"""
        if not os.path.exists(cache_file):
            return None

        try:
            with open(cache_file, encoding="utf-8") as f:
                cache_data = json.load(f)
            return cache_data.get("md5")
        except Exception as e:
            logger.warning(f"加载缓存MD5失败: {e}")
            return None

    async def _fetch_remote_md5(self, md5_url: str | None) -> str | None:
        """获取远程MD5"""
        if not md5_url:
            return None

        try:
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            connector = aiohttp.TCPConnector(ssl=ssl_context)

            async with (
                aiohttp.ClientSession(
                    trust_env=True,
                    connector=connector,
                ) as session,
                session.get(md5_url) as response,
            ):
                if response.status == 200:
                    data = await response.json()
                    return data.get("md5", "")
        except Exception as e:
            logger.debug(f"获取远程MD5失败: {e}")
        return None

    async def _is_cache_valid(self, source: RegistrySource) -> bool:
        """检查缓存是否有效（基于MD5）"""
        try:
            cached_md5 = self._load_cached_md5(source.cache_file)
            if not cached_md5:
                logger.debug("缓存文件中没有MD5信息")
                return False

            remote_md5 = await self._fetch_remote_md5(source.md5_url)
            if remote_md5 is None:
                logger.warning("无法获取远程MD5，将使用缓存")
                return True  # 如果无法获取远程MD5，认为缓存有效

            is_valid = cached_md5 == remote_md5
            logger.debug(
                f"插件数据MD5: 本地={cached_md5}, 远程={remote_md5}, 有效={is_valid}",
            )
            return is_valid

        except Exception as e:
            logger.warning(f"检查缓存有效性失败: {e}")
            return False

    def _load_plugin_cache(self, cache_file: str):
        """加载本地缓存的插件市场数据"""
        try:
            if os.path.exists(cache_file):
                with open(cache_file, encoding="utf-8") as f:
                    cache_data = json.load(f)
                    # 检查缓存是否有效
                    if "data" in cache_data and "timestamp" in cache_data:
                        logger.debug(
                            f"加载缓存文件: {cache_file}, 缓存时间: {cache_data['timestamp']}",
                        )
                        return cache_data["data"]
        except Exception as e:
            logger.warning(f"加载插件市场缓存失败: {e}")
        return None

    def _save_plugin_cache(self, cache_file: str, data, md5: str | None = None) -> None:
        """保存插件市场数据到本地缓存"""
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(cache_file), exist_ok=True)

            cache_data = {
                "timestamp": datetime.now().isoformat(),
                "data": data,
                "md5": md5 or "",
            }

            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            logger.debug(f"插件市场数据已缓存到: {cache_file}, MD5: {md5}")
        except Exception as e:
            logger.warning(f"保存插件市场缓存失败: {e}")

    async def get_plugin_logo_token(self, logo_path: str):
        try:
            if token := self._logo_cache.get(logo_path):
                if not await file_token_service.check_token_expired(token):
                    return self._logo_cache[logo_path]
            token = await file_token_service.register_file(logo_path, timeout=300)
            self._logo_cache[logo_path] = token
            return token
        except Exception as e:
            logger.warning(f"获取插件 Logo 失败: {e}")
            return None

    def _resolve_plugin_dir(self, plugin) -> Path | None:
        if not plugin.root_dir_name:
            return None

        base_dir = Path(
            self.plugin_manager.reserved_plugin_path
            if plugin.reserved
            else self.plugin_manager.plugin_store_path
        )
        plugin_dir = base_dir / plugin.root_dir_name
        if not plugin_dir.is_dir():
            return None
        return plugin_dir

    def _get_plugin_installed_at(self, plugin) -> str | None:
        plugin_dir = self._resolve_plugin_dir(plugin)
        if plugin_dir is None:
            return None

        try:
            return datetime.fromtimestamp(
                plugin_dir.stat().st_mtime,
                timezone.utc,
            ).isoformat()
        except OSError as exc:
            logger.warning(f"获取插件安装时间失败 {plugin.name}: {exc!s}")
            return None

    async def get_plugins(self):
        _plugin_resp = []
        plugin_name = request.args.get("name")
        for plugin in self.plugin_manager.context.get_all_stars():
            if plugin_name and plugin.name != plugin_name:
                continue
            logo_url = None
            if plugin.logo_path:
                logo_url = await self.get_plugin_logo_token(plugin.logo_path)
            _t = {
                "name": plugin.name,
                "repo": "" if plugin.repo is None else plugin.repo,
                "author": plugin.author,
                "desc": plugin.desc,
                "version": plugin.version,
                "reserved": plugin.reserved,
                "activated": plugin.activated,
                "online_vesion": "",
                "handlers": await self.get_plugin_handlers_info(
                    plugin.star_handler_full_names,
                ),
                "display_name": plugin.display_name,
                "logo": f"/api/file/{logo_url}" if logo_url else None,
                "support_platforms": plugin.support_platforms,
                "astrbot_version": plugin.astrbot_version,
                "installed_at": self._get_plugin_installed_at(plugin),
                "webui": await self._serialize_plugin_webui(plugin),
            }
            # 检查是否为全空的幽灵插件
            if not any(
                [
                    plugin.name,
                    plugin.author,
                    plugin.desc,
                    plugin.version,
                    plugin.display_name,
                ]
            ):
                continue
            _plugin_resp.append(_t)
        return (
            Response()
            .ok(_plugin_resp, message=self.plugin_manager.failed_plugin_info)
            .__dict__
        )

    async def get_failed_plugins(self):
        """专门获取加载失败的插件列表(字典格式)"""
        return Response().ok(self.plugin_manager.failed_plugin_dict).__dict__

    async def get_plugin_handlers_info(self, handler_full_names: list[str]):
        """解析插件行为"""
        handlers = []

        for handler_full_name in handler_full_names:
            info = {}
            handler = star_handlers_registry.star_handlers_map.get(
                handler_full_name,
                None,
            )
            if handler is None:
                continue
            info["event_type"] = handler.event_type.name
            info["event_type_h"] = self.translated_event_type.get(
                handler.event_type,
                handler.event_type.name,
            )
            info["handler_full_name"] = handler.handler_full_name
            info["desc"] = handler.desc
            info["handler_name"] = handler.handler_name

            if handler.event_type == EventType.AdapterMessageEvent:
                # 处理平台适配器消息事件
                has_admin = False
                for filter in (
                    handler.event_filters
                ):  # 正常handler就只有 1~2 个 filter，因此这里时间复杂度不会太高
                    if isinstance(filter, CommandFilter):
                        info["type"] = "指令"
                        info["cmd"] = (
                            f"{filter.parent_command_names[0]} {filter.command_name}"
                        )
                        info["cmd"] = info["cmd"].strip()
                    elif isinstance(filter, CommandGroupFilter):
                        info["type"] = "指令组"
                        info["cmd"] = filter.get_complete_command_names()[0]
                        info["cmd"] = info["cmd"].strip()
                        info["sub_command"] = filter.print_cmd_tree(
                            filter.sub_command_filters,
                        )
                    elif isinstance(filter, RegexFilter):
                        info["type"] = "正则匹配"
                        info["cmd"] = filter.regex_str
                    elif isinstance(filter, PermissionTypeFilter):
                        has_admin = True
                info["has_admin"] = has_admin
                if "cmd" not in info:
                    info["cmd"] = "未知"
                if "type" not in info:
                    info["type"] = "事件监听器"
            else:
                info["cmd"] = "自动触发"
                info["type"] = "无"

            if not info["desc"]:
                info["desc"] = "无描述"

            handlers.append(info)

        return handlers

    async def install_plugin(self):
        if DEMO_MODE:
            return (
                Response()
                .error("You are not permitted to do this operation in demo mode")
                .__dict__
            )

        post_data = await request.get_json()
        repo_url = post_data["url"]
        ignore_version_check = bool(post_data.get("ignore_version_check", False))

        proxy: str = post_data.get("proxy", None)
        if proxy:
            proxy = proxy.removesuffix("/")

        try:
            logger.info(f"正在安装插件 {repo_url}")
            plugin_info = await self.plugin_manager.install_plugin(
                repo_url,
                proxy,
                ignore_version_check=ignore_version_check,
            )
            # self.core_lifecycle.restart()
            logger.info(f"安装插件 {repo_url} 成功。")
            return Response().ok(plugin_info, "安装成功。").__dict__
        except PluginVersionIncompatibleError as e:
            return {
                "status": "warning",
                "message": str(e),
                "data": {
                    "warning_type": "astrbot_version_incompatible",
                    "can_ignore": True,
                },
            }
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(str(e)).__dict__

    async def install_plugin_upload(self):
        if DEMO_MODE:
            return (
                Response()
                .error("You are not permitted to do this operation in demo mode")
                .__dict__
            )

        try:
            file = await request.files
            file = file["file"]
            form_data = await request.form
            ignore_version_check = (
                str(form_data.get("ignore_version_check", "false")).lower() == "true"
            )
            logger.info(f"正在安装用户上传的插件 {file.filename}")
            file_path = os.path.join(
                get_astrbot_temp_path(),
                f"plugin_upload_{file.filename}",
            )
            await file.save(file_path)
            plugin_info = await self.plugin_manager.install_plugin_from_file(
                file_path,
                ignore_version_check=ignore_version_check,
            )
            # self.core_lifecycle.restart()
            logger.info(f"安装插件 {file.filename} 成功")
            return Response().ok(plugin_info, "安装成功。").__dict__
        except PluginVersionIncompatibleError as e:
            return {
                "status": "warning",
                "message": str(e),
                "data": {
                    "warning_type": "astrbot_version_incompatible",
                    "can_ignore": True,
                },
            }
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(str(e)).__dict__

    async def uninstall_plugin(self):
        if DEMO_MODE:
            return (
                Response()
                .error("You are not permitted to do this operation in demo mode")
                .__dict__
            )

        post_data = await request.get_json()
        plugin_name = post_data["name"]
        delete_config = post_data.get("delete_config", False)
        delete_data = post_data.get("delete_data", False)
        try:
            logger.info(f"正在卸载插件 {plugin_name}")
            await self.plugin_manager.uninstall_plugin(
                plugin_name,
                delete_config=delete_config,
                delete_data=delete_data,
            )
            logger.info(f"卸载插件 {plugin_name} 成功")
            return Response().ok(None, "卸载成功").__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(str(e)).__dict__

    async def uninstall_failed_plugin(self):
        if DEMO_MODE:
            return (
                Response()
                .error("You are not permitted to do this operation in demo mode")
                .__dict__
            )

        post_data = await request.get_json()
        dir_name = post_data.get("dir_name", "")
        delete_config = post_data.get("delete_config", False)
        delete_data = post_data.get("delete_data", False)
        if not dir_name:
            return Response().error("缺少失败插件目录名").__dict__

        try:
            logger.info(f"正在卸载失败插件 {dir_name}")
            await self.plugin_manager.uninstall_failed_plugin(
                dir_name,
                delete_config=delete_config,
                delete_data=delete_data,
            )
            logger.info(f"卸载失败插件 {dir_name} 成功")
            return Response().ok(None, "卸载成功").__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(str(e)).__dict__

    async def update_plugin(self):
        if DEMO_MODE:
            return (
                Response()
                .error("You are not permitted to do this operation in demo mode")
                .__dict__
            )

        post_data = await request.get_json()
        plugin_name = post_data["name"]
        proxy: str = post_data.get("proxy", None)
        try:
            logger.info(f"正在更新插件 {plugin_name}")
            await self.plugin_manager.update_plugin(plugin_name, proxy)
            # self.core_lifecycle.restart()
            await self.plugin_manager.reload(plugin_name)
            logger.info(f"更新插件 {plugin_name} 成功。")
            return Response().ok(None, "更新成功。").__dict__
        except Exception as e:
            logger.error(f"/api/plugin/update: {traceback.format_exc()}")
            return Response().error(str(e)).__dict__

    async def update_all_plugins(self):
        if DEMO_MODE:
            return (
                Response()
                .error("You are not permitted to do this operation in demo mode")
                .__dict__
            )

        post_data = await request.get_json()
        plugin_names: list[str] = post_data.get("names") or []
        proxy: str = post_data.get("proxy", "")

        if not isinstance(plugin_names, list) or not plugin_names:
            return Response().error("插件列表不能为空").__dict__

        results = []
        sem = asyncio.Semaphore(PLUGIN_UPDATE_CONCURRENCY)

        async def _update_one(name: str):
            async with sem:
                try:
                    logger.info(f"批量更新插件 {name}")
                    await self.plugin_manager.update_plugin(name, proxy)
                    return {"name": name, "status": "ok", "message": "更新成功"}
                except Exception as e:
                    logger.error(
                        f"/api/plugin/update-all: 更新插件 {name} 失败: {traceback.format_exc()}",
                    )
                    return {"name": name, "status": "error", "message": str(e)}

        raw_results = await asyncio.gather(
            *(_update_one(name) for name in plugin_names),
            return_exceptions=True,
        )
        for name, result in zip(plugin_names, raw_results):
            if isinstance(result, asyncio.CancelledError):
                raise result
            if isinstance(result, BaseException):
                results.append(
                    {"name": name, "status": "error", "message": str(result)}
                )
            else:
                results.append(result)

        failed = [r for r in results if r["status"] == "error"]
        message = (
            "批量更新完成，全部成功。"
            if not failed
            else f"批量更新完成，其中 {len(failed)}/{len(results)} 个插件失败。"
        )

        return Response().ok({"results": results}, message).__dict__

    async def off_plugin(self):
        if DEMO_MODE:
            return (
                Response()
                .error("You are not permitted to do this operation in demo mode")
                .__dict__
            )

        post_data = await request.get_json()
        plugin_name = post_data["name"]
        try:
            await self.plugin_manager.turn_off_plugin(plugin_name)
            logger.info(f"停用插件 {plugin_name} 。")
            return Response().ok(None, "停用成功。").__dict__
        except Exception as e:
            logger.error(f"/api/plugin/off: {traceback.format_exc()}")
            return Response().error(str(e)).__dict__

    async def on_plugin(self):
        if DEMO_MODE:
            return (
                Response()
                .error("You are not permitted to do this operation in demo mode")
                .__dict__
            )

        post_data = await request.get_json()
        plugin_name = post_data["name"]
        try:
            await self.plugin_manager.turn_on_plugin(plugin_name)
            logger.info(f"启用插件 {plugin_name} 。")
            return Response().ok(None, "启用成功。").__dict__
        except Exception as e:
            logger.error(f"/api/plugin/on: {traceback.format_exc()}")
            return Response().error(str(e)).__dict__

    async def get_plugin_readme(self):
        plugin_name = request.args.get("name")
        logger.debug(f"正在获取插件 {plugin_name} 的README文件内容")

        if not plugin_name:
            logger.warning("插件名称为空")
            return Response().error("插件名称不能为空").__dict__

        plugin_obj = None
        for plugin in self.plugin_manager.context.get_all_stars():
            if plugin.name == plugin_name:
                plugin_obj = plugin
                break

        if not plugin_obj:
            logger.warning(f"插件 {plugin_name} 不存在")
            return Response().error(f"插件 {plugin_name} 不存在").__dict__

        if not plugin_obj.root_dir_name:
            logger.warning(f"插件 {plugin_name} 目录不存在")
            return Response().error(f"插件 {plugin_name} 目录不存在").__dict__

        if plugin_obj.reserved:
            plugin_dir = os.path.join(
                self.plugin_manager.reserved_plugin_path,
                plugin_obj.root_dir_name,
            )
        else:
            plugin_dir = os.path.join(
                self.plugin_manager.plugin_store_path,
                plugin_obj.root_dir_name,
            )

        if not os.path.isdir(plugin_dir):
            logger.warning(f"无法找到插件目录: {plugin_dir}")
            return Response().error(f"无法找到插件 {plugin_name} 的目录").__dict__

        readme_path = os.path.join(plugin_dir, "README.md")

        if not os.path.isfile(readme_path):
            logger.warning(f"插件 {plugin_name} 没有README文件")
            return Response().error(f"插件 {plugin_name} 没有README文件").__dict__

        try:
            with open(readme_path, encoding="utf-8") as f:
                readme_content = f.read()

            return (
                Response()
                .ok({"content": readme_content}, "成功获取README内容")
                .__dict__
            )
        except Exception as e:
            logger.error(f"/api/plugin/readme: {traceback.format_exc()}")
            return Response().error(f"读取README文件失败: {e!s}").__dict__

    async def get_plugin_changelog(self):
        """获取插件更新日志

        读取插件目录下的 CHANGELOG.md 文件内容。
        """
        plugin_name = request.args.get("name")
        logger.debug(f"正在获取插件 {plugin_name} 的更新日志")

        if not plugin_name:
            logger.warning("插件名称为空")
            return Response().error("插件名称不能为空").__dict__

        # 查找插件
        plugin_obj = None
        for plugin in self.plugin_manager.context.get_all_stars():
            if plugin.name == plugin_name:
                plugin_obj = plugin
                break

        if not plugin_obj:
            logger.warning(f"插件 {plugin_name} 不存在")
            return Response().error(f"插件 {plugin_name} 不存在").__dict__

        if not plugin_obj.root_dir_name:
            logger.warning(f"插件 {plugin_name} 目录不存在")
            return Response().error(f"插件 {plugin_name} 目录不存在").__dict__

        if plugin_obj.reserved:
            plugin_dir = os.path.join(
                self.plugin_manager.reserved_plugin_path,
                plugin_obj.root_dir_name,
            )
        else:
            plugin_dir = os.path.join(
                self.plugin_manager.plugin_store_path,
                plugin_obj.root_dir_name,
            )

        if not os.path.isdir(plugin_dir):
            logger.warning(f"无法找到插件目录: {plugin_dir}")
            return Response().error(f"无法找到插件 {plugin_name} 的目录").__dict__

        # 尝试多种可能的文件名
        changelog_names = ["CHANGELOG.md", "changelog.md", "CHANGELOG", "changelog"]
        for name in changelog_names:
            changelog_path = os.path.join(plugin_dir, name)
            if os.path.isfile(changelog_path):
                try:
                    with open(changelog_path, encoding="utf-8") as f:
                        changelog_content = f.read()
                    return (
                        Response()
                        .ok({"content": changelog_content}, "成功获取更新日志")
                        .__dict__
                    )
                except Exception as e:
                    logger.error(f"/api/plugin/changelog: {traceback.format_exc()}")
                    return Response().error(f"读取更新日志失败: {e!s}").__dict__

        # 没有找到 changelog 文件，返回 ok 但 content 为 null
        logger.warning(f"插件 {plugin_name} 没有更新日志文件")
        return Response().ok({"content": None}, "该插件没有更新日志文件").__dict__

    async def get_custom_source(self):
        """获取自定义插件源"""
        sources = await sp.global_get("custom_plugin_sources", [])
        return Response().ok(sources).__dict__

    async def save_custom_source(self):
        """保存自定义插件源"""
        try:
            data = await request.get_json()
            sources = data.get("sources", [])
            if not isinstance(sources, list):
                return Response().error("sources fields must be a list").__dict__

            await sp.global_put("custom_plugin_sources", sources)
            return Response().ok(None, "保存成功").__dict__
        except Exception as e:
            logger.error(f"/api/plugin/source/save: {traceback.format_exc()}")
            return Response().error(str(e)).__dict__
