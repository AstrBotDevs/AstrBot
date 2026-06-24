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

# 默认的文转图服务端点 URL
ASTRBOT_T2I_DEFAULT_ENDPOINT = "https://t2i.soulter.top/text2img"
# Shiki 运行时脚本的唯一标识 ID，用于检测模板中是否已注入
SHIKI_RUNTIME_SCRIPT_ID = "astrbot-t2i-shiki-runtime"
# 匹配 Shiki 运行时模板变量的正则表达式，用于检测模板是否需要注入
SHIKI_RUNTIME_TEMPLATE_PATTERN = re.compile(r"\{\{\s*shiki_runtime\s*\|\s*safe\s*\}\}")
# 匹配 Jinja2 语法标记的正则表达式，用于检测字符串是否包含 Jinja2 语法
JINJA_SYNTAX_PATTERN = re.compile(r"\{[{%#]")
# 匹配 Jinja2 raw 块开始标记的正则表达式
JINJA_RAW_OPEN_PATTERN = re.compile(r"{%-?\s*raw\s*-?%}")
# 匹配 Jinja2 raw 块结束标记的正则表达式
JINJA_RAW_CLOSE_PATTERN = re.compile(r"{%-?\s*endraw\s*-?%}")

# 获取日志记录器实例
logger = logging.getLogger("astrbot")


@lru_cache(maxsize=1)
def get_shiki_runtime() -> str:
    """
    获取 Shiki 运行时 JavaScript 代码。
    使用 LRU 缓存避免重复读取文件，提升性能。

    Returns:
        str: Shiki 运行时的 IIFE JavaScript 代码，如果文件不存在或读取失败则返回空字符串。
    """
    # 构建 Shiki 运行时文件的完整路径
    runtime_path = (
        Path(__file__).resolve().parent / "template" / "shiki_runtime.iife.js"
    )
    # 检查运行时文件是否存在
    if not runtime_path.exists():
        logger.error(
            "T2I Shiki runtime not found at %s. Run `cd dashboard && pnpm run build:t2i-shiki-runtime` to regenerate it. Continuing without code highlighting.",
            runtime_path,
        )
        return ""  # 文件不存在，返回空字符串

    try:
        # 读取 JavaScript 文件内容
        runtime = runtime_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as err:
        # 捕获文件读取或编码错误
        logger.warning(
            "Failed to load T2I Shiki runtime from %s: %s. Continuing without code highlighting.",
            runtime_path,
            err,
        )
        return ""  # 读取失败，返回空字符串

    # 转义 </script> 标签，防止在 HTML 中提前闭合，确保脚本完整注入
    return re.sub(r"</(script)", r"<\/\1", runtime, flags=re.IGNORECASE)


def _is_inside_jinja_raw_block(tmpl_str: str, index: int) -> bool:
    """
    检查指定索引位置是否位于 Jinja2 的 raw 块内部。
    在 raw 块内部的代码不会被 Jinja2 引擎解析，因此不需要特殊处理。

    Args:
        tmpl_str: 模板字符串
        index: 要检查的字符位置索引

    Returns:
        bool: 如果在 raw 块内返回 True，否则返回 False
    """
    # 查找指定位置之前最后一个 raw 开始标记的位置
    raw_open_index = -1
    for match in JINJA_RAW_OPEN_PATTERN.finditer(tmpl_str, 0, index):
        raw_open_index = match.start()  # 更新为最新的 raw 开始位置

    # 查找指定位置之前最后一个 raw 结束标记的位置
    raw_close_index = -1
    for match in JINJA_RAW_CLOSE_PATTERN.finditer(tmpl_str, 0, index):
        raw_close_index = match.start()  # 更新为最新的 raw 结束位置

    # 如果最近的 raw 开始标记在结束标记之后，说明当前位置在 raw 块内
    return raw_open_index > raw_close_index


def _wrap_runtime_for_jinja(tmpl_str: str, script: str, index: int) -> str:
    """
    根据模板字符串的上下文，决定是否需要用 Jinja2 raw 标签包裹脚本内容。
    如果脚本包含 Jinja2 语法且不在 raw 块内，则包裹以避免被模板引擎错误解析。

    Args:
        tmpl_str: 模板字符串
        script: 要注入的脚本字符串
        index: 注入位置的字符索引

    Returns:
        str: 可能被 raw 标签包裹的脚本字符串
    """
    # 如果脚本不包含 Jinja2 语法，或者注入位置已经在 raw 块内，则直接返回脚本
    if not JINJA_SYNTAX_PATTERN.search(script) or _is_inside_jinja_raw_block(
        tmpl_str,
        index,
    ):
        return script

    # 否则用 raw 标签包裹，防止 Jinja2 模板引擎错误解析脚本内容
    return f"{{% raw %}}{script}{{% endraw %}}"


def inject_shiki_runtime(tmpl_str: str) -> str:
    """
    将 Shiki 运行时代码注入到 HTML 模板中。
    会检查模板是否已包含运行时，避免重复注入。
    优先将脚本插入到 </head> 标签之前，如果没有 head 标签则插入到模板开头。

    Args:
        tmpl_str: HTML 模板字符串

    Returns:
        str: 注入后的模板字符串
    """
    # 检查模板是否已经包含了 Shiki 运行时脚本或模板变量
    if SHIKI_RUNTIME_SCRIPT_ID in tmpl_str or SHIKI_RUNTIME_TEMPLATE_PATTERN.search(
        tmpl_str,
    ):
        return tmpl_str  # 已存在，无需重复注入

    # 获取 Shiki 运行时 JavaScript 代码
    runtime = get_shiki_runtime()
    if not runtime:
        return tmpl_str  # 无法获取运行时，返回原模板

    # 构建包含唯一 ID 的 script 标签
    script = f'<script id="{SHIKI_RUNTIME_SCRIPT_ID}">{runtime}</script>'
    # 查找 </head> 标签的位置
    head_close = re.search(r"</head\s*>", tmpl_str, flags=re.IGNORECASE)
    if head_close:
        # 如果找到 </head>，根据上下文决定是否需要 raw 包裹
        script = _wrap_runtime_for_jinja(tmpl_str, script, head_close.start())
        # 将脚本插入到 </head> 之前
        return f"{tmpl_str[: head_close.start()]}  {script}\n{tmpl_str[head_close.start() :]}"

    # 没有找到 </head>，在模板开头插入
    script = _wrap_runtime_for_jinja(tmpl_str, script, 0)
    return f"{script}\n{tmpl_str}"


class NetworkRenderStrategy(RenderStrategy):
    """
    网络渲染策略类。
    通过远程文转图服务（Text-to-Image）将 HTML 模板渲染为图像。
    支持多端点负载均衡和故障转移。
    """

    def __init__(self, base_url: str | None = None) -> None:
        """
        初始化网络渲染策略。

        Args:
            base_url: 自定义的文转图服务基础 URL，如果为 None 则使用默认端点
        """
        super().__init__()  # 调用父类构造函数
        if not base_url:
            # 使用默认的文转图服务端点
            self.BASE_RENDER_URL = ASTRBOT_T2I_DEFAULT_ENDPOINT
        else:
            # 使用自定义 URL，并进行清理和格式化
            self.BASE_RENDER_URL = self._clean_url(base_url)

        # 初始化端点列表，默认只有基础 URL
        self.endpoints = [self.BASE_RENDER_URL]
        # 创建模板管理器实例
        self.template_manager = TemplateManager()

    async def initialize(self) -> None:
        """
        异步初始化方法。
        如果使用的是官方默认端点，则异步获取官方提供的所有可用端点列表。
        """
        if self.BASE_RENDER_URL == ASTRBOT_T2I_DEFAULT_ENDPOINT:
            # 创建异步任务获取官方端点列表，不阻塞主流程
            asyncio.create_task(self.get_official_endpoints())

    async def get_template(self, name: str = "base") -> str:
        """
        通过名称获取文转图 HTML 模板。

        Args:
            name: 模板名称，默认为 "base"

        Returns:
            str: HTML 模板字符串
        """
        # 从模板管理器中获取指定名称的模板
        return self.template_manager.get_template(name)

    async def get_official_endpoints(self) -> None:
        """
        获取官方的 T2I（文转图）端点列表。
        从官方 API 获取所有活跃的端点 URL，用于负载均衡和故障转移。
        """
        try:
            # 创建 HTTP 客户端会话
            async with aiohttp.ClientSession(
                trust_env=True,  # 信任环境变量中的代理设置
                connector=build_tls_connector(),  # 使用自定义 TLS 连接器
            ) as session:
                # 发送 GET 请求获取端点列表
                async with session.get(
                    "https://api.soulter.top/astrbot/t2i-endpoints",
                ) as resp:
                    if resp.status == 200:
                        # 解析 JSON 响应
                        data = await resp.json()
                        # 获取端点数据列表
                        all_endpoints: list[dict] = data.get("data", [])
                        # 过滤出活跃且有 URL 的端点
                        self.endpoints = [
                            ep.get("url")
                            for ep in all_endpoints
                            if ep.get("active") and ep.get("url")
                        ]
                        logger.info(
                            f"Successfully got {len(self.endpoints)} official T2I endpoints.",
                        )
        except Exception as e:
            # 捕获所有异常，避免影响主流程
            logger.error(f"Failed to get official endpoints: {e}")

    def _clean_url(self, url: str):
        """
        清理和格式化 URL。
        移除末尾斜杠，确保 URL 以 /text2img 结尾。

        Args:
            url: 原始 URL

        Returns:
            str: 清理后的 URL
        """
        # 移除 URL 末尾的斜杠
        url = url.removesuffix("/")
        # 如果 URL 不以 text2img 结尾，则添加
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
        """
        使用自定义文转图模板进行渲染。

        Args:
            tmpl_str: HTML 模板字符串
            tmpl_data: 模板数据字典
            return_url: 是否返回图片 URL，False 则返回图片文件路径
            options: 渲染选项，如页面大小、图片格式、质量等

        Returns:
            str: 图片的 URL 或本地文件路径

        Raises:
            RuntimeError: 当所有端点都渲染失败时抛出
        """
        # 设置默认的渲染选项
        default_options = {
            "full_page": True,  # 渲染整个页面
            "type": "jpeg",     # 输出格式为 JPEG
            "quality": 40,      # 图片质量 40%
        }
        # 合并用户自定义选项
        if options:
            default_options |= options

        # 获取当前事件循环
        loop = asyncio.get_running_loop()
        # 在线程池中执行模板预处理，避免 1.2MB 的 JS 处理阻塞事件循环
        tmpl_str, tmpl_data = await loop.run_in_executor(
            None, self._prepare_template_sync, tmpl_str, tmpl_data
        )

        # 构建 POST 请求数据
        post_data = {
            "tmpl": tmpl_str,           # 模板字符串
            "json": return_url,          # 是否返回 JSON 格式（包含图片 URL）
            "tmpldata": tmpl_data,       # 模板渲染数据
            "options": default_options,  # 渲染选项
        }

        # 复制端点列表并随机打乱，实现负载均衡
        endpoints = self.endpoints.copy() if self.endpoints else [self.BASE_RENDER_URL]
        random.shuffle(endpoints)
        last_exception = None  # 记录最后一个异常，用于全部失败时抛出

        # 遍历所有端点进行故障转移
        for endpoint in endpoints:
            try:
                if return_url:
                    # 需要返回图片 URL 时，使用异步 HTTP 请求
                    async with (
                        aiohttp.ClientSession(
                            trust_env=True,
                            connector=build_tls_connector(),
                        ) as session,
                        session.post(
                            f"{endpoint}/generate",  # 发送渲染请求
                            json=post_data,
                        ) as resp,
                    ):
                        if resp.status == 200:
                            # 请求成功，解析返回的 JSON 数据
                            ret = await resp.json()
                            # 返回完整的图片 URL
                            return f"{endpoint}/{ret['data']['id']}"
                        # HTTP 状态码非 200，抛出异常进入故障转移
                        raise Exception(f"HTTP {resp.status}")
                else:
                    # 直接下载图片到本地，返回本地文件路径
                    return await download_image_by_url(
                        f"{endpoint}/generate",
                        post=True,          # 使用 POST 请求
                        post_data=post_data,
                    )
            except Exception as e:
                # 记录异常并尝试下一个端点
                last_exception = e
                logger.warning(f"Endpoint {endpoint} failed: {e}, trying next...")
                continue

        # 所有端点都失败了
        logger.error(f"All endpoints failed: {last_exception}")
        raise RuntimeError(f"All endpoints failed: {last_exception}")

    async def render(
        self,
        text: str,
        return_url: bool = False,
        template_name: str | None = "base",
    ) -> str:
        """
        渲染文本为图像。

        Args:
            text: 要渲染的文本内容
            return_url: 是否返回图片 URL，默认返回本地文件路径
            template_name: 使用的模板名称，默认为 "base"

        Returns:
            str: 图像的文件路径或 URL
        """
        # 如果未指定模板名称，使用默认模板
        if not template_name:
            template_name = "base"
        # 获取模板字符串
        tmpl_str = await self.get_template(name=template_name)
        # 使用自定义模板渲染，传入文本内容和版本信息
        return await self.render_custom_template(
            tmpl_str,
            {
                "text": text,             # 要渲染的文本
                "version": f"v{VERSION}", # 当前版本号
            },
            return_url,
        )

    @staticmethod
    def _prepare_template_sync(tmpl_str: str, tmpl_data: dict) -> tuple[str, dict]:
        """
        同步方法，在线程池中执行的模板预处理。
        处理 Shiki 运行时注入和模板变量设置，避免阻塞事件循环。

        Args:
            tmpl_str: 模板字符串
            tmpl_data: 模板数据字典

        Returns:
            tuple[str, dict]: 处理后的模板字符串和数据字典
        """
        # 检查模板中是否包含 Shiki 运行时模板变量
        if SHIKI_RUNTIME_TEMPLATE_PATTERN.search(tmpl_str):
            # 将 Shiki 运行时添加到模板数据的最前面
            tmpl_data = {"shiki_runtime": get_shiki_runtime()} | tmpl_data
        # 将 Shiki 运行时脚本注入到 HTML 模板中
        tmpl_str = inject_shiki_runtime(tmpl_str)
        # 返回处理后的模板和数据
        return tmpl_str, tmpl_data