from xinference_client.client.restful.async_restful_client import (
    AsyncClient as Client,
)

from astrbot import logger

from ..entities import ProviderType, RerankResult
from ..provider import RerankProvider
from ..register import register_provider_adapter


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
        self.base_url = provider_config.get("rerank_api_base", "http://127.0.0.1:8000")
        self.base_url = self.base_url.rstrip("/")
        self.timeout = provider_config.get("timeout", 20)
        self.model_name = provider_config.get("rerank_model", "BAAI/bge-reranker-base")
        self.api_key = provider_config.get("rerank_api_key")
        self.launch_model_if_not_running = provider_config.get(
            "launch_model_if_not_running",
            False,
        )
        self.client = None
        self.model = None
        self.model_uid = None

    async def initialize(self):
        if self.api_key:
            logger.info("Xinference Rerank: Using API key for authentication.")
            self.client = Client(self.base_url, api_key=self.api_key)
        else:
            logger.info("Xinference Rerank: No API key provided.")
            self.client = Client(self.base_url)

        try:
            running_models = await self.client.list_models()
            for uid, model_spec in running_models.items():
                if model_spec.get("model_name") == self.model_name:
                    logger.info(
                        f"Model '{self.model_name}' is already running with UID: {uid}",
                    )
                    self.model_uid = uid
                    break

            if self.model_uid is None:
                if self.launch_model_if_not_running:
                    logger.info(f"Launching {self.model_name} model...")
                    self.model_uid = await self.client.launch_model(
                        model_name=self.model_name,
                        model_type="rerank",
                    )
                    logger.info("Model launched.")
                else:
                    logger.warning(
                        f"Model '{self.model_name}' is not running and auto-launch is disabled. Provider will not be available.",
                    )
                    return

            if self.model_uid:
                self.model = await self.client.get_model(self.model_uid)

        except Exception as e:
            logger.error(f"Failed to initialize Xinference model: {e}")
            logger.debug(
                f"Xinference initialization failed with exception: {e}",
                exc_info=True,
            )
            self.model = None

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int | None = None,
    ) -> list[RerankResult]:
        if not self.model:
            logger.error("Xinference rerank model is not initialized.")
            return []
        try:
            response = await self.model.rerank(documents, query, top_n)
            results = response.get("results", [])
            logger.debug(f"Rerank API response: {response}")

            if not results:
                logger.warning(
                    f"Rerank API returned an empty list. Original response: {response}",
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
        if self.client:
            logger.info("Closing Xinference rerank client...")
            try:
                await self.client.close()
            except Exception as e:
                logger.error(f"Failed to close Xinference client: {e}", exc_info=True)
