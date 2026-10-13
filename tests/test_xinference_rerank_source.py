"""Regression tests for the Xinference rerank provider failure contract (#10000).

The provider used to swallow upstream failures and return an empty list,
which the retrieval manager read as a legitimate empty rerank result and
used to overwrite the fused candidates. Failures now propagate so the
manager can fall back to the unreranked results.
"""

from unittest.mock import AsyncMock, Mock

import pytest

from astrbot.core.provider.sources.xinference_rerank_source import (
    XinferenceRerankProvider,
)


@pytest.fixture
def provider() -> XinferenceRerankProvider:
    instance = XinferenceRerankProvider.__new__(XinferenceRerankProvider)
    instance.model = Mock()
    return instance


@pytest.mark.asyncio
async def test_rerank_failure_propagates_instead_of_empty_list(provider):
    provider.model.rerank = AsyncMock(side_effect=RuntimeError("upstream down"))

    with pytest.raises(RuntimeError, match="upstream down"):
        await provider.rerank(query="q", documents=["a", "b"])


@pytest.mark.asyncio
async def test_uninitialized_model_raises_instead_of_empty_list(provider):
    provider.model = None

    with pytest.raises(RuntimeError, match="not initialized"):
        await provider.rerank(query="q", documents=["a"])
