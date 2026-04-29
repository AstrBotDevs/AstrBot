import httpx
from openai import AsyncOpenAI
from astrbot import logger
from ..entities import ProviderType
from ..provider import EmbeddingProvider
from ..register import register_provider_adapter


@register_provider_adapter(
    "openai_embedding",
    "OpenAI API Embedding 提供商适配器",
    provider_type=ProviderType.EMBEDDING,
)
class OpenAIEmbeddingProvider(EmbeddingProvider):
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
            http_client=http_client,
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
        try:
            embedding = await self.client.embeddings.create(
                input=text,
                model=self.model,
                **kwargs,
            )
            return embedding.data[0].embedding
        except Exception as e:
            # 如果包含"matryoshka"或"dimensions"相关的错误，说明vLLM不支持该参数
            # 尝试不带dimensions重试
            error_msg = str(e).lower()
            if ("matryoshka" in error_msg or "dimensions" in error_msg) and kwargs.get("dimensions"):
                logger.warning(
                    f"[OpenAI Embedding] Detected vLLM dimensions error, retrying without dimensions parameter: {e}"
                )
                kwargs_retry = {k: v for k, v in kwargs.items() if k != "dimensions"}
                try:
                    embedding = await self.client.embeddings.create(
                        input=text,
                        model=self.model,
                        **kwargs_retry,
                    )
                    logger.info(
                        "[OpenAI Embedding] Successfully retrieved embedding without dimensions parameter, marking as vLLM"
                    )
                    # 标记为vLLM以便后续调用也跳过dimensions
                    self._mark_as_vllm()
                    return embedding.data[0].embedding
                except Exception as retry_error:
                    logger.error(
                        f"[OpenAI Embedding] Retry without dimensions also failed: {retry_error}"
                    )
                    raise retry_error
            else:
                raise

    async def get_embeddings(self, text: list[str]) -> list[list[float]]:
        """批量获取文本的嵌入"""
        kwargs = self._embedding_kwargs()
        try:
            embeddings = await self.client.embeddings.create(
                input=text,
                model=self.model,
                **kwargs,
            )
            return [item.embedding for item in embeddings.data]
        except Exception as e:
            # 如果包含"matryoshka"或"dimensions"相关的错误，说明vLLM不支持该参数
            # 尝试不带dimensions重试
            error_msg = str(e).lower()
            if ("matryoshka" in error_msg or "dimensions" in error_msg) and kwargs.get("dimensions"):
                logger.warning(
                    f"[OpenAI Embedding] Detected vLLM dimensions error in batch mode, retrying without dimensions: {e}"
                )
                kwargs_retry = {k: v for k, v in kwargs.items() if k != "dimensions"}
                try:
                    embeddings = await self.client.embeddings.create(
                        input=text,
                        model=self.model,
                        **kwargs_retry,
                    )
                    logger.info(
                        "[OpenAI Embedding] Successfully retrieved batch embeddings without dimensions parameter"
                    )
                    # 标记为vLLM以便后续调用也跳过dimensions
                    self._mark_as_vllm()
                    return [item.embedding for item in embeddings.data]
                except Exception as retry_error:
                    logger.error(
                        f"[OpenAI Embedding] Batch retry without dimensions also failed: {retry_error}"
                    )
                    raise retry_error
            else:
                raise

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
        if embedding_dim_config and embedding_dim_config != "":
            try:
                dim_value = int(embedding_dim_config)
                kwargs["dimensions"] = dim_value
                logger.info(
                    f"[OpenAI Embedding] {provider_id}: Added dimensions parameter: {dim_value}"
                )
            except (ValueError, TypeError):
                logger.warning(
                    f"[OpenAI Embedding] {provider_id}: embedding_dimensions is not a valid integer: '{embedding_dim_config}', ignored."
                )
        else:
            logger.info(
                f"[OpenAI Embedding] {provider_id}: No embedding_dimensions configured, API will use default"
            )
        return kwargs

    def get_dim(self) -> int:
        """获取向量的维度"""
        provider_id = self.provider_config.get("id", "unknown")
        # 首先尝试从config读取
        embedding_dim_config = self.provider_config.get("embedding_dimensions", "")
        if embedding_dim_config and embedding_dim_config != "":
            try:
                dim = int(embedding_dim_config)
                if dim > 0:
                    logger.info(
                        f"[OpenAI Embedding] {provider_id}: Dimension from config: {dim}"
                    )
                    return dim
            except (ValueError, TypeError):
                logger.warning(
                    f"[OpenAI Embedding] {provider_id}: embedding_dimensions is not a valid integer: '{embedding_dim_config}', trying model inference"
                )
        # config为空或无效时根据模型名推断维度
        # 这样Living Memory可以在自动检测后匹配正确的维度
        model = self.provider_config.get("embedding_model", "").lower()
        model_dims = {
            "bge-m3": 1024,
            "bge-large-en-v1.5": 1024,
            "bge-large-zh-v1.5": 1024,
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
            "text-embedding-ada-002": 1536,
        }
        for model_key, dim in model_dims.items():
            if model_key in model:
                logger.info(
                    f"[OpenAI Embedding] {provider_id}: Inferred dimension {dim} from model: {model}"
                )
                return dim
        # 无法推断时返回0（Living Memory会检测实际维度）
        logger.warning(
            f"[OpenAI Embedding] {provider_id}: Could not determine dimension (model: {model}, config: '{embedding_dim_config}')"
        )
        return 0

    async def terminate(self):
        if self.client:
            await self.client.close()
