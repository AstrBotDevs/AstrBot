"""Google Gemini Embedding 提供商适配器。

两条任务条件化路径，取决于模型代际：

- ``gemini-embedding-001``（及更早模型）：使用 API 的 ``task_type`` 参数，
  查询用 ``RETRIEVAL_QUERY``，文档用 ``RETRIEVAL_DOCUMENT``（可带 ``title``）。
- ``gemini-embedding-2``：官方不再支持 ``task_type``，改为把任务前缀写进文本。
  非对称检索的格式为：

  - 查询：``task: search result | query: {content}``
  - 文档：``title: {title} | text: {content}``（无标题时 ``title: none``）

参考：https://ai.google.dev/gemini-api/docs/embeddings
"""

from google import genai
from google.genai import types
from google.genai.errors import APIError

from astrbot import logger

from ..entities import ProviderType
from ..provider import EmbeddingProvider
from ..register import register_provider_adapter

#: 走文本前缀路径的模型前缀（gemini-embedding-2 / -2-preview 等）。
_TASK_PREFIX_MODEL_MARKERS = ("gemini-embedding-2",)

#: 走 ``task_type`` 参数路径的默认查询/文档任务类型。
_DEFAULT_QUERY_TASK = "RETRIEVAL_QUERY"
_DEFAULT_DOCUMENT_TASK = "RETRIEVAL_DOCUMENT"

#: ``gemini-embedding-2`` 支持的非对称任务名。
_PREFIX_ASYMMETRIC_TASKS = {
    "search result",
    "question answering",
    "fact checking",
    "code retrieval",
}


def uses_task_prefix(model: str) -> bool:
    """判断该模型是否应使用文本任务前缀（而非 ``task_type`` 参数）。"""
    model_name = str(model or "").strip().lower()
    # 允许 ``models/gemini-embedding-2`` 这类带前缀的写法。
    model_name = model_name.rsplit("/", 1)[-1]
    return model_name.startswith(_TASK_PREFIX_MODEL_MARKERS)


def _normalize_task_name(task: str) -> str:
    """把用户配置的任务名归一化（大小写、下划线/空格互换）。"""
    return " ".join(str(task or "").strip().lower().replace("_", " ").split())


def resolve_query_task(task: str | None) -> str:
    """把配置值解析成合法的查询任务名，非法值回退到 ``search result``。

    单独抽出来的原因是：配置笔误（多一个连字符、大写、写错单词）不应该让
    整个检索链路在调用时才崩掉，而构造期就应该收敛到一个可用值。
    """
    normalized = _normalize_task_name(task or "")
    return normalized if normalized in _PREFIX_ASYMMETRIC_TASKS else "search result"


def build_query_prefix(task: str = "search result") -> str:
    """构造 ``gemini-embedding-2`` 的查询前缀。

    任务名不可识别时回退到 ``search result``，保证检索链路不会因为一个配置
    笔误整体崩掉。

    Args:
        task: 任务名，见 ``_PREFIX_ASYMMETRIC_TASKS``，默认 ``search result``。

    Returns:
        形如 ``task: search result | query: `` 的前缀字符串。
    """
    normalized = _normalize_task_name(task)
    if normalized not in _PREFIX_ASYMMETRIC_TASKS:
        normalized = resolve_query_task(task)
    return f"task: {normalized} | query: "


def build_document_prefix(title: str | None = None) -> str:
    """构造 ``gemini-embedding-2`` 的文档前缀。

    Args:
        title: 文档标题；为空时使用 ``none``。

    Returns:
        形如 ``title: none | text: `` 的前缀字符串。
    """
    safe_title = " ".join(str(title or "").split()) or "none"
    return f"title: {safe_title} | text: "


@register_provider_adapter(
    "gemini_embedding",
    "Google Gemini Embedding 提供商适配器",
    provider_type=ProviderType.EMBEDDING,
)
class GeminiEmbeddingProvider(EmbeddingProvider):
    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.provider_config = provider_config
        self.provider_settings = provider_settings

        api_key: str = provider_config["embedding_api_key"]
        api_base: str = provider_config["embedding_api_base"]
        timeout: int = int(provider_config.get("timeout", 20))

        http_options = types.HttpOptions(
            timeout=timeout * 1000, headers=self.request_headers
        )
        if api_base:
            api_base = api_base.removesuffix("/")
            http_options.base_url = api_base
        proxy = provider_config.get("proxy", "")
        if proxy:
            http_options.async_client_args = {"proxy": proxy}
            logger.info(f"[Gemini Embedding] 使用代理: {proxy}")

        self.client = genai.Client(api_key=api_key, http_options=http_options).aio
        # The SDK adds its own lower-case UA alongside our explicit header.
        self.client._api_client._http_options.headers.pop("user-agent", None)

        self.model = provider_config.get(
            "embedding_model",
            "gemini-embedding-001",
        )

        # 任务条件化配置。默认按检索场景（查询/文档非对称）处理。
        self.task_config_mode = (
            str(provider_config.get("embedding_task_type_mode", "auto")).strip().lower()
        )
        if self.task_config_mode not in {"auto", "never", "always"}:
            logger.warning(
                f"[Gemini Embedding] 未知的 embedding_task_type_mode: "
                f"{self.task_config_mode!r}，回退为 'auto'。",
            )
            self.task_config_mode = "auto"
        self.query_task = (
            provider_config.get("embedding_query_task_type") or _DEFAULT_QUERY_TASK
        )
        self.document_task = (
            provider_config.get("embedding_document_task_type")
            or _DEFAULT_DOCUMENT_TASK
        )
        self.query_prefix_task = resolve_query_task(
            provider_config.get("embedding_query_task_name")
        )
        configured_task = provider_config.get("embedding_query_task_name")
        if configured_task and resolve_query_task(
            configured_task
        ) != _normalize_task_name(configured_task):
            logger.warning(
                f"[Gemini Embedding] 未知的 embedding_query_task_name: "
                f"{configured_task!r}，回退为 'search result'。"
                f"可选: {', '.join(sorted(_PREFIX_ASYMMETRIC_TASKS))}",
            )
        # 默认留空：AstrBot 入库时已经把文档标题拼进了 embedding_contents
        # （见 kb_helper.py 的 ``{document_title}\n\n{chunk_text}``），这里再填
        # 一次会让标题重复两遍。只有直接调用本适配器、正文不含标题时才建议设置。
        self.document_title = provider_config.get("embedding_document_title") or ""

        if self._uses_task_prefix():
            logger.debug(
                f"[Gemini Embedding] 模型 {self.model} 使用文本任务前缀，"
                "不发送 task_type。",
            )

        self.set_model(self.model)

    # ── 任务条件化 ──────────────────────────────────────────────

    def _uses_task_prefix(self) -> bool:
        if self.task_config_mode == "never":
            return False
        if self.task_config_mode == "always":
            return True
        return uses_task_prefix(self.model)

    def _build_config(
        self,
        *,
        task_type: str | None,
        title: str | None = None,
    ) -> types.EmbedContentConfig:
        """构造 ``EmbedContentConfig``；前缀模式不设置 ``task_type``。"""
        kwargs: dict = {"output_dimensionality": self.get_dim()}
        if task_type and not self._uses_task_prefix():
            kwargs["task_type"] = task_type
            # ``title`` 只在 RETRIEVAL_DOCUMENT 下有意义。
            if title and task_type == _DEFAULT_DOCUMENT_TASK:
                kwargs["title"] = title
        return types.EmbedContentConfig(**kwargs)

    def _prepare_query(self, text: str) -> str:
        if not self._uses_task_prefix():
            return text
        return build_query_prefix(self.query_prefix_task) + text

    def _prepare_document(self, text: str) -> str:
        if not self._uses_task_prefix():
            return text
        return build_document_prefix(self.document_title) + text

    # ── EmbeddingProvider 接口 ──────────────────────────────────

    async def get_embedding(self, text: str) -> list[float]:
        """获取文本的嵌入。

        为兼容既有调用方（知识库入库、提供商连通性测试等），该方法按
        **文档**侧语义嵌入。检索查询请使用 :meth:`get_query_embedding`。
        """
        return await self._embed_single(
            self._prepare_document(text),
            config=self._build_config(
                task_type=self.document_task,
                title=self.document_title or None,
            ),
        )

    async def get_query_embedding(self, text: str) -> list[float]:
        """获取检索查询的嵌入（带查询侧任务条件化）。"""
        return await self._embed_single(
            self._prepare_query(text),
            config=self._build_config(task_type=self.query_task),
        )

    async def get_embeddings(self, text: list[str]) -> list[list[float]]:
        """批量获取**文档**侧文本的嵌入。

        批量入库不需要查询侧语义，因此统一走文档路径。
        """
        return await self._embed_many(
            [self._prepare_document(s) for s in text],
            config=self._build_config(
                task_type=self.document_task,
                title=self.document_title or None,
            ),
        )

    async def _embed_single(
        self,
        text: str,
        *,
        config: types.EmbedContentConfig,
    ) -> list[float]:
        try:
            result = await self.client.models.embed_content(
                model=self.model,
                contents=text,
                config=config,
            )
            if not result.embeddings or result.embeddings[0].values is None:
                raise Exception("Gemini Embedding API 返回了空向量")
            return result.embeddings[0].values
        except APIError as e:
            raise Exception(f"Gemini Embedding API请求失败: {e.message}")

    async def _embed_many(
        self,
        text: list[str],
        *,
        config: types.EmbedContentConfig,
    ) -> list[list[float]]:
        try:
            contents = [
                types.Content(parts=[types.Part.from_text(text=s)]) for s in text
            ]
            result = await self.client.models.embed_content(
                model=self.model,
                contents=contents,
                config=config,
            )
            if result.embeddings is None:
                raise Exception("Gemini Embedding API 返回了空结果")

            embeddings: list[list[float]] = []
            for embedding in result.embeddings:
                if embedding.values is None:
                    raise Exception("Gemini Embedding API 返回的向量为空")
                embeddings.append(embedding.values)
            return embeddings
        except APIError as e:
            raise Exception(f"Gemini Embedding API批量请求失败: {e.message}")

    def get_dim(self) -> int:
        """获取向量的维度"""
        return int(self.provider_config.get("embedding_dimensions", 768))

    async def terminate(self):
        if self.client:
            await self.client.aclose()
