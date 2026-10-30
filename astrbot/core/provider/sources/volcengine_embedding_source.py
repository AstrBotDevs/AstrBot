from ..entities import ProviderType
from ..register import register_provider_adapter
from .openai_embedding_source import OpenAIEmbeddingProvider


@register_provider_adapter(
    "volcengine_embedding",
    "Volcengine Doubao Embedding provider adapter",
    provider_type=ProviderType.EMBEDDING,
)
class VolcengineEmbeddingProvider(OpenAIEmbeddingProvider):
    """Embed texts with Doubao vision models via Ark's multimodal endpoint."""

    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        """Initialize the Ark client with the existing OpenAI transport.

        Args:
            provider_config: Provider credentials, model, dimensions and transport settings.
            provider_settings: Shared provider settings.
        """
        config = provider_config.copy()
        # Agent Plan uses https://ark.cn-beijing.volces.com/api/plan/v3
        # with its dedicated API key and model name doubao-embedding-vision.
        # Standard Ark uses /api/v3 and a versioned model name or endpoint ID.
        config["embedding_api_base"] = (
            (
                config.get("embedding_api_base")
                or "https://ark.cn-beijing.volces.com/api/v3"
            )
            .strip()
            .rstrip("/")
            .removesuffix("/embeddings/multimodal")
        )
        config["embedding_model"] = (
            config.get("embedding_model") or "doubao-embedding-vision-251215"
        )
        config.setdefault("embedding_dimensions", 1024)
        super().__init__(config, provider_settings)
        self.set_model(self.model)

    async def get_embedding(self, text: str) -> list[float]:
        """Get one text vector from the native multimodal response.

        Args:
            text: Text to embed.

        Returns:
            The dense embedding vector.

        Raises:
            ValueError: If the response does not contain a dense vector.
        """
        payload = {
            "model": self.model,
            "input": [{"type": "text", "text": text}],
            "encoding_format": "float",
        }
        dimensions = self.get_dim()
        if dimensions > 0:
            payload["dimensions"] = dimensions
        response = await self.client.post(
            "/embeddings/multimodal", body=payload, cast_to=dict[str, object]
        )
        data = response.get("data")
        embedding = data.get("embedding") if isinstance(data, dict) else None
        if not isinstance(embedding, list) or not embedding:
            raise ValueError("Volcengine Embedding response contains no dense vector")
        return embedding

    async def get_embeddings(self, text: list[str]) -> list[list[float]]:
        """Get a separate vector for each text in input order.

        Args:
            text: Independent texts to embed.

        Returns:
            Embedding vectors in the same order as the input texts.
        """
        # Multimodal inputs in one request are fused into a single vector.
        # The base provider already limits concurrency across document batches.
        return [await self.get_embedding(item) for item in text]
