import asyncio
import logging
import random
import re
from functools import lru_cache
from pathlib import Path

import aiohttp

from astrbot.core.config import VERSION
from astrbot.core.utils.http_ssl import build_tls_connector
from astrbot.core.utils.io import download_image_by_url
from astrbot.core.utils.t2i.template_manager import TemplateManager

from . import RenderStrategy

ASTRBOT_T2I_DEFAULT_ENDPOINT = "https://t2i.soulter.top/text2img"
SHIKI_RUNTIME_SCRIPT_ID = "astrbot-t2i-shiki-runtime"
SHIKI_RUNTIME_TEMPLATE_PATTERN = re.compile(r"\{\{\s*shiki_runtime\s*\|\s*safe\s*\}\}")
JINJA_SYNTAX_PATTERN = re.compile(r"\{[{%#]")
JINJA_RAW_OPEN_PATTERN = re.compile(r"{%-?\s*raw\s*-?%}")
JINJA_RAW_CLOSE_PATTERN = re.compile(r"{%-?\s*endraw\s*-?%}")

logger = logging.getLogger("astrbot")


@lru_cache(maxsize=1)
def get_shiki_runtime() -> str:
    runtime_path = (
        Path(__file__).resolve().parent / "template" / "shiki_runtime.iife.js"
    )
    if not runtime_path.exists():
        logger.error(
            "T2I Shiki runtime not found at %s. Run `cd dashboard && pnpm run build:t2i-shiki-runtime` to regenerate it. Continuing without code highlighting.",
            runtime_path,
        )
        return ""

    try:
        runtime = runtime_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as err:
        logger.warning(
            "Failed to load T2I Shiki runtime from %s: %s. Continuing without code highlighting.",
            runtime_path,
            err,
        )
        return ""

    return re.sub(r"</(script)", r"<\/\1", runtime, flags=re.IGNORECASE)


def _is_inside_jinja_raw_block(tmpl_str: str, index: int) -> bool:
    raw_open_index = -1
    for match in JINJA_RAW_OPEN_PATTERN.finditer(tmpl_str, 0, index):
        raw_open_index = match.start()

    raw_close_index = -1
    for match in JINJA_RAW_CLOSE_PATTERN.finditer(tmpl_str, 0, index):
        raw_close_index = match.start()

    return raw_open_index > raw_close_index


def _wrap_runtime_for_jinja(tmpl_str: str, script: str, index: int) -> str:
    if not JINJA_SYNTAX_PATTERN.search(script) or _is_inside_jinja_raw_block(
        tmpl_str,
        index,
    ):
        return script

    return f"{{% raw %}}{script}{{% endraw %}}"


def inject_shiki_runtime(tmpl_str: str) -> str:
    if SHIKI_RUNTIME_SCRIPT_ID in tmpl_str or SHIKI_RUNTIME_TEMPLATE_PATTERN.search(
        tmpl_str,
    ):
        return tmpl_str

    runtime = get_shiki_runtime()
    if not runtime:
        return tmpl_str

    script = f'<script id="{SHIKI_RUNTIME_SCRIPT_ID}">{runtime}</script>'
    head_close = re.search(r"</head\s*>", tmpl_str, flags=re.IGNORECASE)
    if head_close:
        script = _wrap_runtime_for_jinja(tmpl_str, script, head_close.start())
        return f"{tmpl_str[: head_close.start()]}  {script}\n{tmpl_str[head_close.start() :]}"

    script = _wrap_runtime_for_jinja(tmpl_str, script, 0)
    return f"{script}\n{tmpl_str}"


class NetworkRenderStrategy(RenderStrategy):
    def __init__(self, base_url: str | None = None) -> None:
        super().__init__()
        if not base_url:
            self.BASE_RENDER_URL = ASTRBOT_T2I_DEFAULT_ENDPOINT
        else:
            self.BASE_RENDER_URL = self._clean_url(base_url)

        self.endpoints = [self.BASE_RENDER_URL]
        self.template_manager = TemplateManager()

    async def initialize(self) -> None:
        if self.BASE_RENDER_URL == ASTRBOT_T2I_DEFAULT_ENDPOINT:
            asyncio.create_task(self.get_official_endpoints())

    async def get_template(self, name: str = "base") -> str:
        """通过名称获取文转图 HTML 模板"""
        return self.template_manager.get_template(name)

    async def get_official_endpoints(self) -> None:
        """获取官方的 t2i 端点列表。"""
        try:
            async with aiohttp.ClientSession(
                trust_env=True,
                connector=build_tls_connector(),
            ) as session:
                async with session.get(
                    "https://api.soulter.top/astrbot/t2i-endpoints",
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        all_endpoints: list[dict] = data.get("data", [])
                        self.endpoints = [
                            ep.get("url")
                            for ep in all_endpoints
                            if ep.get("active") and ep.get("url")
                        ]
                        logger.info(
                            f"Successfully got {len(self.endpoints)} official T2I endpoints.",
                        )
        except Exception as e:
            logger.error(f"Failed to get official endpoints: {e}")

    def _clean_url(self, url: str):
        url = url.removesuffix("/")
        if not url.endswith("text2img"):
            url += "/text2img"
        return url

    async def render_custom_template(
        self,
        tmpl_str: str,
        tmpl_data: dict,
        return_url: bool = True,
        options: dict | None = None,
    ) -> str:
        """使用自定义文转图模板"""
        default_options = {
            "full_page": True,
            "type": "jpeg",
            "quality": 40,
        }
        if options:
            default_options |= options

        if SHIKI_RUNTIME_TEMPLATE_PATTERN.search(tmpl_str):
            tmpl_data = {"shiki_runtime": get_shiki_runtime()} | tmpl_data
        tmpl_str = inject_shiki_runtime(tmpl_str)
        post_data = {
            "tmpl": tmpl_str,
            "json": return_url,
            "tmpldata": tmpl_data,
            "options": default_options,
        }

        endpoints = self.endpoints.copy() if self.endpoints else [self.BASE_RENDER_URL]
        random.shuffle(endpoints)
        last_exception = None
        for endpoint in endpoints:
            try:
                if return_url:
                    async with (
                        aiohttp.ClientSession(
                            trust_env=True,
                            connector=build_tls_connector(),
                        ) as session,
                        session.post(
                            f"{endpoint}/generate",
                            json=post_data,
                        ) as resp,
                    ):
                        if resp.status == 200:
                            ret = await resp.json()
                            return f"{endpoint}/{ret['data']['id']}"
                        raise Exception(f"HTTP {resp.status}")
                else:
                    # download_image_by_url 失败时抛异常
                    return await download_image_by_url(
                        f"{endpoint}/generate",
                        post=True,
                        post_data=post_data,
                    )
            except Exception as e:
                last_exception = e
                logger.warning(f"Endpoint {endpoint} failed: {e}, trying next...")
                continue
        # 全部失败
        logger.error(f"All endpoints failed: {last_exception}")
        raise RuntimeError(f"All endpoints failed: {last_exception}")

    async def render(
        self,
        text: str,
        return_url: bool = False,
        template_name: str | None = "base",
    ) -> str:
        """返回图像的文件路径"""
        if not template_name:
            template_name = "base"
        tmpl_str = await self.get_template(name=template_name)
        return await self.render_custom_template(
            tmpl_str,
            {
                "text": text,
                "version": f"v{VERSION}",
            },
            return_url,
        )
