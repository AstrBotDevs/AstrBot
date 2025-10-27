import asyncio
from xinference_client import RESTfulClient as Client
from astrbot import logger
from ..provider import RerankProvider
from ..register import register_provider_adapter
from ..entities import ProviderType, RerankResult


@register_provider_adapter(
    "xinference_rerank",
    "Xinference Rerank 适配器",
    provider_type=ProviderType.RERANK,
)
class XinferenceRerankProvider(RerankProvider):
    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.provider_config = provider_config
        self.provider_settings = provider_settings
        self.auth_key = provider_config.get("rerank_api_key", "")
        self.base_url = provider_config.get("rerank_api_base", "http://127.0.0.1:8000")
        self.base_url = self.base_url.rstrip("/")
        self.timeout = provider_config.get("timeout", 20)
        self.model_name = provider_config.get("rerank_model", "BAAI/bge-reranker-base")
        self.api_key = provider_config.get("rerank_api_key")

        if self.api_key:
            logger.info("Xinference Rerank: Using API key for authentication.")
            self.client = Client(self.base_url, api_key=self.api_key)
        else:
            logger.info("Xinference Rerank: No API key provided.")
            self.client = Client(self.base_url)

        self.model_uid = None

        running_models = self.client.list_models()
        for uid, model_spec in running_models.items():
            if model_spec.get("model_name") == self.model_name:
                logger.info(f"Model '{self.model_name}' is already running with UID: {uid}")
                self.model_uid = uid
                break

        if self.model_uid is None:
            logger.info(f"Launching {self.model_name} model...")
            self.model_uid = self.client.launch_model(
                model_name=self.model_name,
                model_type="rerank"
            )
            logger.info("Model launched.")

        self.model = self.client.get_model(self.model_uid)


    async def rerank(
        self, query: str, documents: list[str], top_n: int | None = None
    ) -> list[RerankResult]:

        try:
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None, self.model.rerank, documents, query, top_n
            )
            results = response.get("results", [])

            if not results:
                logger.warning(
                    f"Rerank API 返回了空的列表数据。原始响应: {response}"
                )

            return [
                RerankResult(
                    index=result["index"],
                    relevance_score=result["relevance_score"],
                )
                for result in results
            ]
        except Exception as e:
            logger.error(f"Xinference rerank failed: {e}")
            logger.debug(f"Xinference rerank failed with exception: {e}", exc_info=True)
            return []

    async def terminate(self) -> None:
        """关闭客户端会话"""
        pass
