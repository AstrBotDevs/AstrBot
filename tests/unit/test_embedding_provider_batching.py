import pytest

from astrbot.core.provider.provider import EmbeddingProvider


class FakeEmbeddingProvider(EmbeddingProvider):
    def __init__(self, provider_config: dict | None = None) -> None:
        super().__init__(provider_config or {}, {})
        self.batches: list[list[str]] = []

    async def get_embedding(self, text: str) -> list[float]:
        return [1.0]

    async def get_embeddings(self, text: list[str]) -> list[list[float]]:
        self.batches.append(text)
        return [[1.0] for _ in text]

    def get_dim(self) -> int:
        return 1


@pytest.mark.asyncio
async def test_get_embeddings_batch_uses_configured_limit() -> None:
    provider = FakeEmbeddingProvider({"max_batch_size": 10})

    embeddings = await provider.get_embeddings_batch(
        [str(index) for index in range(25)],
        batch_size=32,
    )

    assert len(embeddings) == 25
    assert sorted(len(batch) for batch in provider.batches) == [5, 10, 10]


@pytest.mark.asyncio
async def test_get_embeddings_batch_defaults_to_100() -> None:
    provider = FakeEmbeddingProvider()

    embeddings = await provider.get_embeddings_batch(
        [str(index) for index in range(205)],
        batch_size=256,
    )

    assert len(embeddings) == 205
    assert sorted(len(batch) for batch in provider.batches) == [5, 100, 100]


@pytest.mark.parametrize("max_batch_size", [0, -1])
@pytest.mark.asyncio
async def test_get_embeddings_batch_rejects_invalid_provider_limit(
    max_batch_size: int,
) -> None:
    provider = FakeEmbeddingProvider({"max_batch_size": max_batch_size})

    with pytest.raises(
        ValueError,
        match="max_batch_size must be greater than or equal to 1",
    ):
        await provider.get_embeddings_batch(["text"], batch_size=32)
