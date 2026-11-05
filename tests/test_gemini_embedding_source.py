"""Gemini Embedding 适配器的任务条件化测试。

覆盖 issue #11006：gemini-embedding-001 需要 ``task_type``，
gemini-embedding-2 需要把任务指令写进文本前缀。
"""

import pytest

from astrbot.core.provider.sources.gemini_embedding_source import (
    GeminiEmbeddingProvider,
    build_document_prefix,
    build_query_prefix,
    resolve_query_task,
    uses_task_prefix,
)


class _RecordingClient:
    """记录 embed_content 调用参数的假客户端。"""

    def __init__(self, dim: int = 8) -> None:
        self.calls: list[dict] = []
        self.dim = dim
        self.models = self

    async def embed_content(self, **kwargs):
        self.calls.append(kwargs)

        class _Emb:
            values = [0.1] * 8

        class _Result:
            pass

        result = _Result()
        contents = kwargs["contents"]
        if isinstance(contents, str):
            result.embeddings = [_Emb()]
        else:
            result.embeddings = [_Emb() for _ in contents]
        return result


def _make_provider(model: str, **overrides) -> GeminiEmbeddingProvider:
    """绕开 __init__ 的 SDK 依赖，构造可测的实例。"""
    provider = GeminiEmbeddingProvider.__new__(GeminiEmbeddingProvider)
    provider.provider_config = {
        "embedding_dimensions": 768,
        "embedding_model": model,
        **overrides,
    }
    provider.provider_settings = {}
    provider.model = model
    provider.task_config_mode = overrides.get("embedding_task_type_mode", "auto")
    provider.query_task = overrides.get("embedding_query_task_type", "RETRIEVAL_QUERY")
    provider.document_task = overrides.get(
        "embedding_document_task_type", "RETRIEVAL_DOCUMENT"
    )
    provider.query_prefix_task = resolve_query_task(
        overrides.get("embedding_query_task_name")
    )
    provider.document_title = overrides.get("embedding_document_title", "")
    provider.client = _RecordingClient()
    return provider


# ── 前缀构造 ────────────────────────────────────────────────


def test_query_prefix_matches_google_format():
    assert build_query_prefix("search result") == "task: search result | query: "


def test_query_prefix_normalizes_underscore_task_name():
    assert build_query_prefix("QUESTION_ANSWERING") == (
        "task: question answering | query: "
    )


def test_query_prefix_falls_back_for_unsupported_task():
    """配置笔误不能打断检索链路，回退到默认任务名。"""
    assert build_query_prefix("classification") == "task: search result | query: "
    assert build_query_prefix("") == "task: search result | query: "


def test_document_prefix_uses_none_when_title_missing():
    assert build_document_prefix(None) == "title: none | text: "
    assert build_document_prefix("") == "title: none | text: "


def test_document_prefix_includes_title():
    assert build_document_prefix("我的文档") == "title: 我的文档 | text: "


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ("gemini-embedding-2", True),
        ("gemini-embedding-2-preview", True),
        ("models/gemini-embedding-2", True),
        ("gemini-embedding-001", False),
        ("text-embedding-004", False),
    ],
)
def test_uses_task_prefix_by_generation(model, expected):
    assert uses_task_prefix(model) is expected


# ── 请求参数：001 走 task_type ──────────────────────────────


@pytest.mark.asyncio
async def test_gemini_embedding_001_sends_task_type_not_prefix():
    provider = _make_provider("gemini-embedding-001")

    await provider.get_embedding("文档正文")
    await provider.get_query_embedding("查询词")

    doc_call, query_call = provider.client.calls
    assert doc_call["config"].task_type == "RETRIEVAL_DOCUMENT"
    assert query_call["config"].task_type == "RETRIEVAL_QUERY"
    # 001 不应改写文本内容
    assert doc_call["contents"] == "文档正文"
    assert query_call["contents"] == "查询词"


@pytest.mark.asyncio
async def test_gemini_embedding_001_batch_sends_document_task_type():
    provider = _make_provider("gemini-embedding-001")

    await provider.get_embeddings(["甲", "乙"])

    call = provider.client.calls[0]
    assert call["config"].task_type == "RETRIEVAL_DOCUMENT"
    texts = [c.parts[0].text for c in call["contents"]]
    assert texts == ["甲", "乙"]


# ── 请求参数：embedding-2 走文本前缀 ────────────────────────


@pytest.mark.asyncio
async def test_gemini_embedding_2_uses_text_prefix_and_no_task_type():
    provider = _make_provider("gemini-embedding-2")

    await provider.get_embedding("文档正文")
    await provider.get_query_embedding("查询词")

    doc_call, query_call = provider.client.calls
    assert doc_call["config"].task_type is None
    assert query_call["config"].task_type is None
    assert doc_call["contents"] == "title: none | text: 文档正文"
    assert query_call["contents"] == "task: search result | query: 查询词"


@pytest.mark.asyncio
async def test_gemini_embedding_2_applies_document_title():
    provider = _make_provider("gemini-embedding-2", embedding_document_title="群聊记忆")

    await provider.get_embedding("正文")

    assert provider.client.calls[0]["contents"] == "title: 群聊记忆 | text: 正文"


@pytest.mark.asyncio
async def test_gemini_embedding_2_batch_applies_document_prefix():
    provider = _make_provider("gemini-embedding-2")

    await provider.get_embeddings(["甲", "乙"])

    texts = [c.parts[0].text for c in provider.client.calls[0]["contents"]]
    assert texts == ["title: none | text: 甲", "title: none | text: 乙"]


# ── 开关与回退 ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_task_prefix_mode_never_disables_prefix_for_embedding_2():
    provider = _make_provider("gemini-embedding-2", embedding_task_type_mode="never")

    await provider.get_query_embedding("查询词")

    call = provider.client.calls[0]
    assert call["contents"] == "查询词"

    # never = 不启用任务条件化；且 embedding-2 不支持 task_type，两者都不能发
    assert call["config"].task_type is None


@pytest.mark.asyncio
async def test_task_prefix_mode_always_forces_prefix_on_older_model():
    provider = _make_provider("gemini-embedding-001", embedding_task_type_mode="always")

    await provider.get_query_embedding("查询词")

    call = provider.client.calls[0]
    assert call["contents"] == "task: search result | query: 查询词"
    assert call["config"].task_type is None


@pytest.mark.asyncio
async def test_query_embedding_falls_back_without_override():
    """未覆盖 get_query_embedding 的提供商标，基类回退到 get_embedding。"""

    class _Plain:
        def __init__(self) -> None:
            self.seen: list[str] = []

        async def get_embedding(self, text: str) -> list[float]:
            self.seen.append(text)
            return [1.0]

    from astrbot.core.provider.provider import EmbeddingProvider

    plain = _Plain()
    result = await EmbeddingProvider.get_query_embedding(plain, "查询词")

    assert plain.seen == ["查询词"]
    assert result == [1.0]


@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        ("search result", "search result"),
        ("QUESTION_ANSWERING", "question answering"),
        ("  Code_Retrieval  ", "code retrieval"),
        # 笔误一律回退，不要让检索链路在调用时崩掉
        ("Search-Result", "search result"),
        ("nonsense-task", "search result"),
        ("", "search result"),
        (None, "search result"),
    ],
)
def test_resolve_query_task(configured, expected):
    assert resolve_query_task(configured) == expected


@pytest.mark.asyncio
async def test_misspelled_task_name_produces_valid_prefix_end_to_end():
    provider = _make_provider(
        "gemini-embedding-2", embedding_query_task_name="Search-Result"
    )

    await provider.get_query_embedding("查询词")

    assert provider.client.calls[0]["contents"] == "task: search result | query: 查询词"


@pytest.mark.parametrize(
    ("model", "mode", "expect_prefix", "expect_task_type"),
    [
        # 001 走 task_type
        ("gemini-embedding-001", "auto", False, "RETRIEVAL_DOCUMENT"),
        # never = 完全不启用任务条件化，既不写前缀也不发 task_type
        ("gemini-embedding-001", "never", False, None),
        # always 强制前缀
        ("gemini-embedding-001", "always", True, None),
        # 2 走文本前缀
        ("gemini-embedding-2", "auto", True, None),
        # 关键：2 不支持 task_type，never 也不能退回它，否则 API 会拒绝
        ("gemini-embedding-2", "never", False, None),
        ("gemini-embedding-2", "always", True, None),
    ],
)
def test_task_conditioning_matrix(model, mode, expect_prefix, expect_task_type):
    """gemini-embedding-2 在任何模式下都不能收到 task_type。"""
    provider = _make_provider(model, embedding_task_type_mode=mode)

    assert provider._uses_task_prefix() is expect_prefix

    config = provider._build_config(
        task_type=provider.document_task,
        title="示例标题",
    )
    assert config.task_type == expect_task_type


@pytest.mark.asyncio
async def test_embedding_2_never_mode_omits_task_type_in_request():
    """回归：mode=never + gemini-embedding-2 曾把 task_type 发给不支持的模型。"""
    provider = _make_provider("gemini-embedding-2", embedding_task_type_mode="never")

    await provider.get_query_embedding("查询词")

    call = provider.client.calls[0]
    assert call["config"].task_type is None
    # 也不加前缀
    assert call["contents"] == "查询词"
