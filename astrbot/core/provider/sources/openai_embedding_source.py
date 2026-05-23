from openai import AsyncOpenAI

# 使用 openai 库内部引用的 httpx 模块，避免打包后 isinstance 校验失败
from openai._base_client import httpx as _openai_httpx

from astrbot import logger
from astrbot.core.utils.network_utils import create_proxy_client

from ..entities import ProviderType
from ..provider import EmbeddingProvider
from ..register import register_provider_adapter
from .embedding_utils import (
    infer_embedding_dimension_from_model,
    parse_configured_embedding_dimension,
)


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
        
        proxy = provider_config.get("proxy", "")
        provider_id = provider_config.get("id", "unknown_id")
        http_client = None
        if proxy:
            logger.info(f"[OpenAI Embedding] {provider_id} Using proxy: {proxy}")
            http_client = httpx.AsyncClient(proxy=proxy)
        
        api_base = (
            provider_config.get("embedding_api_base", "https://api.openai.com/v1")
            .strip()
            .removesuffix("/")
            .removesuffix("/embeddings")
        )
        if api_base and not api_base.endswith("/v1") and not api_base.endswith("/v4"):
            # /v4 see #5699
            api_base = api_base + "/v1"
        
        # [新增] 保存处理后的 api_base 并转换为小写，用于后续特征比对
        self.api_base_normalized = api_base.lower()
        
        logger.info(f"[OpenAI Embedding] {provider_id} Using API Base: {api_base}")
        
        self.client = AsyncOpenAI(
            api_key=provider_config.get("embedding_api_key"),
            base_url=api_base,
            timeout=int(provider_config.get("timeout", 20)),
            http_client=self._http_client,
        )
        self.model = provider_config.get("embedding_model", "text-embedding-3-small")
        
        # [新增] 运行时状态标记：一旦触发 400 错误将此设为 True
        self._is_vllm_detected = False

    def _is_vllm(self) -> bool:
        """检测是否是 vLLM（vLLM 不支持 dimensions 参数）"""
        # 1. 优先检查运行时已证实的标记
        if self._is_vllm_detected:
            return True
        
        # 2. [核心修改] 检查 API Key 是否为 "vllm"
        api_key = self.provider_config.get("embedding_api_key", "")
        if api_key and api_key.lower() == "vllm":
            logger.info("[OpenAI Embedding] vLLM mode enabled by API Key 'vllm'.")
            return True
        
        # 3. 辅助检查：ID 或 URL 中是否显式包含 "vllm"
        provider_id = self.provider_config.get("id", "").lower()
        api_base = self.api_base_normalized.lower()
        if "vllm" in provider_id or "vllm" in api_base:
            logger.info(f"[OpenAI Embedding] Detected vLLM by id/api_base: {provider_id}")
            return True
        
        # 4. 移除对端口 (8000, 8001) 的静态判定，避免误伤其他兼容服务
        return False

    def _mark_as_vllm(self) -> None:
        """标记此实例为vLLM（通过运行时错误检测出来的）"""
        self._is_vllm_detected = True
        logger.info("[OpenAI Embedding] Marked as vLLM (runtime detection via error)")

    async def get_embedding(self, text: str) -> list[float]:
        """获取文本的嵌入"""
        kwargs = self._embedding_kwargs()
        embedding = await self._request_with_vllm_retry(text, kwargs, batch=False)
        return embedding.data[0].embedding

    async def get_embeddings(self, text: list[str]) -> list[list[float]]:
        """批量获取文本的嵌入"""
        kwargs = self._embedding_kwargs()
        embeddings = await self._request_with_vllm_retry(text, kwargs, batch=True)
        return [item.embedding for item in embeddings.data]

    async def _request_with_vllm_retry(
        self,
        input_data: str | list[str],
        kwargs: dict,
        *,
        batch: bool,
    ):
        try:
            return await self.client.embeddings.create(
                input=input_data,
                model=self.model,
                **kwargs,
            )
        except Exception as exc:
            if not self._should_retry_without_dimensions(exc, kwargs):
                raise

            if batch:
                logger.warning(
                    f"[OpenAI Embedding] Detected vLLM dimensions error in batch mode, retrying without dimensions: {exc}"
                )
            else:
                logger.warning(
                    f"[OpenAI Embedding] Detected vLLM dimensions error, retrying without dimensions parameter: {exc}"
                )

            kwargs_retry = {k: v for k, v in kwargs.items() if k != "dimensions"}
            try:
                embeddings = await self.client.embeddings.create(
                    input=input_data,
                    model=self.model,
                    **kwargs_retry,
                )
            except Exception as retry_error:
                if batch:
                    logger.error(
                        f"[OpenAI Embedding] Batch retry without dimensions also failed: {retry_error}"
                    )
                else:
                    logger.error(
                        f"[OpenAI Embedding] Retry without dimensions also failed: {retry_error}"
                    )
                raise

            if batch:
                logger.info(
                    "[OpenAI Embedding] Successfully retrieved batch embeddings without dimensions parameter"
                )
            else:
                logger.info(
                    "[OpenAI Embedding] Successfully retrieved embedding without dimensions parameter, marking as vLLM"
                )

            self._mark_as_vllm()
            return embeddings

    def _should_retry_without_dimensions(self, exc: Exception, kwargs: dict) -> bool:
        if not kwargs.get("dimensions"):
            return False

        error_msg = str(exc).lower()
        return "matryoshka" in error_msg or "dimensions" in error_msg

    def _configured_dimension(self) -> int | None:
        provider_id = self.provider_config.get("id", "unknown")
        return parse_configured_embedding_dimension(
            self.provider_config.get("embedding_dimensions", ""),
            provider_label="OpenAI Embedding",
            provider_id=provider_id,
        )

    def _embedding_kwargs(self) -> dict:
        """构建嵌入请求的可选参数"""
        kwargs = {}
        provider_id = self.provider_config.get("id", "unknown")
        embedding_dim_config = self.provider_config.get("embedding_dimensions", "")
        # 检查是否是vLLM
        is_vllm = self._is_vllm()
        if is_vllm:
            logger.info(
                f"[OpenAI Embedding] {provider_id}: Detected vLLM, skipping dimensions parameter (config value: '{embedding_dim_config}')"
            )
            return kwargs
        # 非vLLM服务（OpenAI等）支持dimensions，读取配置
        configured_dim = self._configured_dimension()
        if configured_dim is not None:
            kwargs["dimensions"] = configured_dim
            logger.info(
                f"[OpenAI Embedding] {provider_id}: Added dimensions parameter: {configured_dim}"
            )
        elif embedding_dim_config in (None, ""):
            logger.info(
                f"[OpenAI Embedding] {provider_id}: No embedding_dimensions configured, API will use default"
            )
        return kwargs

    def get_dim(self) -> int:
        """获取向量的维度"""
        provider_id = self.provider_config.get("id", "unknown")
        embedding_dim_config = self.provider_config.get("embedding_dimensions", "")

        configured_dim = self._configured_dimension()
        if configured_dim is not None:
            logger.info(
                f"[OpenAI Embedding] {provider_id}: Dimension from config: {configured_dim}"
            )
            return configured_dim

        model = self.provider_config.get("embedding_model", "")
        inferred_dim = infer_embedding_dimension_from_model(model)
        if inferred_dim:
            logger.info(
                f"[OpenAI Embedding] {provider_id}: Inferred dimension {inferred_dim} from model: {str(model).lower()}"
            )
            return inferred_dim

        logger.warning(
            f"[OpenAI Embedding] {provider_id}: Could not determine dimension (model: {str(model).lower()}, config: '{embedding_dim_config}')"
        )
        return 0

    async def terminate(self):
        if self.client:
            await self.client.close()
        if self._http_client:
            await self._http_client.aclose()
