from __future__ import annotations

from ipaddress import ip_address
from typing import Any
from urllib.parse import urlparse

import httpx
from openai import AsyncOpenAI

from astrbot import logger

from ..entities import ProviderType
from ..provider import EmbeddingProvider
from ..register import register_provider_adapter


_COMMON_MODEL_DIMENSIONS = {
    "bge-m3": 1024,
    "bge-large-en-v1.5": 1024,
    "bge-large-zh-v1.5": 1024,
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}


@register_provider_adapter(
    "vllm_embedding",
    "vLLM Embedding 提供商适配器",
    provider_type=ProviderType.EMBEDDING,
    provider_display_name="vLLM Embedding",
)
class VLLMEmbeddingProvider(EmbeddingProvider):
    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.provider_config = provider_config
        self.provider_settings = provider_settings
        self.timeout = int(provider_config.get("timeout", 20) or 20)
        self.model = str(provider_config.get("embedding_model", "") or "").strip()
        self.set_model(self.model)
        self._force_direct_transport = self._should_force_direct_transport()

        self._detected_dimension: int | None = None
        self._resolved_request_model: str | None = None
        self._direct_client_ready = self._force_direct_transport

        self.client = AsyncOpenAI(
            api_key=provider_config.get("embedding_api_key"),
            base_url=self._effective_api_base(),
            timeout=self.timeout,
            http_client=self._build_http_client(),
        )

    async def get_embedding(self, text: str) -> list[float]:
        await self._ensure_runtime_ready()
        request_model = await self._resolve_request_model()
        logger.info(
            "[vLLM Embedding] %s 发起单条 embedding 请求，model=%s，text_len=%s，跳过 dimensions。",
            self._provider_id(),
            request_model,
            len(text),
        )
        embedding = await self.client.embeddings.create(
            input=text,
            model=request_model,
        )
        vector = embedding.data[0].embedding
        self._cache_detected_dimension(len(vector))
        return vector

    async def get_embeddings(self, text: list[str]) -> list[list[float]]:
        await self._ensure_runtime_ready()
        request_model = await self._resolve_request_model()
        total_chars = sum(len(item) for item in text)
        logger.info(
            "[vLLM Embedding] %s 发起批量 embedding 请求，model=%s，batch=%s，total_chars=%s，跳过 dimensions。",
            self._provider_id(),
            request_model,
            len(text),
            total_chars,
        )
        embeddings = await self.client.embeddings.create(
            input=text,
            model=request_model,
        )
        vectors = [item.embedding for item in embeddings.data]
        if vectors:
            self._cache_detected_dimension(len(vectors[0]))
        return vectors

    def get_dim(self) -> int:
        configured_dim = self._configured_dimension()
        if configured_dim:
            return configured_dim
        if self._detected_dimension:
            return self._detected_dimension
        inferred_dim = self._infer_dimension_from_model(self.model)
        if inferred_dim:
            return inferred_dim
        return 0

    async def terminate(self) -> None:
        if self.client:
            await self.client.close()

    def _build_http_client(self) -> httpx.AsyncClient | None:
        proxy = str(self.provider_config.get("proxy", "") or "").strip()
        if proxy:
            logger.info("[vLLM Embedding] %s 使用显式代理: %s", self._provider_id(), proxy)
            return httpx.AsyncClient(proxy=proxy, timeout=self.timeout)
        if self._force_direct_transport:
            return httpx.AsyncClient(timeout=self.timeout, trust_env=False)
        return None

    async def _ensure_runtime_ready(self) -> None:
        if self._direct_client_ready or not self._should_force_direct_transport():
            return

        old_client = self.client
        self.client = AsyncOpenAI(
            api_key=self.provider_config.get("embedding_api_key"),
            base_url=self._effective_api_base(),
            timeout=self.timeout,
            http_client=httpx.AsyncClient(timeout=self.timeout, trust_env=False),
        )
        self._direct_client_ready = True

        logger.info(
            "[vLLM Embedding] %s 检测到本地/内网端点，已切换为 trust_env=False 的直连 client。",
            self._provider_id(),
        )

        if old_client is not None and old_client is not self.client:
            try:
                await old_client.close()
            except Exception:
                logger.debug("[vLLM Embedding] %s 关闭旧 client 失败，已忽略。", self._provider_id())

    async def _resolve_request_model(self) -> str:
        if self._resolved_request_model:
            return self._resolved_request_model

        configured_model = self.model
        if not configured_model:
            self._resolved_request_model = configured_model
            return configured_model

        available_models = await self._list_vllm_models()
        resolved_model = self._match_served_model(configured_model, available_models)
        if resolved_model:
            self._resolved_request_model = resolved_model
            if resolved_model != configured_model:
                logger.info(
                    "[vLLM Embedding] %s 已将模型名 %s 对齐到 served-model-name %s。",
                    self._provider_id(),
                    configured_model,
                    resolved_model,
                )
            return resolved_model

        basename_model = configured_model.rsplit("/", 1)[-1].strip()
        if basename_model and basename_model != configured_model:
            self._resolved_request_model = basename_model
            logger.warning(
                "[vLLM Embedding] %s 未能从 /models 精确匹配 %s，回退为 %s。",
                self._provider_id(),
                configured_model,
                basename_model,
            )
            return basename_model

        self._resolved_request_model = configured_model
        return configured_model

    async def _list_vllm_models(self) -> list[dict[str, str]]:
        try:
            models = await self.client.models.list()
        except Exception as exc:
            logger.warning(
                "[vLLM Embedding] %s 拉取 /models 失败，将直接使用配置模型名: %s",
                self._provider_id(),
                exc,
            )
            return []

        results: list[dict[str, str]] = []
        for item in getattr(models, "data", []) or []:
            model_id = str(getattr(item, "id", "") or "").strip()
            model_root = str(getattr(item, "root", "") or "").strip()
            if model_id:
                results.append({"id": model_id, "root": model_root})
        return results

    def _match_served_model(
        self,
        configured_model: str,
        available_models: list[dict[str, str]],
    ) -> str | None:
        normalized_configured = configured_model.lower()
        basename_model = configured_model.rsplit("/", 1)[-1].strip().lower()

        for item in available_models:
            model_id = str(item.get("id", "") or "").strip()
            model_root = str(item.get("root", "") or "").strip()
            if model_id.lower() == normalized_configured:
                return model_id
            if model_root and model_root.lower() == normalized_configured:
                return model_id
            if basename_model and model_id.lower() == basename_model:
                return model_id
        return None

    def _configured_dimension(self) -> int | None:
        raw_dimension = self.provider_config.get("embedding_dimensions", "")
        if raw_dimension in (None, ""):
            return None
        try:
            dimension = int(raw_dimension)
        except (TypeError, ValueError):
            logger.warning(
                "[vLLM Embedding] %s 的 embedding_dimensions 不是有效整数: %r",
                self._provider_id(),
                raw_dimension,
            )
            return None
        return dimension if dimension > 0 else None

    def _infer_dimension_from_model(self, model_name: Any) -> int | None:
        normalized_model = str(model_name or "").strip().lower()
        for model_key, dimension in _COMMON_MODEL_DIMENSIONS.items():
            if model_key in normalized_model:
                return dimension
        return None

    def _cache_detected_dimension(self, dimension: int) -> None:
        if isinstance(dimension, int) and dimension > 0:
            self._detected_dimension = dimension

    def _effective_api_base(self) -> str:
        api_base = str(
            self.provider_config.get("embedding_api_base", "http://127.0.0.1:8000/v1")
            or "http://127.0.0.1:8000/v1"
        ).strip()
        api_base = api_base.removesuffix("/").removesuffix("/embeddings")
        if api_base and not api_base.endswith("/v1") and not api_base.endswith("/v4"):
            api_base = api_base + "/v1"
        return api_base

    def _should_force_direct_transport(self) -> bool:
        if str(self.provider_config.get("proxy", "") or "").strip():
            return False

        host = (urlparse(self._effective_api_base()).hostname or "").strip().lower()
        if not host:
            return False
        if host in {"localhost", "127.0.0.1", "::1", "host.docker.internal"}:
            return True
        try:
            parsed_host = ip_address(host)
        except ValueError:
            return False
        return parsed_host.is_loopback or parsed_host.is_private

    def _provider_id(self) -> str:
        return str(self.provider_config.get("id", "unknown") or "unknown")