import abc
import asyncio
import os
import re
from collections.abc import AsyncGenerator
from typing import Literal, TypeAlias, Union

from astrbot import logger
from astrbot.core.agent.message import ContentPart, Message, is_checkpoint_message
from astrbot.core.agent.tool import ToolSet
from astrbot.core.provider.entities import (
    LLMResponse,
    ProviderMeta,
    RerankResult,
    ToolCallsResult,
)
from astrbot.core.provider.headers import build_provider_headers
from astrbot.core.provider.register import provider_cls_map
from astrbot.core.utils.astrbot_path import get_astrbot_path

Providers: TypeAlias = Union[
    "Provider",
    "STTProvider",
    "TTSProvider",
    "EmbeddingProvider",
    "RerankProvider",
]


# ---------------------------------------------------------------------------
# Embedding batch-size rejections
#
# A request refused because it carried too many inputs fails deterministically:
# the same request will be refused again however often it is retried. Such a
# failure has to be recognised so the caller shrinks the request (which is what
# adaptive splitting does) instead of spending the retry budget on it. All of
# the matching below is deliberately narrow -- a misread makes AstrBot split a
# batch that was never too large, so unrelated failures (token limits, rate
# limits, bad credentials) must never qualify.
# ---------------------------------------------------------------------------

# Client error codes a provider may use to report "too many inputs in one request".
_BATCH_SIZE_STATUS_CODES = frozenset({400, 413, 414, 422})

# 4xx codes that are still worth retrying (timeouts / conflicts / throttling).
_RETRYABLE_CLIENT_STATUS_CODES = frozenset({408, 409, 425, 429})

_BATCH_SIZE_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"batch[\s_-]*(?:size|length|count|limit)",
        r"too many (?:inputs?|texts?|items?|sentences?|contents?|documents?|chunks?|rows?)",
        r"input (?:array|list|batch)[^.]{0,32}too (?:long|large|many)",
        r"(?:maximum|max)\s+(?:number of\s+)?(?:inputs?|texts?|items?|rows?)",
        r"range of inputs?(?: length)?[^.]{0,24}\[\s*\d+\s*,\s*\d+\s*\]",
        # zh
        r"批量[\s\S]{0,8}(?:超|不能|不得|最多|限制|过大)",
        r"(?:单次|每次|一次)[\s\S]{0,8}(?:最多|不超过|不能超过|不得超过)\s*\d+",
    )
)

# Per-item content limits: splitting the request would not help and would mask
# the real cause, so these disqualify a message even if it also mentions a size.
_BATCH_SIZE_EXCLUSIONS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"context[\s_-]*(?:length|window)",
        r"max_tokens|maximum (?:output )?tokens|token limit|too many tokens",
        r"rate limit|too many requests",
        r"文本(?:过长|长度)|输入(?:过长|长度超)|内容(?:过长)",
    )
)

_STATUS_PATTERN = re.compile(
    r"(?:http|status(?:\s*code)?)\s*[:=]?\s*(\d{3})\b",
    re.IGNORECASE,
)

# "should not be larger than 10", "maximum of 10", "[1, 10]", "最多 10 条"
_LIMIT_HINT_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"(?:larger|greater|more|bigger)\s+than\s*[:：]?\s*(\d+)",
        r"(?:at most|no more than|maximum of|max)\s*[:：]?\s*(\d+)",
        r"\[\s*\d+\s*,\s*(\d+)\s*\]",
        r"(?:不超过|最多|不能超过|不得超过)\s*(\d+)",
    )
)


def _exception_status_code(exc: BaseException) -> int | None:
    """Best-effort HTTP status code for a provider failure.

    Covers both shapes used in this repo: SDK errors carrying ``status_code``
    (``openai.BadRequestError``) and plain ``Exception``s whose text embeds
    ``(HTTP 400)`` (the DashScope adapter).
    """
    for attr in ("status_code", "http_status", "status"):
        value = getattr(exc, attr, None)
        if isinstance(value, int) and 100 <= value < 600:
            return value
    response = getattr(exc, "response", None)
    value = getattr(response, "status_code", None)
    if isinstance(value, int) and 100 <= value < 600:
        return value
    match = _STATUS_PATTERN.search(str(exc))
    if match:
        code = int(match.group(1))
        if 100 <= code < 600:
            return code
    return None


def _looks_like_batch_size_error(exc: BaseException) -> bool:
    """Whether ``exc`` says the request carried too many inputs."""
    message = str(exc)
    if not message:
        return False
    if any(pattern.search(message) for pattern in _BATCH_SIZE_EXCLUSIONS):
        return False
    status = _exception_status_code(exc)
    if status is not None and status not in _BATCH_SIZE_STATUS_CODES:
        return False
    return any(pattern.search(message) for pattern in _BATCH_SIZE_PATTERNS)


def _extract_batch_limit(exc: BaseException, attempted: int) -> int | None:
    """Read the provider's stated input limit out of a rejection message.

    Only a value that is a plausible limit for the request just refused
    (``1 <= limit < attempted``) is returned, so a number quoted for any other
    reason can never become the new batch size.
    """
    message = str(exc)
    for pattern in _LIMIT_HINT_PATTERNS:
        for match in pattern.finditer(message):
            limit = int(match.group(1))
            if 1 <= limit < attempted:
                return limit
    return None


def _is_retryable_error(exc: BaseException) -> bool:
    """Whether re-issuing the identical request could plausibly succeed."""
    status = _exception_status_code(exc)
    if status is None:
        return True
    if status >= 500 or status in _RETRYABLE_CLIENT_STATUS_CODES:
        return True
    return not 400 <= status < 500


class AbstractProvider(abc.ABC):
    """Provider Abstract Class"""

    def __init__(self, provider_config: dict) -> None:
        super().__init__()
        self.model_name = ""
        self.provider_config = provider_config
        self.request_headers = build_provider_headers(
            provider_config.get("custom_headers")
        )

    def set_model(self, model_name: str) -> None:
        """Set the current model name"""
        self.model_name = model_name

    def get_model(self) -> str:
        """Get the current model name"""
        return self.model_name

    def meta(self) -> ProviderMeta:
        """Get the provider metadata"""
        provider_type_name = self.provider_config["type"]
        meta_data = provider_cls_map.get(provider_type_name)
        if not meta_data:
            raise ValueError(f"Provider type {provider_type_name} not registered")
        meta = ProviderMeta(
            id=self.provider_config.get("id", "default"),
            model=self.get_model(),
            type=provider_type_name,
            provider_type=meta_data.provider_type,
        )
        return meta

    async def test(self) -> None:
        """test the provider is a

        raises:
            Exception: if the provider is not available
        """
        ...


class Provider(AbstractProvider):
    """Chat Provider"""

    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        super().__init__(provider_config)
        self.provider_settings = provider_settings

    @abc.abstractmethod
    def get_current_key(self) -> str:
        raise NotImplementedError

    def get_keys(self) -> list[str]:
        """获得提供商 Key"""
        keys = self.provider_config.get("key", [""])
        return keys or [""]

    @abc.abstractmethod
    def set_key(self, key: str) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    async def get_models(self) -> list[str]:
        """获得支持的模型列表"""
        raise NotImplementedError

    @abc.abstractmethod
    async def text_chat(
        self,
        prompt: str | None = None,
        session_id: str | None = None,
        image_urls: list[str] | None = None,
        audio_urls: list[str] | None = None,
        func_tool: ToolSet | None = None,
        contexts: list[Message] | list[dict] | None = None,
        system_prompt: str | None = None,
        tool_calls_result: ToolCallsResult | list[ToolCallsResult] | None = None,
        model: str | None = None,
        extra_user_content_parts: list[ContentPart] | None = None,
        tool_choice: Literal["auto", "required"] = "auto",
        request_max_retries: int | None = None,
        **kwargs,
    ) -> LLMResponse:
        """获得 LLM 的文本对话结果。会使用当前的模型进行对话。

        Args:
            prompt: 提示词，和 contexts 二选一使用，如果都指定，则会将 prompt（以及可能的 image_urls） 作为最新的一条记录添加到 contexts 中
            session_id: 会话 ID(此属性已经被废弃)
            image_urls: 图片 URL 列表
            audio_urls: 音频 URL 列表，也支持本地路径
            tools: tool set
            tool_choice: 工具调用策略，`auto` 表示由模型自行决定，`required` 表示要求模型必须调用工具
            contexts: 上下文，和 prompt 二选一使用
            tool_calls_result: 回传给 LLM 的工具调用结果。参考: https://platform.openai.com/docs/guides/function-calling
            extra_user_content_parts: 额外的内容块列表，用于在用户消息后添加额外的文本块（如系统提醒、指令等）
            request_max_retries: 可重试请求错误的最大尝试次数，包含首次请求。
            kwargs: 其他参数

        Notes:
            - 如果传入了 image_urls，将会在对话时附上图片。如果模型不支持图片输入，将会抛出错误。
            - 如果传入了 audio_urls，将会在对话时附上音频。如果模型不支持音频输入，将会抛出错误或降级处理。
            - 如果传入了 tools，将会使用 tools 进行 Function-calling。如果模型不支持 Function-calling，将会抛出错误。

        """
        ...

    async def text_chat_stream(
        self,
        prompt: str | None = None,
        session_id: str | None = None,
        image_urls: list[str] | None = None,
        audio_urls: list[str] | None = None,
        func_tool: ToolSet | None = None,
        contexts: list[Message] | list[dict] | None = None,
        system_prompt: str | None = None,
        tool_calls_result: ToolCallsResult | list[ToolCallsResult] | None = None,
        model: str | None = None,
        tool_choice: Literal["auto", "required"] = "auto",
        request_max_retries: int | None = None,
        **kwargs,
    ) -> AsyncGenerator[LLMResponse, None]:
        """获得 LLM 的流式文本对话结果。会使用当前的模型进行对话。在生成的最后会返回一次完整的结果。

        Args:
            prompt: 提示词，和 contexts 二选一使用，如果都指定，则会将 prompt（以及可能的 image_urls） 作为最新的一条记录添加到 contexts 中
            session_id: 会话 ID(此属性已经被废弃)
            image_urls: 图片 URL 列表
            audio_urls: 音频 URL 列表，也支持本地路径
            tools: tool set
            tool_choice: 工具调用策略，`auto` 表示由模型自行决定，`required` 表示要求模型必须调用工具
            contexts: 上下文，和 prompt 二选一使用
            tool_calls_result: 回传给 LLM 的工具调用结果。参考: https://platform.openai.com/docs/guides/function-calling
            request_max_retries: 可重试请求错误的最大尝试次数，包含首次请求。
            kwargs: 其他参数

        Notes:
            - 如果传入了 image_urls，将会在对话时附上图片。如果模型不支持图片输入，将会抛出错误。
            - 如果传入了 audio_urls，将会在对话时附上音频。如果模型不支持音频输入，将会抛出错误或降级处理。
            - 如果传入了 tools，将会使用 tools 进行 Function-calling。如果模型不支持 Function-calling，将会抛出错误。

        """
        if False:  # pragma: no cover - make this an async generator for typing
            yield None  # type: ignore
        raise NotImplementedError()

    async def pop_record(self, context: list) -> None:
        """弹出 context 第一条非系统提示词对话记录"""
        poped = 0
        indexs_to_pop = []
        for idx, record in enumerate(context):
            if record["role"] == "system":
                continue
            indexs_to_pop.append(idx)
            poped += 1
            if poped == 2:
                break

        for idx in reversed(indexs_to_pop):
            context.pop(idx)

    def _ensure_message_to_dicts(
        self,
        messages: list[dict] | list[Message] | None,
    ) -> list[dict]:
        """Convert a list of Message objects to a list of dictionaries."""
        if not messages:
            return []
        dicts: list[dict] = []
        for message in messages:
            if is_checkpoint_message(message):
                continue
            if isinstance(message, Message):
                dicts.append(message.model_dump())
            else:
                dicts.append(message)

        return dicts

    async def test(self, timeout: float = 45.0) -> None:
        await asyncio.wait_for(
            self.text_chat(prompt="REPLY `PONG` ONLY"),
            timeout=timeout,
        )


class STTProvider(AbstractProvider):
    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config)
        self.provider_config = provider_config
        self.provider_settings = provider_settings

    @abc.abstractmethod
    async def get_text(self, audio_url: str) -> str:
        """获取音频的文本"""
        raise NotImplementedError

    async def test(self) -> None:
        sample_audio_path = os.path.join(
            get_astrbot_path(),
            "samples",
            "stt_health_check.wav",
        )
        await self.get_text(sample_audio_path)


class TTSProvider(AbstractProvider):
    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config)
        self.provider_config = provider_config
        self.provider_settings = provider_settings

    def support_stream(self) -> bool:
        """是否支持流式 TTS

        Returns:
            bool: True 表示支持流式处理，False 表示不支持（默认）

        Notes:
            子类可以重写此方法返回 True 来启用流式 TTS 支持
        """
        return False

    @abc.abstractmethod
    async def get_audio(self, text: str) -> str:
        """获取文本的音频，返回音频文件路径"""
        raise NotImplementedError

    async def get_audio_stream(
        self,
        text_queue: asyncio.Queue[str | None],
        audio_queue: "asyncio.Queue[bytes | tuple[str, bytes] | None]",
    ) -> None:
        """流式 TTS 处理方法。

        从 text_queue 中读取文本片段，将生成的音频数据（WAV 格式的 in-memory bytes）放入 audio_queue。
        当 text_queue 收到 None 时，表示文本输入结束，此时应该处理完所有剩余文本并向 audio_queue 发送 None 表示结束。

        Args:
            text_queue: 输入文本队列，None 表示输入结束
            audio_queue: 输出音频队列（bytes 或 (text, bytes)），None 表示输出结束

        Notes:
            - 默认实现会将文本累积后一次性调用 get_audio 生成完整音频
            - 子类可以重写此方法实现真正的流式 TTS
            - 音频数据应该是 WAV 格式的 bytes
        """
        accumulated_text = ""

        while True:
            text_part = await text_queue.get()

            if text_part is None:
                # 输入结束，处理累积的文本
                if accumulated_text:
                    try:
                        # 调用原有的 get_audio 方法获取音频文件路径
                        audio_path = await self.get_audio(accumulated_text)
                        # 读取音频文件内容
                        with open(audio_path, "rb") as f:
                            audio_data = f.read()
                        await audio_queue.put((accumulated_text, audio_data))
                    except Exception:
                        # 出错时也要发送 None 结束标记
                        pass
                # 发送结束标记
                await audio_queue.put(None)
                break

            accumulated_text += text_part

    async def test(self) -> None:
        audio_path = await self.get_audio("hi")

        # 检查生成的音频文件是否有效
        if not os.path.exists(audio_path):
            raise Exception("TTS test failed: audio file was not created")

        file_size = os.path.getsize(audio_path)
        if file_size == 0:
            raise Exception(
                "TTS test failed: generated audio file is empty (0 bytes). "
                "Please check your TTS provider configuration, especially required parameters like group_id for MiniMax."
            )

        # 清理测试文件
        try:
            os.remove(audio_path)
        except Exception:
            pass


class EmbeddingProvider(AbstractProvider):
    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config)
        self.provider_config = provider_config
        self.provider_settings = provider_settings
        # Upper bound on the inputs per request, once a provider has rejected a
        # batch and stated it. None until then (see get_embeddings_batch).
        self._learned_batch_size: int | None = None

    @abc.abstractmethod
    async def get_embedding(self, text: str) -> list[float]:
        """获取文本的向量"""
        ...

    @abc.abstractmethod
    async def get_embeddings(self, text: list[str]) -> list[list[float]]:
        """批量获取文本的向量"""
        ...

    @abc.abstractmethod
    def get_dim(self) -> int:
        """获取向量的维度"""
        ...

    async def test(self) -> None:
        await self.get_embedding("astrbot")

    def get_max_batch_size(self) -> int | None:
        """单次嵌入请求允许携带的最大文本数量。

        Returning ``None`` (the default) means the limit is unknown, which keeps
        the caller-supplied ``batch_size`` untouched. Adapters whose service
        documents a fixed limit should override this; a generic OpenAI-compatible
        endpoint whose limit cannot be inferred can declare it through the
        ``embedding_max_batch_items`` provider config key instead.

        This is only a *hint* used to avoid a doomed request up front --
        ``get_embeddings_batch`` additionally recovers from a rejection at
        runtime, so a wrong or missing value cannot break batching.
        """
        raw = (getattr(self, "provider_config", None) or {}).get(
            "embedding_max_batch_items"
        )
        if raw is None or raw == "":
            return None
        try:
            value = int(raw)
        except (TypeError, ValueError):
            logger.warning(
                f"embedding_max_batch_items is not a valid integer: '{raw}', ignored."
            )
            return None
        if value <= 0:
            logger.warning(
                f"embedding_max_batch_items must be positive, got {value}, ignored."
            )
            return None
        return value

    async def get_embeddings_batch(
        self,
        texts: list[str],
        batch_size: int = 16,
        tasks_limit: int = 3,
        max_retries: int = 3,
        progress_callback=None,
    ) -> list[list[float]]:
        """批量获取文本的向量，分批处理以节省内存

        Args:
            texts: 文本列表
            batch_size: 每批处理的文本数量；超过提供商单次请求上限时会被自动压低
            tasks_limit: 并发任务数量限制
            max_retries: 失败时的最大重试次数
            progress_callback: 进度回调函数，接收参数 (current, total)

        Returns:
            向量列表

        """
        if not texts:
            return []

        batch_size = max(1, int(batch_size))
        # A request that carries too many inputs is refused deterministically, so
        # clamp to whatever limit the provider declares before building any work.
        declared_cap = self.get_max_batch_size()
        if declared_cap is not None and batch_size > declared_cap:
            logger.debug(
                f"[{type(self).__name__}] batch_size {batch_size} exceeds the "
                f"provider limit {declared_cap}, using {declared_cap}."
            )
            batch_size = declared_cap

        # A single rejection reveals the real limit, so record it and reuse it
        # for the remaining batches of this call (and later calls on this
        # instance). Learned values always come from a message that *stated* a
        # limit; a bare rejection only tightens the size for the current call,
        # so an unrelated error misread as a size rejection cannot permanently
        # shrink this provider's batches.
        learned_cap = getattr(self, "_learned_batch_size", None)
        cap_state = {"size": batch_size}
        if isinstance(learned_cap, int) and 0 < learned_cap < cap_state["size"]:
            cap_state["size"] = learned_cap

        semaphore = asyncio.Semaphore(tasks_limit)
        batch_results: dict[int, list[list[float]]] = {}
        failed_batches: list[tuple[int, list[str]]] = []
        completed_count = 0
        total_count = len(texts)

        def note_limit(size: int) -> None:
            if size < cap_state["size"]:
                cap_state["size"] = size

        async def embed_slice(slice_texts: list[str]) -> list[list[float]]:
            """Embed one slice, splitting it when the provider refuses its size."""
            if len(slice_texts) > cap_state["size"]:
                # A limit learned earlier in this call already rules this out.
                return await split_and_embed(slice_texts)
            for attempt in range(max_retries):
                try:
                    return await self.get_embeddings(slice_texts)
                except Exception as e:
                    if _looks_like_batch_size_error(e) and len(slice_texts) > 1:
                        limit = _extract_batch_limit(e, len(slice_texts))
                        if limit is not None:
                            self._learned_batch_size = limit
                            note_limit(limit)
                        else:
                            note_limit(len(slice_texts) // 2)
                        logger.debug(
                            f"[{type(self).__name__}] provider rejected {len(slice_texts)} "
                            f"inputs, retrying in smaller batches: {e!s}"
                        )
                        return await split_and_embed(slice_texts)
                    if attempt == max_retries - 1 or not _is_retryable_error(e):
                        raise
                    # 等待一段时间后重试，使用指数退避
                    await asyncio.sleep(2**attempt)

        async def split_and_embed(slice_texts: list[str]) -> list[list[float]]:
            # Only ever called with len(slice_texts) > cap_state["size"], so a
            # known limit is honoured exactly (32 inputs against a limit of 10
            # become 10/10/10/2, not four rounds of halving) and an unknown one
            # halves. Every piece is strictly smaller than the slice, so the
            # recursion terminates, and a single rejected text re-raises the
            # provider's own error instead of splitting forever.
            step = max(1, min(cap_state["size"], len(slice_texts) - 1))
            embeddings: list[list[float]] = []
            for start in range(0, len(slice_texts), step):
                embeddings.extend(await embed_slice(slice_texts[start : start + step]))
            return embeddings

        async def process_batch(batch_idx: int, batch_texts: list[str]) -> None:
            nonlocal completed_count
            async with semaphore:
                try:
                    batch_embeddings = await embed_slice(batch_texts)
                except Exception as e:
                    failed_batches.append((batch_idx, batch_texts))
                    raise Exception(f"批次 {batch_idx} 处理失败: {e!s}") from e
                batch_results[batch_idx] = batch_embeddings
                completed_count += len(batch_texts)
                if progress_callback:
                    await progress_callback(completed_count, total_count)

        tasks = []
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i : i + batch_size]
            batch_idx = i // batch_size
            tasks.append(process_batch(batch_idx, batch_texts))

        # 收集所有任务的结果，包括失败的任务
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 检查是否有失败的任务
        errors = [r for r in results if isinstance(r, Exception)]
        if errors:
            error_msg = (
                f"有 {len(errors)} 个批次处理失败: {'; '.join(str(e) for e in errors)}"
            )
            raise Exception(error_msg)

        all_embeddings: list[list[float]] = []
        for batch_idx in range(len(tasks)):
            all_embeddings.extend(batch_results[batch_idx])
        return all_embeddings


class RerankProvider(AbstractProvider):
    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config)
        self.provider_config = provider_config
        self.provider_settings = provider_settings

    @abc.abstractmethod
    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int | None = None,
    ) -> list[RerankResult]:
        """获取查询和文档的重排序分数"""
        ...

    async def test(self) -> None:
        result = await self.rerank("Apple", documents=["apple", "banana"])
        if not result:
            raise Exception("Rerank provider test failed, no results returned")
