import asyncio
import logging
import re
import time
import uuid
from pathlib import Path
from typing import Any, Literal, TypedDict

from jinja2.sandbox import SandboxedEnvironment
from pydantic import BaseModel

from astrbot.core.config import VERSION
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path

from . import RenderStrategy
from .runtime_stats import RenderResult, T2iRuntimeStats
from .template_manager import TemplateManager
from .template_runtime import (
    SHIKI_RUNTIME_TEMPLATE_PATTERN,
    get_shiki_runtime,
    inject_shiki_runtime,
    render_markdown,
)

try:
    from playwright._impl._errors import TargetClosedError
    from playwright.async_api import async_playwright
except ImportError:  # pragma: no cover - exercised indirectly in runtime setups
    TargetClosedError = RuntimeError
    async_playwright = None

logger = logging.getLogger("astrbot")
RENDERED_HTML_TEMPLATE_PATTERN = re.compile(r"\brendered_html\b")


class FloatRect(TypedDict):
    x: float
    y: float
    width: float
    height: float


class ScreenshotOptions(BaseModel):
    timeout: float | None = None
    type: Literal["jpeg", "png", None] = None
    quality: int | None = None
    omit_background: bool | None = None
    full_page: bool | None = True
    clip: FloatRect | None = None
    animations: Literal["allow", "disabled", None] = None
    caret: Literal["hide", "initial", None] = None
    scale: Literal["css", "device", None] = None
    viewport_width: int | None = None
    viewport_height: int | None = None
    device_scale_factor_level: Literal["normal", "high", "ultra", None] = None


class LocalRenderStrategy(RenderStrategy):
    DEFAULT_VIEWPORT_WIDTH = 1280
    DEFAULT_VIEWPORT_HEIGHT = 720
    SCALE_FACTOR_MAP = {
        "normal": 1.0,
        "high": 1.3,
        "ultra": 1.8,
    }

    def __init__(self, runtime_stats: T2iRuntimeStats | None = None) -> None:
        self.template_manager = TemplateManager()
        self.runtime_stats = runtime_stats or T2iRuntimeStats()
        self.playwright: Any | None = None
        self.browser: Any | None = None
        self.contexts: dict[str, Any] = {}
        self._browser_lock = asyncio.Lock()
        self.temp_dir = Path(get_astrbot_temp_path()) / "t2i_local"
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    async def initialize(self) -> None:
        return None

    async def terminate(self) -> None:
        async with self._browser_lock:
            await self._close_contexts_locked()

            if self.browser is not None:
                try:
                    await self.browser.close()
                except Exception as exc:
                    logger.debug("Failed to close local T2I browser: %s", exc)
                self.browser = None
            self.runtime_stats.set_browser_connected(False)

            if self.playwright is not None:
                try:
                    await self.playwright.stop()
                except Exception as exc:
                    logger.debug("Failed to stop local T2I Playwright: %s", exc)
                self.playwright = None

    async def _close_contexts_locked(self) -> None:
        """Close every cached context while the browser lock is held."""
        for context in self.contexts.values():
            try:
                await context.close()
            except Exception as exc:
                logger.debug("Failed to close local T2I browser context: %s", exc)
        self.contexts.clear()
        self.runtime_stats.set_context_count(0)

    async def _discard_context(self, level: str, context: Any) -> None:
        """Discard a closed context without racing another renderer."""
        async with self._browser_lock:
            if self.contexts.get(level) is not context:
                return
            self.contexts.pop(level, None)
            try:
                await context.close()
            except Exception as exc:
                logger.debug("Failed to close stale local T2I context: %s", exc)
            self.runtime_stats.set_context_count(len(self.contexts))

    async def _ensure_context(self, level: str = "normal"):
        if async_playwright is None:
            raise RuntimeError(
                "Playwright is not installed. Install the `playwright` package and run `playwright install chromium`.",
            )
        async with self._browser_lock:
            playwright = self.playwright
            if playwright is None:
                playwright = await async_playwright().start()
                self.playwright = playwright

            browser = self.browser
            if browser is None or not browser.is_connected():
                restarted = browser is not None
                await self._close_contexts_locked()
                if browser is not None:
                    try:
                        await browser.close()
                    except Exception as exc:
                        logger.debug("Failed to close stale local T2I browser: %s", exc)
                browser = await playwright.chromium.launch(headless=True)
                self.browser = browser
                self.runtime_stats.record_browser_started(restarted=restarted)

            context = self.contexts.get(level)
            if context is None:
                scale_factor = self.SCALE_FACTOR_MAP.get(level, 1.0)
                context = await browser.new_context(device_scale_factor=scale_factor)
                self.contexts[level] = context
                self.runtime_stats.set_context_count(len(self.contexts))

            return context

    @staticmethod
    def _prepare_template_sync(tmpl_str: str, tmpl_data: dict) -> tuple[str, dict]:
        if SHIKI_RUNTIME_TEMPLATE_PATTERN.search(tmpl_str):
            tmpl_data = {"shiki_runtime": get_shiki_runtime()} | tmpl_data
        if (
            "text" in tmpl_data
            and "rendered_html" not in tmpl_data
            and RENDERED_HTML_TEMPLATE_PATTERN.search(tmpl_str)
        ):
            tmpl_data = {
                "rendered_html": render_markdown(str(tmpl_data["text"])),
            } | tmpl_data
        tmpl_str = inject_shiki_runtime(tmpl_str)
        return tmpl_str, tmpl_data

    @staticmethod
    def _render_template_sync(tmpl_str: str, tmpl_data: dict) -> str:
        return SandboxedEnvironment().from_string(tmpl_str).render(tmpl_data)

    def _create_temp_path(self, suffix: str) -> Path:
        return self.temp_dir / f"t2i_{uuid.uuid4().hex}.{suffix}"

    def _resolve_viewport_size(
        self,
        html: str,
        screenshot_options: ScreenshotOptions,
    ) -> tuple[int | None, int | None]:
        viewport_width = screenshot_options.viewport_width
        viewport_height = screenshot_options.viewport_height

        if viewport_width is not None and viewport_height is not None:
            return viewport_width, viewport_height

        try:
            head_snippet = html[:4096]
            if viewport_width is None:
                pattern = (
                    r'<meta\s+[^>]*name=["\']viewport["\'][^>]*'
                    r'content=["\'][^"\']*width\s*=\s*(\d+)[^"\']*["\'][^>]*>'
                )
                if match := re.search(pattern, head_snippet, re.IGNORECASE):
                    viewport_width = int(match[1])

            if viewport_height is None:
                pattern = (
                    r'<meta\s+[^>]*name=["\']viewport["\'][^>]*'
                    r'content=["\'][^"\']*height\s*=\s*(\d+)[^"\']*["\'][^>]*>'
                )
                if match := re.search(pattern, head_snippet, re.IGNORECASE):
                    viewport_height = int(match[1])
        except (ValueError, re.error) as exc:
            logger.debug("Failed to resolve local T2I viewport size: %s", exc)

        return viewport_width, viewport_height

    async def _render_html_to_image(
        self,
        html: str,
        screenshot_options: ScreenshotOptions,
    ) -> str:
        level = screenshot_options.device_scale_factor_level or "normal"
        html_path = self._create_temp_path("html")
        image_path = self._create_temp_path(screenshot_options.type or "png")
        page = None
        page_opened = False
        rendered = False
        output_bytes = 0
        result: RenderResult = "failed"
        started = time.perf_counter()
        self.runtime_stats.record_render_started()
        try:
            await asyncio.to_thread(html_path.write_text, html, encoding="utf-8")
            context = await self._ensure_context(level)
            try:
                page = await context.new_page()
            except TargetClosedError as exc:
                logger.warning(
                    "Local T2I context closed while creating a page: %s", exc
                )
                await self._discard_context(level, context)
                context = await self._ensure_context(level)
                page = await context.new_page()
            page_opened = True
            self.runtime_stats.record_page_opened()

            async def block_remote_requests(route) -> None:
                if route.request.url.startswith(("http://", "https://")):
                    await route.abort()
                    return
                await route.continue_()

            await page.route("**/*", block_remote_requests)
            viewport_width, viewport_height = self._resolve_viewport_size(
                html,
                screenshot_options,
            )
            await page.set_viewport_size(
                {
                    "width": viewport_width
                    if viewport_width is not None
                    else self.DEFAULT_VIEWPORT_WIDTH,
                    "height": viewport_height
                    if viewport_height is not None
                    else self.DEFAULT_VIEWPORT_HEIGHT,
                },
            )

            await page.goto(html_path.as_uri(), timeout=screenshot_options.timeout)
            screenshot_kwargs = screenshot_options.model_dump(exclude_none=True)
            screenshot_kwargs.pop("viewport_width", None)
            screenshot_kwargs.pop("viewport_height", None)
            screenshot_kwargs.pop("device_scale_factor_level", None)
            if screenshot_options.type == "png":
                screenshot_kwargs.pop("quality", None)
            screenshot_kwargs["path"] = str(image_path)
            await page.screenshot(**screenshot_kwargs)
            output_bytes = (await asyncio.to_thread(image_path.stat)).st_size
            rendered = True
            result = "success"
            return str(image_path)
        except asyncio.CancelledError:
            result = "cancelled"
            raise
        finally:
            if page is not None:
                try:
                    await page.close()
                except Exception as exc:
                    logger.debug("Failed to close local T2I page: %s", exc)
                finally:
                    if page_opened:
                        self.runtime_stats.record_page_closed()
            html_path.unlink(missing_ok=True)
            if not rendered:
                image_path.unlink(missing_ok=True)
            self.runtime_stats.record_render_finished(
                result,
                (time.perf_counter() - started) * 1000,
                output_bytes,
            )

    async def render_custom_template(
        self,
        tmpl_str: str,
        tmpl_data: dict,
        options: dict | None = None,
    ) -> str:
        default_options = {
            "full_page": True,
            "type": "png",
            "device_scale_factor_level": "ultra",
            "viewport_width": 1280,
        }
        if options:
            default_options |= options

        tmpl_str, tmpl_data = await asyncio.to_thread(
            self._prepare_template_sync,
            tmpl_str,
            tmpl_data,
        )
        html = await asyncio.to_thread(
            self._render_template_sync,
            tmpl_str,
            tmpl_data,
        )
        return await self._render_html_to_image(
            html,
            ScreenshotOptions(**default_options),
        )

    async def render(
        self,
        text: str,
        template_name: str | None = "base",
    ) -> str:
        if not template_name:
            template_name = "base"
        tmpl_str = self.template_manager.get_template(template_name)
        return await self.render_custom_template(
            tmpl_str,
            {
                "text": text,
                "version": f"v{VERSION}",
            },
        )

    def get_runtime_stats(self) -> dict[str, int | float | bool]:
        """Return a non-sensitive snapshot of the local renderer state."""
        try:
            connected = bool(
                self.browser is not None and self.browser.is_connected(),
            )
        except Exception as exc:
            logger.debug("Failed to inspect local T2I browser state: %s", exc)
            connected = False
        self.runtime_stats.set_browser_connected(connected)
        return self.runtime_stats.snapshot()
