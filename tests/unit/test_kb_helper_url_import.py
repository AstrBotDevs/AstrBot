import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core.knowledge_base._kb_helper_url_import import (
    build_url_document_name,
)


@pytest.fixture
def stub_provider_manager_module():
    original_module = sys.modules.get("astrbot.core.provider.manager")
    stub_module = types.ModuleType("astrbot.core.provider.manager")

    class ProviderManager: ...

    setattr(stub_module, "ProviderManager", ProviderManager)
    sys.modules["astrbot.core.provider.manager"] = stub_module

    try:
        yield
    finally:
        if original_module is not None:
            sys.modules["astrbot.core.provider.manager"] = original_module
        else:
            sys.modules.pop("astrbot.core.provider.manager", None)


@pytest.mark.asyncio
async def test_upload_from_url_requires_tavily_key(
    stub_provider_manager_module,
) -> None:
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    helper = KBHelper.__new__(KBHelper)
    helper.prov_mgr = MagicMock()
    helper.prov_mgr.acm = MagicMock()
    helper.prov_mgr.acm.default_conf = {}

    with pytest.raises(ValueError, match="Tavily API key"):
        await helper.upload_from_url("https://example.com/page")


@pytest.mark.asyncio
async def test_upload_from_url_uses_extracted_chunks(
    stub_provider_manager_module,
) -> None:
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    helper = KBHelper.__new__(KBHelper)
    helper.prov_mgr = MagicMock()
    helper.prov_mgr.acm = MagicMock()
    helper.prov_mgr.acm.default_conf = {
        "provider_settings": {"websearch_tavily_key": ["test-key"]}
    }
    helper._clean_and_rechunk_content = AsyncMock(return_value=["chunk-a", "chunk-b"])
    helper.upload_document = AsyncMock(return_value="uploaded")

    with patch(
        "astrbot.core.knowledge_base.kb_helper.extract_url_content",
        new=AsyncMock(return_value="content"),
    ):
        result = await helper.upload_from_url("https://example.com/article")

    assert result == "uploaded"
    helper.upload_document.assert_awaited_once()
    _, kwargs = helper.upload_document.await_args
    assert kwargs["pre_chunked_text"] == ["chunk-a", "chunk-b"]
    assert kwargs["file_name"] == "article.url"


@pytest.mark.asyncio
async def test_upload_from_url_rejects_empty_cleaned_chunks(
    stub_provider_manager_module,
) -> None:
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    helper = KBHelper.__new__(KBHelper)
    helper.prov_mgr = MagicMock()
    helper.prov_mgr.acm = MagicMock()
    helper.prov_mgr.acm.default_conf = {
        "provider_settings": {"websearch_tavily_key": ["test-key"]}
    }
    helper._clean_and_rechunk_content = AsyncMock(return_value=[])
    helper.upload_document = AsyncMock()

    with patch(
        "astrbot.core.knowledge_base.kb_helper.extract_url_content",
        new=AsyncMock(return_value="content"),
    ):
        with pytest.raises(ValueError, match="内容清洗后未提取到有效文本"):
            await helper.upload_from_url(
                "https://example.com/article",
                enable_cleaning=True,
                cleaning_provider_id="provider-1",
            )

    helper.upload_document.assert_not_called()


def test_build_url_document_name_adds_suffix_when_missing() -> None:
    assert build_url_document_name("https://example.com/article") == "article.url"
    assert build_url_document_name("https://example.com/file.md") == "file.md"
