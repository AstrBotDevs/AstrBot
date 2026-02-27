from astrbot.core.lang import t
from typing import cast

from xinference_client.client.restful.async_restful_client import (
    AsyncClient as Client,
)
from xinference_client.client.restful.async_restful_client import (
    AsyncRESTfulRerankModelHandle,
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
        self.model: AsyncRESTfulRerankModelHandle | None = None
        self.model_uid = None

    async def initialize(self) -> None:
        if self.api_key:
            logger.info(t("msg-1ec1e6e4"))
            self.client = Client(self.base_url, api_key=self.api_key)
        else:
            logger.info(t("msg-7bcb6e1b"))
            self.client = Client(self.base_url)

        try:
            running_models = await self.client.list_models()
            for uid, model_spec in running_models.items():
                if model_spec.get("model_name") == self.model_name:
                    logger.info(
                        t("msg-b0d1e564", res=self.model_name, uid=uid),
                    )
                    self.model_uid = uid
                    break

            if self.model_uid is None:
                if self.launch_model_if_not_running:
                    logger.info(t("msg-16965859", res=self.model_name))
                    self.model_uid = await self.client.launch_model(
                        model_name=self.model_name,
                        model_type="rerank",
                    )
                    logger.info(t("msg-7b1dfdd3"))
                else:
                    logger.warning(
                        t("msg-3fc7310e", res=self.model_name),
                    )
                    return

            if self.model_uid:
                self.model = cast(
                    AsyncRESTfulRerankModelHandle,
                    await self.client.get_model(self.model_uid),
                )

        except Exception as e:
            logger.error(t("msg-15f19a42", e=e))
            logger.debug(
                t("msg-01af1651", e=e),
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
            logger.error(t("msg-2607cc7a"))
            return []
        try:
            response = await self.model.rerank(documents, query, top_n)
            results = response.get("results", [])
            logger.debug(t("msg-3d28173b", response=response))

            if not results:
                logger.warning(
                    t("msg-4c63e1bd", response=response),
                )

            return [
                RerankResult(
                    index=result["index"],
                    relevance_score=result["relevance_score"],
                )
                for result in results
            ]
        except Exception as e:
            logger.error(t("msg-cac71506", e=e))
            logger.debug(t("msg-4135cf72", e=e), exc_info=True)
            return []

    async def terminate(self) -> None:
        """关闭客户端会话"""
        if self.client:
            logger.info(t("msg-ea2b36d0"))
            try:
                await self.client.close()
            except Exception as e:
                logger.error(t("msg-633a269f", e=e), exc_info=True)
