from __future__ import annotations

import json
import mimetypes
import os
import posixpath
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

import aiofiles
import jwt
from aiofiles import ospath as aio_ospath

from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.star.star import StarMetadata
from astrbot.core.star.star_manager import PluginManager

PLUGIN_PAGE_ASSET_TOKEN_TYPE = "plugin_page_asset"
PLUGIN_PAGE_ASSET_TOKEN_TTL_SECONDS = 60
PLUGIN_PAGE_ROOT_DIR_NAME = "pages"
PLUGIN_PAGE_ENTRY_FILE_NAME = "index.html"
PLUGIN_PAGE_BRIDGE_FILE = (
    Path(__file__).resolve().parent.parent / "plugin_page_bridge.js"
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


@dataclass
class PluginPage:
    name: str
    title: str
    entry_file: str = PLUGIN_PAGE_ENTRY_FILE_NAME


@dataclass
class PluginPageContentPayload:
    content: str | bytes
    content_type: str


class PluginPageServiceError(Exception):
    def __init__(
        self,
        message: str,
        status_code: int = 400,
        *,
        public_message: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.public_message = public_message or message


class PluginPageService:
    def __init__(
        self,
        plugin_manager: PluginManager,
        core_lifecycle: AstrBotCoreLifecycle | None = None,
        config: AstrBotConfig | None = None,
    ) -> None:
        self.plugin_manager = plugin_manager
        self.config = config or (
            core_lifecycle.astrbot_config if core_lifecycle is not None else None
        )
        self.bridge_file = PLUGIN_PAGE_BRIDGE_FILE

    def _jwt_secret(self) -> str | None:
        if self.config is None:
            return None
        return self.config.get("dashboard", {}).get("jwt_secret")

    def get_plugin_metadata_by_name(self, plugin_name: str) -> StarMetadata | None:
        for plugin in self.plugin_manager.context.get_all_stars():
            if plugin.name == plugin_name:
                return plugin
        return None

    @staticmethod
    def get_by_path(source: dict | None, key: str):
        if not isinstance(source, dict) or not key:
            return None
        current = source
        for part in key.split("."):
            if not isinstance(current, dict) or part not in current:
                return None
            current = current[part]
        return current

    @staticmethod
    def apply_theme_to_html(html: str, theme: str) -> str:
        def _replace_html_tag(m: re.Match) -> str:
            attrs = m.group(1) or ""
            attrs = re.sub(
                r'\s+data-theme\s*=\s*["\'][^"\']*["\']',
                "",
                attrs,
                flags=re.IGNORECASE,
            )
            return f'<html{attrs} data-theme="{theme}">'

        html = re.sub(
            r"<html(\b[^>]*)>",
            _replace_html_tag,
            html,
            count=1,
            flags=re.IGNORECASE,
        )

        meta_tag = f'<meta name="color-scheme" content="{theme}">'
        html = re.sub(
            r'<meta\s[^>]*name\s*=\s*["\']color-scheme["\'][^>]*>',
            "",
            html,
            flags=re.IGNORECASE,
        )

        head_match = re.search(r"<head\b[^>]*>", html, re.IGNORECASE)
        if head_match:
            html = html.replace(
                head_match.group(0), f"{head_match.group(0)}{meta_tag}", 1
            )
        else:
            html = re.sub(
                r"(<html\b[^>]*>)",
                rf"\1<head>{meta_tag}</head>",
                html,
                count=1,
                flags=re.IGNORECASE,
            )
        return html

    def build_initial_context(
        self,
        *,
        asset_token: str,
        jwt_secret: str | None = None,
        locale: str,
        theme: str | None,
    ) -> dict | None:
        if not asset_token:
            return None
        jwt_secret = jwt_secret or self._jwt_secret()
        if not isinstance(jwt_secret, str) or not jwt_secret.strip():
            return None

        try:
            payload = jwt.decode(asset_token, jwt_secret, algorithms=["HS256"])
        except jwt.InvalidTokenError:
            return None
        if payload.get("token_type") != PLUGIN_PAGE_ASSET_TOKEN_TYPE:
            return None

        plugin_name = payload.get("plugin_name")
        page_name = payload.get("page_name")
        if not isinstance(plugin_name, str) or not isinstance(page_name, str):
            return None

        plugin = self.get_plugin_metadata_by_name(plugin_name)
        if not plugin:
            return None

        resolved_locale = locale
        token_locale = payload.get("locale")
        if isinstance(token_locale, str):
            resolved_locale = token_locale
        plugin_i18n = plugin.i18n or {}
        try:
            plugin_root = self.get_plugin_root_dir(plugin)
            fresh_i18n = PluginManager._load_plugin_i18n(str(plugin_root))
            if fresh_i18n:
                plugin_i18n = fresh_i18n
        except (OSError, ValueError):
            pass

        locale_data = plugin_i18n.get(resolved_locale)
        display_name = (
            self.get_by_path(locale_data, "metadata.display_name")
            or plugin.display_name
            or plugin.name
        )
        page_title = (
            self.get_by_path(locale_data, f"pages.{page_name}.title") or page_name
        )

        return {
            "pluginName": plugin.name,
            "displayName": display_name,
            "pageName": page_name,
            "pageTitle": page_title,
            "locale": resolved_locale,
            "i18n": plugin_i18n,
            "isDark": theme == "dark",
        }

    async def get_plugin_page_entry_config(
        self,
        *,
        plugin_name: str | None,
        page_name: str | None,
        jwt_secret: str | None = None,
        username: str | None,
        locale: str,
    ) -> dict:
        if not plugin_name:
            raise PluginPageServiceError("缺少插件名")
        if not page_name:
            raise PluginPageServiceError("缺少 Page 名称")

        plugin = self.get_plugin_metadata_by_name(plugin_name)
        if not plugin:
            raise PluginPageServiceError("插件不存在")
        if not plugin.activated:
            raise PluginPageServiceError("插件未启用")

        page = await self.serialize_plugin_page_for_request(
            plugin,
            page_name,
            include_content_path=True,
            jwt_secret=jwt_secret,
            username=username,
            locale=locale,
        )
        if not page:
            raise PluginPageServiceError("插件 Page 不存在")
        return page

    async def serialize_plugin_page_for_request(
        self,
        plugin: StarMetadata,
        page_name: str,
        *,
        include_content_path: bool = False,
        jwt_secret: str | None = None,
        username: str | None,
        locale: str,
    ) -> dict | None:
        asset_token = ""
        if include_content_path:
            plugin_name = plugin.name.strip() if isinstance(plugin.name, str) else ""
            asset_token = (
                self.issue_plugin_page_asset_token(
                    plugin_name=plugin_name,
                    page_name=page_name,
                    jwt_secret=jwt_secret or self._jwt_secret(),
                    username=username,
                    locale=locale,
                )
                or ""
            )
        return await self.serialize_plugin_page(
            plugin,
            page_name,
            include_content_path=include_content_path,
            asset_token=asset_token,
        )

    def prepare_plugin_page_query_params(
        self,
        plugin_name: str,
        page_name: str,
        *,
        asset_token: str,
        jwt_secret: str | None = None,
        username: str | None,
        locale: str,
        theme: str | None,
    ) -> dict[str, str] | None:
        if not asset_token:
            asset_token = (
                self.issue_plugin_page_asset_token(
                    plugin_name=plugin_name,
                    page_name=page_name,
                    jwt_secret=jwt_secret or self._jwt_secret(),
                    username=username,
                    locale=locale,
                )
                or ""
            )

        if not asset_token and not theme:
            return None

        params: dict[str, str] = {}
        if asset_token:
            params["asset_token"] = asset_token
        if theme:
            params["theme"] = theme
        return params

    async def serve_bridge_sdk(
        self,
        *,
        asset_token: str,
        jwt_secret: str | None = None,
        locale: str,
        theme: str | None,
    ) -> PluginPageContentPayload:
        if not self.bridge_file.is_file():
            raise PluginPageServiceError(
                "Plugin Page bridge SDK not found",
                status_code=404,
            )
        bridge_js = await self.read_plugin_page_text(self.bridge_file)
        initial_context = self.build_initial_context(
            asset_token=asset_token,
            jwt_secret=jwt_secret,
            locale=locale,
            theme=theme,
        )
        if initial_context:
            context_json = json.dumps(initial_context, ensure_ascii=False)
            bridge_js += (
                f"\n;window.AstrBotPluginPage?.__setInitialContext({context_json});\n"
            )
        return PluginPageContentPayload(
            content=bridge_js,
            content_type="application/javascript; charset=utf-8",
        )

    async def serve_page_content(
        self,
        *,
        plugin_name: str,
        page_name: str,
        asset_path: str,
        asset_token: str,
        jwt_secret: str | None = None,
        username: str | None,
        locale: str,
        theme: str | None,
    ) -> PluginPageContentPayload:
        plugin = self.get_plugin_metadata_by_name(plugin_name)
        if not plugin:
            raise PluginPageServiceError("Plugin not found", status_code=404)
        if not plugin.activated:
            raise PluginPageServiceError("Plugin is disabled", status_code=403)

        try:
            page = await self.get_plugin_page(plugin, page_name)
            file_path = await self.resolve_plugin_page_file(
                plugin,
                page.name,
                asset_path,
            )
        except (FileNotFoundError, ValueError) as exc:
            raise PluginPageServiceError(
                "Plugin Page asset not found",
                status_code=404,
            ) from exc

        extra_query_params = self.prepare_plugin_page_query_params(
            plugin_name,
            page.name,
            asset_token=asset_token,
            jwt_secret=jwt_secret,
            username=username,
            locale=locale,
            theme=theme,
        )
        served_asset_path = asset_path or page.entry_file
        suffix = file_path.suffix.lower()
        if suffix == ".html":
            html_text = await self.read_plugin_page_text(file_path)
            return PluginPageContentPayload(
                content=self.rewrite_plugin_page_html(
                    html_text,
                    plugin_name,
                    page.name,
                    served_asset_path,
                    theme=theme,
                    extra_query_params=extra_query_params,
                ),
                content_type="text/html; charset=utf-8",
            )
        if suffix == ".css":
            css_text = await self.read_plugin_page_text(file_path)
            return PluginPageContentPayload(
                content=self.rewrite_plugin_page_css(
                    css_text,
                    plugin_name,
                    page.name,
                    served_asset_path,
                    extra_query_params=extra_query_params,
                ),
                content_type="text/css; charset=utf-8",
            )
        if suffix in {".js", ".mjs"}:
            js_text = await self.read_plugin_page_text(file_path)
            return PluginPageContentPayload(
                content=self.rewrite_plugin_page_js(
                    js_text,
                    plugin_name,
                    page.name,
                    served_asset_path,
                    extra_query_params=extra_query_params,
                ),
                content_type="application/javascript; charset=utf-8",
            )
        return PluginPageContentPayload(
            content=await self.read_plugin_page_binary(file_path),
            content_type=self.guess_plugin_page_mime_type(file_path),
        )

    @staticmethod
    def build_security_headers() -> dict[str, str]:
        headers = {
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
            "Cross-Origin-Resource-Policy": "cross-origin",
            "Access-Control-Allow-Origin": "*",
        }

        csp = "object-src 'none'; base-uri 'self'"
        if os.environ.get("ASTRBOT_LAUNCHER") not in ("1", "true"):
            headers["X-Frame-Options"] = "SAMEORIGIN"
            csp = f"frame-ancestors 'self'; {csp}"
        headers["Content-Security-Policy"] = csp
        return headers

    @staticmethod
    def normalize_plugin_page_path(
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
            raise ValueError("Invalid plugin Page asset path")
        if (
            normalized.startswith("../")
            or normalized == ".."
            or normalized.startswith("/")
        ):
            raise ValueError("Invalid plugin Page asset path")
        return normalized

    @staticmethod
    def normalize_plugin_page_name(raw_name: str) -> str:
        page_name = raw_name.strip()
        if not page_name:
            raise ValueError("Invalid plugin Page name")
        normalized = posixpath.normpath(page_name.replace("\\", "/"))
        if (
            normalized != page_name
            or normalized in {".", ".."}
            or normalized.startswith(".")
            or "/" in page_name
            or "\\" in page_name
        ):
            raise ValueError("Invalid plugin Page name")
        return page_name

    def get_plugin_root_dir(self, plugin: StarMetadata) -> Path:
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

    async def resolve_plugin_pages_root(self, plugin: StarMetadata) -> Path:
        plugin_root = self.get_plugin_root_dir(plugin)
        pages_root = (plugin_root / PLUGIN_PAGE_ROOT_DIR_NAME).resolve(strict=False)
        pages_root.relative_to(plugin_root)
        if pages_root == plugin_root:
            raise FileNotFoundError("Plugin Pages root directory is invalid")
        if not await aio_ospath.isdir(str(pages_root)):
            raise FileNotFoundError("Plugin Pages root directory does not exist")
        return pages_root

    async def discover_plugin_pages(self, plugin: StarMetadata) -> list[PluginPage]:
        try:
            pages_root = await self.resolve_plugin_pages_root(plugin)
        except (FileNotFoundError, ValueError):
            return []

        pages: list[PluginPage] = []
        try:
            page_dirs = sorted(
                (item for item in pages_root.iterdir() if item.is_dir()),
                key=lambda item: item.name.lower(),
            )
        except OSError:
            return []

        for page_dir in page_dirs:
            try:
                page_name = self.normalize_plugin_page_name(page_dir.name)
            except ValueError:
                continue
            entry_path = page_dir / PLUGIN_PAGE_ENTRY_FILE_NAME
            if not await aio_ospath.isfile(str(entry_path)):
                continue
            pages.append(
                PluginPage(
                    name=page_name,
                    title=page_name,
                    entry_file=PLUGIN_PAGE_ENTRY_FILE_NAME,
                )
            )
        return pages

    async def get_plugin_page(
        self,
        plugin: StarMetadata,
        page_name: str,
    ) -> PluginPage:
        normalized_name = self.normalize_plugin_page_name(page_name)
        for page in await self.discover_plugin_pages(plugin):
            if page.name == normalized_name:
                return page
        raise FileNotFoundError("Plugin Page entry not found")

    async def resolve_plugin_page_root(
        self,
        plugin: StarMetadata,
        page_name: str,
    ) -> Path:
        normalized_name = self.normalize_plugin_page_name(page_name)
        pages_root = await self.resolve_plugin_pages_root(plugin)
        page_root = (pages_root / normalized_name).resolve(strict=False)
        page_root.relative_to(pages_root)
        if not await aio_ospath.isdir(str(page_root)):
            raise FileNotFoundError("Plugin Page root directory does not exist")
        return page_root

    async def resolve_plugin_page_file(
        self,
        plugin: StarMetadata,
        page_name: str,
        asset_path: str,
    ) -> Path:
        page = await self.get_plugin_page(plugin, page_name)
        page_root = await self.resolve_plugin_page_root(plugin, page.name)
        target_name = (
            self.normalize_plugin_page_path(asset_path, allow_empty=True)
            or page.entry_file
        )
        target_path = (page_root / target_name).resolve(strict=False)
        target_path.relative_to(page_root)
        if not await aio_ospath.isfile(str(target_path)):
            raise FileNotFoundError("Plugin Page asset not found")
        return target_path

    @staticmethod
    def is_rewritable_asset_url(raw_url: str) -> bool:
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
    def resolve_referenced_asset_path(
        base_asset_path: str,
        referenced_url: str,
    ) -> str:
        parts = urlsplit(referenced_url)
        referenced_path = parts.path.strip()
        if not referenced_path:
            raise ValueError("Plugin Page referenced asset path is empty")
        base_dir = posixpath.dirname(base_asset_path) if base_asset_path else ""
        normalized = PluginPageService.normalize_plugin_page_path(
            referenced_path,
            base_dir=base_dir,
        )
        if not normalized:
            raise ValueError("Plugin Page referenced asset path is invalid")
        return normalized

    def build_plugin_page_asset_url(
        self,
        plugin_name: str,
        page_name: str,
        asset_path: str,
        original_query: str = "",
        original_fragment: str = "",
        extra_query_params: dict[str, str] | None = None,
    ) -> str:
        path = self.build_plugin_page_content_path(plugin_name, page_name, asset_path)
        query_dict = dict(parse_qsl(original_query, keep_blank_values=True))
        if extra_query_params:
            for key, value in extra_query_params.items():
                if value:
                    query_dict[key] = value
        query = urlencode(query_dict)
        return urlunsplit(("", "", path, query, original_fragment))

    @staticmethod
    def build_plugin_page_content_path(
        plugin_name: str,
        page_name: str,
        asset_path: str = "",
    ) -> str:
        encoded_plugin_name = quote(plugin_name, safe="")
        encoded_page_name = quote(
            PluginPageService.normalize_plugin_page_name(page_name),
            safe="",
        )
        if not asset_path:
            return (
                f"/api/plugin/page/content/{encoded_plugin_name}/{encoded_page_name}/"
            )
        safe_asset_path = PluginPageService.normalize_plugin_page_path(
            asset_path,
            allow_empty=True,
        )
        encoded_path = "/".join(
            quote(part, safe="") for part in safe_asset_path.split("/")
        )
        return (
            f"/api/plugin/page/content/{encoded_plugin_name}/"
            f"{encoded_page_name}/{encoded_path}"
        )

    @staticmethod
    def get_plugin_page_bridge_sdk_url(
        extra_query_params: dict[str, str] | None = None,
    ) -> str:
        query = urlencode(extra_query_params or {})
        return urlunsplit(("", "", "/api/plugin/page/bridge-sdk.js", query, ""))

    @staticmethod
    def is_js_relative_module_specifier(raw_url: str) -> bool:
        value = raw_url.strip()
        return value.startswith(("./", "../", "/"))

    def rewrite_relative_asset_url(
        self,
        raw_url: str,
        base_asset_path: str,
        plugin_name: str,
        page_name: str,
        extra_query_params: dict[str, str] | None = None,
    ) -> str | None:
        candidate = raw_url.strip()
        if not self.is_rewritable_asset_url(candidate):
            return None
        parts = urlsplit(candidate)
        asset_path = self.resolve_referenced_asset_path(base_asset_path, candidate)
        return self.build_plugin_page_asset_url(
            plugin_name,
            page_name,
            asset_path,
            original_query=parts.query,
            original_fragment=parts.fragment,
            extra_query_params=extra_query_params,
        )

    def rewrite_plugin_page_html(
        self,
        html_text: str,
        plugin_name: str,
        page_name: str,
        entry_asset_path: str,
        *,
        theme: str | None,
        extra_query_params: dict[str, str] | None = None,
    ) -> str:
        def replace_attr(match: re.Match[str]) -> str:
            raw_url = match.group("url")
            attr = match.group("attr")
            quote_char = match.group("quote")

            if raw_url.strip() == "/api/plugin/page/bridge-sdk.js":
                url = self.get_plugin_page_bridge_sdk_url(extra_query_params)
                return f"{attr}={quote_char}{url}{quote_char}"

            if not self.is_rewritable_asset_url(raw_url):
                return match.group(0)

            try:
                rewritten_url = self.rewrite_relative_asset_url(
                    raw_url,
                    entry_asset_path,
                    plugin_name,
                    page_name,
                    extra_query_params=extra_query_params,
                )
                if not rewritten_url:
                    return match.group(0)
                return f"{attr}={quote_char}{rewritten_url}{quote_char}"
            except ValueError:
                return match.group(0)

        rewritten_html = _HTML_ASSET_ATTR_RE.sub(replace_attr, html_text)
        if theme:
            rewritten_html = self.apply_theme_to_html(rewritten_html, theme)
        if "/api/plugin/page/bridge-sdk.js" not in rewritten_html:
            bridge_tag = f'<script src="{self.get_plugin_page_bridge_sdk_url(extra_query_params)}"></script>'
            if "</body>" in rewritten_html:
                rewritten_html = rewritten_html.replace(
                    "</body>", f"{bridge_tag}</body>", 1
                )
            else:
                rewritten_html += bridge_tag
        return rewritten_html

    def rewrite_plugin_page_css(
        self,
        css_text: str,
        plugin_name: str,
        page_name: str,
        css_asset_path: str,
        extra_query_params: dict[str, str] | None = None,
    ) -> str:
        def replace_url(match: re.Match[str]) -> str:
            raw_url = match.group("url").strip()
            quote_char = match.group("quote") or ""
            try:
                rewritten_url = self.rewrite_relative_asset_url(
                    raw_url,
                    css_asset_path,
                    plugin_name,
                    page_name,
                    extra_query_params=extra_query_params,
                )
                if not rewritten_url:
                    return match.group(0)
                return f"url({quote_char}{rewritten_url}{quote_char})"
            except ValueError:
                return match.group(0)

        return _CSS_URL_RE.sub(replace_url, css_text)

    def rewrite_plugin_page_js(
        self,
        js_text: str,
        plugin_name: str,
        page_name: str,
        js_asset_path: str,
        extra_query_params: dict[str, str] | None = None,
    ) -> str:
        def rewrite_specifier(raw_url: str) -> str:
            if not self.is_js_relative_module_specifier(raw_url):
                return raw_url
            if not self.is_rewritable_asset_url(raw_url):
                return raw_url
            rewritten = self.rewrite_relative_asset_url(
                raw_url,
                js_asset_path,
                plugin_name,
                page_name,
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
            return (
                f"{match.group('prefix')}{match.group('quote')}"
                f"{rewritten}{match.group('quote')}"
            )

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
            return (
                f"{match.group('prefix')}{match.group('quote')}"
                f"{rewritten}{match.group('quote')}"
            )

        return _JS_SIDE_EFFECT_IMPORT_RE.sub(replace_side_effect, rewritten_js)

    @staticmethod
    async def read_plugin_page_text(file_path: Path) -> str:
        async with aiofiles.open(file_path, encoding="utf-8") as file:
            return await file.read()

    @staticmethod
    async def read_plugin_page_binary(file_path: Path) -> bytes:
        async with aiofiles.open(file_path, mode="rb") as file:
            return await file.read()

    @staticmethod
    def guess_plugin_page_mime_type(file_path: Path) -> str:
        return mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"

    async def serialize_plugin_page(
        self,
        plugin: StarMetadata,
        page_name: str,
        *,
        include_content_path: bool = False,
        asset_token: str = "",
    ) -> dict | None:
        plugin_name = plugin.name.strip() if isinstance(plugin.name, str) else ""
        if not plugin_name:
            return None
        try:
            page = await self.get_plugin_page(plugin, page_name)
            await self.resolve_plugin_page_file(plugin, page.name, "")
        except (FileNotFoundError, ValueError):
            return None

        page_data = {
            "name": page.name,
            "title": page.title,
            "i18n_key": f"pages.{page.name}",
        }
        if include_content_path:
            extra_query_params = {"asset_token": asset_token} if asset_token else None
            page_data["content_path"] = self.build_plugin_page_asset_url(
                plugin_name,
                page.name,
                "",
                extra_query_params=extra_query_params,
            )
        return page_data

    async def serialize_plugin_pages(self, plugin: StarMetadata) -> list[dict]:
        pages = []
        for page in await self.discover_plugin_pages(plugin):
            page_data = await self.serialize_plugin_page(plugin, page.name)
            if page_data:
                pages.append(page_data)
        return pages

    def issue_plugin_page_asset_token(
        self,
        *,
        plugin_name: str,
        page_name: str,
        jwt_secret: str | None = None,
        username: str | None,
        locale: str,
    ) -> str | None:
        jwt_secret = jwt_secret or self._jwt_secret()
        if not isinstance(jwt_secret, str) or not jwt_secret.strip():
            return None
        if not isinstance(username, str) or not username.strip():
            return None

        now = datetime.now(timezone.utc)
        payload = {
            "username": username,
            "token_type": PLUGIN_PAGE_ASSET_TOKEN_TYPE,
            "plugin_name": plugin_name,
            "page_name": page_name,
            "locale": locale,
            "iat": now,
            "exp": now + timedelta(seconds=PLUGIN_PAGE_ASSET_TOKEN_TTL_SECONDS),
        }
        return cast(str, jwt.encode(payload, jwt_secret, algorithm="HS256"))


__all__ = [
    "PLUGIN_PAGE_ASSET_TOKEN_TYPE",
    "PLUGIN_PAGE_BRIDGE_FILE",
    "PLUGIN_PAGE_ENTRY_FILE_NAME",
    "PLUGIN_PAGE_ROOT_DIR_NAME",
    "PluginPage",
    "PluginPageContentPayload",
    "PluginPageService",
    "PluginPageServiceError",
]
