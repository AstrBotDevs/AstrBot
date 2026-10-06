from __future__ import annotations

import json
import mimetypes
import os
import posixpath
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote, urlencode, urlunsplit

import aiofiles
import jwt
from aiofiles import ospath as aio_ospath

from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.star.star import StarMetadata
from astrbot.core.star.star_manager import PluginManager

PLUGIN_PAGE_ASSET_TOKEN_TYPE = "plugin_page_asset"
# Aligned with the dashboard session lifetime (7 days): a plugin view
# cannot outlive its parent dashboard page anyway.
PLUGIN_PAGE_ASSET_TOKEN_TTL_SECONDS = 7 * 24 * 60 * 60
# Directory names that hold plugin views inside a plugin package, in
# preference order. "views" is preferred; "pages" stays as an alias.
PLUGIN_PAGE_ROOT_DIR_NAMES = ("views", "pages")
PLUGIN_PAGE_ENTRY_FILE_NAME = "index.html"
PLUGIN_PAGE_BRIDGE_FILE = (
    Path(__file__).resolve().parent.parent / "plugin_page_bridge.js"
)

_HTML_ASSET_ATTR_RE = re.compile(
    r"(?P<attr>src|href)=(?P<quote>[\"\'])(?P<url>.*?)(?P=quote)",
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

    def _bridge_for(self, plugin: StarMetadata) -> Any | None:
        """Return the SDK bridge hosting this plugin, when bridge-hosted.

        Bridge-hosted plugins serve views through the RPC pipeline; the
        dashboard never reads their view files from disk.
        """
        if not (plugin.module_path or "").startswith("sdk_bridge."):
            return None
        manager = getattr(self.plugin_manager, "_sdk_plugin_manager", None)
        if manager is None:
            return None
        return manager.bridges.get(plugin.root_dir_name or "")

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
        view_name = payload.get("page_name")
        if not isinstance(plugin_name, str) or not isinstance(view_name, str):
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
            # "views" is the preferred i18n key prefix; "pages" stays as an alias.
            self.get_by_path(locale_data, f"views.{view_name}.title")
            or self.get_by_path(locale_data, f"pages.{view_name}.title")
            or view_name
        )

        return {
            "pluginName": plugin.name,
            "displayName": display_name,
            "pageName": view_name,
            "pageTitle": page_title,
            "locale": resolved_locale,
            "i18n": plugin_i18n,
            "isDark": theme == "dark",
        }

    async def get_plugin_page_entry_config(
        self,
        *,
        plugin_name: str | None,
        view_name: str | None,
        jwt_secret: str | None = None,
        username: str | None,
        locale: str,
    ) -> dict:
        if not plugin_name:
            raise PluginPageServiceError("缺少插件名")
        if not view_name:
            raise PluginPageServiceError("缺少 View 名称")

        plugin = self.get_plugin_metadata_by_name(plugin_name)
        if not plugin:
            raise PluginPageServiceError("插件不存在")
        if not plugin.activated:
            raise PluginPageServiceError("插件未启用")

        page = await self.serialize_plugin_page_for_request(
            plugin,
            view_name,
            include_content_path=True,
            jwt_secret=jwt_secret,
            username=username,
            locale=locale,
        )
        if not page:
            raise PluginPageServiceError("插件 View 不存在")
        return page

    async def serialize_plugin_page_for_request(
        self,
        plugin: StarMetadata,
        view_name: str,
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
                    view_name=view_name,
                    jwt_secret=jwt_secret or self._jwt_secret(),
                    username=username,
                    locale=locale,
                )
                or ""
            )
        return await self.serialize_plugin_page(
            plugin,
            view_name,
            include_content_path=include_content_path,
            asset_token=asset_token,
        )

    def prepare_plugin_page_query_params(
        self,
        plugin_name: str,
        view_name: str,
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
                    view_name=view_name,
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
                "Plugin view bridge SDK not found",
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
                f"\n;window.AstrBotPluginView?.__setInitialContext({context_json});\n"
            )
        return PluginPageContentPayload(
            content=bridge_js,
            content_type="application/javascript; charset=utf-8",
        )

    async def serve_page_content(
        self,
        *,
        plugin_name: str,
        view_name: str,
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

        bridge = self._bridge_for(plugin)
        if bridge is not None:
            return await self._serve_bridge_page_content(
                bridge,
                plugin,
                plugin_name=plugin_name,
                page_name=view_name,
                asset_path=asset_path,
                asset_token=asset_token,
                jwt_secret=jwt_secret,
                username=username,
                locale=locale,
                theme=theme,
            )

        try:
            page = await self.get_plugin_page(plugin, view_name)
            file_path = await self.resolve_plugin_page_file(
                plugin,
                page.name,
                asset_path,
            )
        except (FileNotFoundError, ValueError) as exc:
            raise PluginPageServiceError(
                "Plugin view asset not found",
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
        suffix = file_path.suffix.lower()
        if suffix == ".html":
            html_text = await self.read_plugin_page_text(file_path)
            return PluginPageContentPayload(
                content=self.process_plugin_page_html(
                    html_text,
                    theme=theme,
                    extra_query_params=extra_query_params,
                ),
                content_type="text/html; charset=utf-8",
            )
        if suffix in {".css", ".js", ".mjs"}:
            return PluginPageContentPayload(
                content=await self.read_plugin_page_text(file_path),
                content_type=self.guess_plugin_page_mime_type(file_path),
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
        allow_empty: bool = False,
    ) -> str:
        path = raw_path.replace("\\", "/").strip()
        normalized = posixpath.normpath(path)
        if normalized in {"", "."}:
            if allow_empty:
                return ""
            raise ValueError("Invalid plugin view asset path")
        if (
            normalized.startswith("../")
            or normalized == ".."
            or normalized.startswith("/")
        ):
            raise ValueError("Invalid plugin view asset path")
        return normalized

    @staticmethod
    def normalize_plugin_page_name(raw_name: str) -> str:
        view_name = raw_name.strip()
        if not view_name:
            raise ValueError("Invalid plugin view name")
        normalized = posixpath.normpath(view_name.replace("\\", "/"))
        if (
            normalized != view_name
            or normalized in {".", ".."}
            or normalized.startswith(".")
            or "/" in view_name
            or "\\" in view_name
        ):
            raise ValueError("Invalid plugin view name")
        return view_name

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
        for dir_name in PLUGIN_PAGE_ROOT_DIR_NAMES:
            pages_root = (plugin_root / dir_name).resolve(strict=False)
            pages_root.relative_to(plugin_root)
            if pages_root == plugin_root:
                continue
            if await aio_ospath.isdir(str(pages_root)):
                return pages_root
        raise FileNotFoundError("Plugin views root directory does not exist")

    async def discover_plugin_pages(self, plugin: StarMetadata) -> list[PluginPage]:
        bridge = self._bridge_for(plugin)
        if bridge is not None:
            # Bridge-hosted plugins report pages through the pipeline.
            return [
                PluginPage(
                    name=self.normalize_plugin_page_name(str(page.get("name", ""))),
                    title=str(page.get("name", "")),
                    entry_file=PLUGIN_PAGE_ENTRY_FILE_NAME,
                )
                for page in bridge._views_manifest.get("pages") or []
                if page.get("name")
            ]
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
                view_name = self.normalize_plugin_page_name(page_dir.name)
            except ValueError:
                continue
            entry_path = page_dir / PLUGIN_PAGE_ENTRY_FILE_NAME
            if not await aio_ospath.isfile(str(entry_path)):
                continue
            pages.append(
                PluginPage(
                    name=view_name,
                    title=view_name,
                    entry_file=PLUGIN_PAGE_ENTRY_FILE_NAME,
                )
            )
        return pages

    async def get_plugin_page(
        self,
        plugin: StarMetadata,
        view_name: str,
    ) -> PluginPage:
        normalized_name = self.normalize_plugin_page_name(view_name)
        for page in await self.discover_plugin_pages(plugin):
            if page.name == normalized_name:
                return page
        raise FileNotFoundError("Plugin view entry not found")

    async def resolve_plugin_page_root(
        self,
        plugin: StarMetadata,
        view_name: str,
    ) -> Path:
        normalized_name = self.normalize_plugin_page_name(view_name)
        pages_root = await self.resolve_plugin_pages_root(plugin)
        page_root = (pages_root / normalized_name).resolve(strict=False)
        page_root.relative_to(pages_root)
        if not await aio_ospath.isdir(str(page_root)):
            raise FileNotFoundError("Plugin view root directory does not exist")
        return page_root

    async def resolve_plugin_page_file(
        self,
        plugin: StarMetadata,
        view_name: str,
        asset_path: str,
    ) -> Path:
        page = await self.get_plugin_page(plugin, view_name)
        page_root = await self.resolve_plugin_page_root(plugin, page.name)
        target_name = (
            self.normalize_plugin_page_path(asset_path, allow_empty=True)
            or page.entry_file
        )
        target_path = (page_root / target_name).resolve(strict=False)
        target_path.relative_to(page_root)
        if not await aio_ospath.isfile(str(target_path)):
            raise FileNotFoundError("Plugin view asset not found")
        return target_path

    async def _serve_bridge_page_content(
        self,
        bridge: Any,
        plugin: StarMetadata,
        *,
        plugin_name: str,
        page_name: str,
        asset_path: str,
        asset_token: str,
        jwt_secret: str | None,
        username: str | None,
        locale: str,
        theme: str | None,
    ) -> PluginPageContentPayload:
        """Serve one view asset for a bridge-hosted plugin via the pipeline."""
        try:
            page = await self.get_plugin_page(plugin, page_name)
        except (FileNotFoundError, ValueError) as exc:
            raise PluginPageServiceError(
                "Plugin Page not found",
                status_code=404,
            ) from exc

        served_asset_path = asset_path or page.entry_file
        try:
            content_type, content = await self._read_bridge_view_file(
                bridge,
                page.name,
                served_asset_path,
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
        suffix = Path(served_asset_path).suffix.lower()
        if suffix == ".html":
            return PluginPageContentPayload(
                content=self.process_plugin_page_html(
                    content.decode("utf-8", errors="replace"),
                    theme=theme,
                    extra_query_params=extra_query_params,
                ),
                content_type="text/html; charset=utf-8",
            )
        # CSS/JS are served as-is: path-token URLs make relative references
        # resolve correctly, same as the disk path.
        if suffix in {".css", ".js", ".mjs"}:
            return PluginPageContentPayload(
                content=content.decode("utf-8", errors="replace"),
                content_type=content_type,
            )
        return PluginPageContentPayload(
            content=content,
            content_type=content_type,
        )

    @staticmethod
    async def _read_bridge_view_file(
        bridge: Any,
        page_name: str,
        asset_path: str,
    ) -> tuple[str, bytes]:
        """Stream one view file from the Runner through the pipeline."""
        client = bridge._require_client()
        items = [
            item
            async for item in client.invoke_views(
                "read",
                page_name,
                asset_path,
            )
        ]
        if not items:
            raise FileNotFoundError(asset_path)
        info = items[0].get("info") or {}
        content = b"".join(item.get("chunk") or b"" for item in items[1:])
        return str(info.get("content_type") or "application/octet-stream"), content

    @staticmethod
    def build_plugin_page_view_content_path(
        plugin_name: str,
        view_name: str,
        token: str,
        asset_path: str = "",
    ) -> str:
        """Build a path-token view content URL.

        The token travels in the path so relative URLs inside the view inherit
        it through normal URL resolution, without content rewriting.
        """
        encoded_plugin_name = quote(plugin_name, safe="")
        encoded_view_name = quote(
            PluginPageService.normalize_plugin_page_name(view_name),
            safe="",
        )
        base = (
            f"/api/v1/plugins/{encoded_plugin_name}/views/"
            f"{encoded_view_name}/_t/{quote(token, safe='')}"
        )
        if not asset_path:
            return base + "/"
        safe_asset_path = PluginPageService.normalize_plugin_page_path(
            asset_path,
            allow_empty=True,
        )
        encoded_path = "/".join(
            quote(part, safe="") for part in safe_asset_path.split("/")
        )
        return f"{base}/{encoded_path}"

    @staticmethod
    def get_plugin_page_bridge_sdk_url(
        extra_query_params: dict[str, str] | None = None,
    ) -> str:
        query = urlencode(extra_query_params or {})
        return urlunsplit(("", "", "/api/plugin/page/bridge-sdk.js", query, ""))

    def process_plugin_page_html(
        self,
        html_text: str,
        *,
        theme: str | None,
        extra_query_params: dict[str, str] | None = None,
    ) -> str:
        """Process view HTML before serving.

        Applies the theme and injects (or retargets) the bridge SDK script.
        Relative asset URLs are left untouched: view assets are served from
        path-token URLs, so relative references resolve correctly on their own.
        """

        def replace_bridge_url(match: re.Match[str]) -> str:
            raw_url = match.group("url")
            if raw_url.strip() != "/api/plugin/page/bridge-sdk.js":
                return match.group(0)
            url = self.get_plugin_page_bridge_sdk_url(extra_query_params)
            return f"{match.group('attr')}={match.group('quote')}{url}{match.group('quote')}"

        processed_html = _HTML_ASSET_ATTR_RE.sub(replace_bridge_url, html_text)
        if theme:
            processed_html = self.apply_theme_to_html(processed_html, theme)
        if "/api/plugin/page/bridge-sdk.js" not in processed_html:
            bridge_tag = f'<script src="{self.get_plugin_page_bridge_sdk_url(extra_query_params)}"></script>'
            if "</body>" in processed_html:
                processed_html = processed_html.replace(
                    "</body>", f"{bridge_tag}</body>", 1
                )
            else:
                processed_html += bridge_tag
        return processed_html

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
        view_name: str,
        *,
        include_content_path: bool = False,
        asset_token: str = "",
    ) -> dict | None:
        plugin_name = plugin.name.strip() if isinstance(plugin.name, str) else ""
        if not plugin_name:
            return None
        try:
            page = await self.get_plugin_page(plugin, view_name)
            await self.resolve_plugin_page_file(plugin, page.name, "")
        except (FileNotFoundError, ValueError):
            return None

        page_data = {
            "name": page.name,
            "title": page.title,
            "i18n_key": f"pages.{page.name}",
        }
        if include_content_path and asset_token:
            page_data["content_path"] = (
                self.build_plugin_page_view_content_path(
                    plugin_name,
                    page.name,
                    asset_token,
                )
                # Kept as a query echo for view scripts that read the token
                # from location.search.
                + f"?asset_token={quote(asset_token, safe='')}"
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
        view_name: str,
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
            # Distinguishes long-lived view-session tokens from future
            # one-shot presigned tokens (e.g. direct downloads).
            "purpose": "page_session",
            "plugin_name": plugin_name,
            "page_name": view_name,
            "locale": locale,
            "iat": now,
            "exp": now + timedelta(seconds=PLUGIN_PAGE_ASSET_TOKEN_TTL_SECONDS),
        }
        return cast(str, jwt.encode(payload, jwt_secret, algorithm="HS256"))


__all__ = [
    "PLUGIN_PAGE_ASSET_TOKEN_TYPE",
    "PLUGIN_PAGE_BRIDGE_FILE",
    "PLUGIN_PAGE_ENTRY_FILE_NAME",
    "PLUGIN_PAGE_ROOT_DIR_NAMES",
    "PluginPage",
    "PluginPageContentPayload",
    "PluginPageService",
    "PluginPageServiceError",
]
