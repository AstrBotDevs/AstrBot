from openai import AsyncOpenAI

# 使用 openai 库内部引用的 httpx 模块，避免打包后 isinstance 校验失败
from openai._base_client import httpx as _openai_httpx

from astrbot import logger
from astrbot.core.utils.network_utils import create_proxy_client

from ..entities import ProviderType
from ..provider import EmbeddingProvider
from ..register import register_provider_adapter


@register_provider_adapter(
    "openai_embedding",
    "OpenAI API Embedding 提供商适配器",
    provider_type=ProviderType.EMBEDDING,
)
class OpenAIEmbeddingProvider(EmbeddingProvider):
    _EMBEDDING_MODEL_HINTS = (
        "embedding",
        "bge",
        "gte",
        "e5",
        "m3e",
        "multilingual-e5",
    )

    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.provider_config = provider_config
        self.provider_settings = provider_settings
        provider_id = provider_config.get("id", "unknown_id")
        http_client = create_proxy_client(
            "OpenAI Embedding",
            provider_config.get("proxy", ""),
            httpx_module=_openai_httpx,
        )
        api_base = (
            provider_config.get("embedding_api_base", "https://api.openai.com/v1")
            .strip()
            .removesuffix("/")
            .removesuffix("/embeddings")
        )
        if api_base:
            parsed = urlsplit(api_base)
            # 无 scheme 时 urlsplit 会把 host 当 path，需要补上 scheme
            if not parsed.scheme:
                api_base = f"https://{api_base}"
                parsed = urlsplit(api_base)
            # 只在纯域名（无路径或只有 /）时追加 /v1，带路径的地址保持原样
            # 这样智谱 /api/paas/v4、火山 /api/v3 等不会被破坏
            if not parsed.path or parsed.path == "/":
                api_base = f"{api_base}/v1"
        logger.info(f"[OpenAI Embedding] {provider_id} Using API Base: {api_base}")
        self.client = AsyncOpenAI(
            api_key=provider_config.get("embedding_api_key"),
            base_url=api_base,
            timeout=int(provider_config.get("timeout", 20)),
            http_client=self._http_client,
        )
        self.model = provider_config.get("embedding_model", "text-embedding-3-small")

    async def get_embedding(self, text: str) -> list[float]:
        """获取文本的嵌入"""
        kwargs = self._embedding_kwargs()
        embedding = await self.client.embeddings.create(
            input=text,
            model=self.model,
            **kwargs,
        )
        return embedding.data[0].embedding

    async def get_embeddings(self, text: list[str]) -> list[list[float]]:
        """批量获取文本的嵌入"""
        kwargs = self._embedding_kwargs()
        embeddings = await self.client.embeddings.create(
            input=text,
            model=self.model,
            **kwargs,
        )
        return [item.embedding for item in embeddings.data]

    async def get_models(self) -> list[str]:
        try:
            models = await self.client.models.list()
            all_model_ids = sorted(
                {model.id for model in models.data if getattr(model, "id", None)}
            )

            embedding_model_ids = [
                model_id
                for model_id in all_model_ids
                if self._looks_like_embedding_model(model_id)
            ]

            # Fall back to all model ids when no embedding-like names are detected.
            return embedding_model_ids or all_model_ids
        except Exception as e:
            raise Exception(f"获取嵌入模型列表失败: {e!s}") from e

    @classmethod
    def _looks_like_embedding_model(cls, model_id: str) -> bool:
        normalized = model_id.lower()
        return any(hint in normalized for hint in cls._EMBEDDING_MODEL_HINTS)

    def _embedding_kwargs(self) -> dict:
        """构建嵌入请求的可选参数"""
        kwargs = {}
        extra_body = {}
        dim_val = self.provider_config.get("embedding_dimensions")
        send_dimensions = self.provider_config.get("embedding_send_dimensions", True)
        if dim_val not in (None, "", 0) and send_dimensions:
            try:
                dim_int = int(dim_val)
                if dim_int > 0:
                    kwargs["dimensions"] = dim_int
            except (ValueError, TypeError):
                logger.warning(
                    f"embedding_dimensions in embedding configs is not a valid integer: '{self.provider_config['embedding_dimensions']}', ignored.",
                )

        input_type = self.provider_config.get("embedding_input_type")
        if input_type:
            extra_body["input_type"] = input_type

        if extra_body:
            kwargs["extra_body"] = extra_body
        return kwargs

    def get_dim(self) -> int:
        """获取向量的维度"""
        dim_val = self.provider_config.get("embedding_dimensions")
        if dim_val not in (None, ""):
            try:
                return int(dim_val)
            except (ValueError, TypeError):
                logger.warning(
                    f"embedding_dimensions in embedding configs is not a valid integer: '{dim_val}', ignored."
                )
        return 0

    async def terminate(self):
        if self.client:
            await self.client.close()
        if self._http_client:
            await self._http_client.aclose()
