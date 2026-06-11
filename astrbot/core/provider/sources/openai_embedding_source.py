from urllib.parse import urlparse

import httpx
import openai
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

        provider_id = provider_config.get("id", "unknown_id")

        # 1. 强制校验 API Key (Fail-Fast)
        api_key: str = provider_config.get("embedding_api_key", "")
        if not api_key:
            raise ValueError(
                f"OpenAI embedding provider [{provider_id}] 配置错误: 缺少必需成 'embedding_api_key'"
            )

        # 2. 安全获取并转换 timeout 避免空字符串导致 int() 崩溃
        raw_timeout = provider_config.get("timeout", 20)
        try:
            timeout_val = int(raw_timeout) if raw_timeout else 20
        except (ValueError, TypeError):
            timeout_val = 20

        proxy = provider_config.get("proxy", "")
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

        logger.info(f"[OpenAI Embedding] {provider_id} Using API Base: {api_base}")

        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=api_base,
            timeout=timeout_val,
            http_client=http_client,
        )
        self.model = provider_config.get("embedding_model", "text-embedding-3-small")

    async def get_embedding(self, text: str) -> list[float]:
        """获取文本的嵌入"""
        # 3. 拦截空文本防 400 报错
        if not text or not text.strip():
            raise ValueError("输入文本不能为空")

        kwargs = self._embedding_kwargs()

        try:
            embedding = await self.client.embeddings.create(
                input=text,
                model=self.model,
                **kwargs,
            )
            return embedding.data[0].embedding
        except openai.OpenAIError as e:
            # 4. 包装规范异常，使用 from e 保留原始调用栈
            raise Exception(f"OpenAI Embedding API 请求失败: {e}") from e

    async def get_embeddings(self, text: list[str]) -> list[list[float]]:
        """批量获取文本的嵌入"""
        # 5. 拦截空列表和内部脏数据，与 get_embedding 逻辑保持一致
        if not text:
            raise ValueError("批量输入列表不能为空")

        if any(not s or not s.strip() for s in text):
            raise ValueError("批量输入文本列表中不能包含空文本")

        kwargs = self._embedding_kwargs()

        try:
            embeddings = await self.client.embeddings.create(
                input=text,
                model=self.model,
                **kwargs,
            )
            return [item.embedding for item in embeddings.data]
        except openai.OpenAIError as e:
            raise Exception(f"OpenAI Embedding API 批量请求失败: {e}") from e

    def _embedding_kwargs(self) -> dict:
        """构建嵌入请求的可选参数"""
        kwargs = {}
        if "embedding_dimensions" in self.provider_config:
            try:
                kwargs["dimensions"] = int(self.provider_config["embedding_dimensions"])
            except (ValueError, TypeError):
                logger.warning(
                    f"embedding_dimensions in embedding configs is not a valid integer: '{self.provider_config['embedding_dimensions']}', ignored."
                )

        # Fix: SiliconFlow provider does not support dimensions parameter, except for Qwen models.
        provider_api_base = self.provider_config.get("embedding_api_base", "")
        provider_id = self.provider_config.get("id", "unknown_id")
        if provider_api_base:
            api_base = provider_api_base.strip().lower()
            # 兼容不带 http:// 或 https:// 头的 api_base，确保 urlparse 能正常解析 hostname
            if not api_base.startswith(("http://", "https://")):
                api_base = "https://" + api_base
            hostname = urlparse(api_base).hostname or ""

            if hostname in {
                "api.siliconflow.cn",
                "api.siliconflow.com",
            } and not self.model.lower().startswith("qwen"):
                # For SiliconFlow and Non-Qwen models, dimensions parameter is not supported, so remove it.
                removed_dimensions = kwargs.pop("dimensions", None)
                if removed_dimensions is not None:
                    # Log a warning message if dimensions parameter is removed.
                    logger.warning(
                        f"dimensions not supported for model '{self.model}' of provider '{provider_id}' "
                        f"as SiliconFlow does not support this parameter for non-Qwen models: '{removed_dimensions}'."
                    )
        return kwargs

    def get_dim(self) -> int:
        """获取向量的维度"""
        if "embedding_dimensions" in self.provider_config:
            try:
                return int(self.provider_config["embedding_dimensions"])
            except (ValueError, TypeError):
                logger.warning(
                    f"embedding_dimensions in embedding configs is not a valid integer: '{self.provider_config['embedding_dimensions']}', ignored."
                )
        return 0

    async def terminate(self):
        """释放资源"""
        if getattr(self, "client", None):
            await self.client.close()
