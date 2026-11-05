import aiohttp

from astrbot import logger

from ..entities import ProviderType
from ..provider import EmbeddingProvider
from ..register import register_provider_adapter


@register_provider_adapter(
    "nvidia_embedding",
    "NVIDIA NIM Embedding 提供商适配器",
    provider_type=ProviderType.EMBEDDING,
)
class NvidiaEmbeddingProvider(EmbeddingProvider):
    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.provider_config = provider_config
        self.provider_settings = provider_settings

        self.api_key = provider_config.get("embedding_api_key", "")
        self.base_url = (
            provider_config.get(
                "embedding_api_base", "https://integrate.api.nvidia.com/v1"
            )
            .rstrip("/")
            .removesuffix("/embeddings")
        )
        self.timeout = int(provider_config.get("timeout", 20))
        self.model = provider_config.get(
            "embedding_model", "nvidia/nemotron-3-embed-1b"
        )
        # 文档侧 input_type。索引阶段用 passage。
        self.input_type = provider_config.get("input_type", "passage")
        # 查询侧 input_type。NV-Embed-QA / E5 / nemotron 这类模型必须区分
        # passage 与 query，混用会显著降低检索准确率。
        self.query_input_type = provider_config.get("query_input_type") or "query"

        proxy = provider_config.get("proxy", "")
        self.proxy = proxy
        if proxy:
            logger.info(f"[NVIDIA Embedding] Using proxy: {proxy}")

        self.client = None
        self.set_model(self.model)

    async def _get_client(self):
        if self.client is None or self.client.closed:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self.client = aiohttp.ClientSession(
                headers={**self.request_headers, **headers},
                timeout=timeout,
            )
        return self.client

    def _build_payload(
        self,
        text: str | list[str],
        input_type: str | None = None,
    ) -> dict:
        if isinstance(text, str):
            input_text = [text]
        else:
            input_text = text

        return {
            "input": input_text,
            "model": self.model,
            "input_type": input_type or self.input_type,
            "encoding_format": "float",
        }

    def _parse_response(self, response_data: dict) -> list[list[float]]:
        data = response_data.get("data", [])
        embeddings = []
        for item in data:
            embedding = item.get("embedding", [])
            embeddings.append(embedding)
        return embeddings

    async def get_embedding(self, text: str) -> list[float]:
        """单条文本按文档侧（passage）语义嵌入。"""
        embeddings = await self.get_embeddings([text])
        return embeddings[0] if embeddings else []

    async def get_query_embedding(self, text: str) -> list[float]:
        """检索查询按 query 侧语义嵌入。

        NVIDIA 文档明确要求检索查询使用 ``input_type=query``，混用 passage
        会显著降低检索准确率。
        """
        embeddings = await self._get_embeddings_with_type([text], self.query_input_type)
        return embeddings[0] if embeddings else []

    async def get_embeddings(self, text: list[str]) -> list[list[float]]:
        """批量按文档侧（passage）语义嵌入。"""
        return await self._get_embeddings_with_type(text, self.input_type)

    async def _get_embeddings_with_type(
        self,
        text: list[str],
        input_type: str,
    ) -> list[list[float]]:
        client = await self._get_client()
        if not client or client.closed:
            raise Exception("[NVIDIA Embedding] Client session not initialized")

        payload = self._build_payload(text, input_type=input_type)
        request_url = f"{self.base_url}/embeddings"

        try:
            async with client.post(
                request_url, json=payload, proxy=self.proxy or None
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(
                        f"[NVIDIA Embedding] API Error: {response.status} - {error_text}"
                    )
                    raise Exception(
                        f"NVIDIA Embedding API request failed: HTTP {response.status} - {error_text}"
                    )

                response_data = await response.json()
                embeddings = self._parse_response(response_data)

                usage = response_data.get("usage", {})
                total_tokens = usage.get("total_tokens", 0)
                if total_tokens > 0:
                    logger.debug(f"[NVIDIA Embedding] Token usage: {total_tokens}")

                return embeddings

        except aiohttp.ClientError as e:
            logger.error(f"[NVIDIA Embedding] Network error: {e}")
            raise
        except Exception as e:
            logger.error(f"[NVIDIA Embedding] Error: {e}", exc_info=True)
            raise

    def get_dim(self) -> int:
        if "embedding_dimensions" in self.provider_config:
            try:
                return int(self.provider_config["embedding_dimensions"])
            except (ValueError, TypeError):
                logger.warning(
                    f"embedding_dimensions in embedding configs is not a valid integer: "
                    f"'{self.provider_config['embedding_dimensions']}', ignored."
                )
        return 0

    async def terminate(self):
        if self.client and not self.client.closed:
            await self.client.close()
            self.client = None
