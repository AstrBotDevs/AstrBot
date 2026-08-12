import abc
import asyncio
import os
from collections.abc import AsyncGenerator
from typing import Any, Literal, TypeAlias, Union

from astrbot.core.agent.message import (
    FROM_REAL_TOOL_CALL_KEY,
    ContentPart,
    Message,
    is_checkpoint_message,
    message_to_dict_with_marker,
)
from astrbot.core.agent.tool import ToolSet
from astrbot.core.provider.entities import (
    LLMResponse,
    ProviderMeta,
    RerankResult,
    ToolCallsResult,
)
from astrbot.core.provider.register import provider_cls_map
from astrbot.core.utils.astrbot_path import get_astrbot_path

Providers: TypeAlias = Union[
    "Provider",
    "STTProvider",
    "TTSProvider",
    "EmbeddingProvider",
    "RerankProvider",
]


class AbstractProvider(abc.ABC):
    """Provider Abstract Class"""

    def __init__(self, provider_config: dict) -> None:
        super().__init__()
        self.model_name = ""
        self.provider_config = provider_config

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
                dicts.append(message_to_dict_with_marker(message))
            else:
                dicts.append(message)

        return dicts

    async def test(self, timeout: float = 45.0) -> None:
        await asyncio.wait_for(
            self.text_chat(prompt="REPLY `PONG` ONLY"),
            timeout=timeout,
        )


def _is_fake_tool_pair(asst_msg: dict[str, Any], tool_msg: dict[str, Any]) -> bool:
    """判断一对 assistant(tool_calls) / tool 是否为需要重排的伪造对。

    先校验结构（角色与 ``tool_call_id`` 匹配，忽略缺失 ID），再排除真实工具执行
    产生的对——真实对带 ``_from_real_tool_call`` 标记（见 ``ToolCallsResult`` 与
    ``Message``），插件注入的伪造对是裸 dict，永远不会有该标记。
    """
    if not isinstance(asst_msg, dict) or not isinstance(tool_msg, dict):
        return False

    if asst_msg.get("role") != "assistant" or tool_msg.get("role") != "tool":
        return False

    tool_calls = asst_msg.get("tool_calls")
    if not tool_calls:
        return False

    # 仅收集非 None 的 tool_call_id，避免缺失 ID 被误判为有效匹配
    tc_ids: set[str] = set()
    for tc in tool_calls:
        if not isinstance(tc, dict):
            continue
        tc_id = tc.get("id")
        if tc_id is not None:
            tc_ids.add(tc_id)

    if tool_msg.get("tool_call_id") not in tc_ids:
        return False

    # 排除真实工具执行产生的对
    if asst_msg.get(FROM_REAL_TOOL_CALL_KEY) or tool_msg.get(FROM_REAL_TOOL_CALL_KEY):
        return False

    return True


def _collect_tailing_fake_pairs(
    messages: list[dict[str, Any]],
) -> tuple[int, list[tuple[dict[str, Any], dict[str, Any]]]]:
    """返回尾部伪造对块的起始索引及按外层到内层顺序排列的对。

    从尾部向前收集连续的伪造对（内层优先），遇非对或真实标记对即停止。
    起始索引是重排前缀（不参与重排部分）的长度；无匹配时返回整个列表长度与空列表。
    """
    if not isinstance(messages, list) or len(messages) < 2:
        # messages 可能为 None 等无长度对象；此时 pairs 必为空，起始索引无意义
        return 0, []

    last = messages[-1]
    if not isinstance(last, dict) or last.get("role") != "user":
        return len(messages), []

    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    i = len(messages) - 2
    while i >= 1 and _is_fake_tool_pair(messages[i - 1], messages[i]):
        pairs.append((messages[i - 1], messages[i]))
        i -= 2

    return i + 1, list(reversed(pairs))


def reorder_tailing_tool_call_user(messages: list[dict[str, Any]]) -> None:
    """重排因伪造工具调用导致尾部 assistant(tc) → tool → user 乱序的消息。

    真实工具执行产生的对带 ``_from_real_tool_call`` 标记，扫描遇到即停止，
    避免误伤紧随其后的真实 user 消息（图片复核、max steps 收尾、跨轮次历史）。
    此为轻量妥协修复。未来若实现专用的上下文操作钩子或伪造工具调用钩子，
    可考虑移除此函数。

    Constraints:
    - ``messages`` 必须为 OpenAI 风格 dict 列表（``role`` / ``content`` /
      ``tool_calls`` / ``tool_call_id`` 字段）；非 dict 条目安全跳过。
    - 就地修改 ``messages``，返回 ``None``。
    - 仅当末尾消息为 ``user`` 时触发，且只收集尾部连续的最内层伪造对块；
      其余情况静默 no-op。
    """
    start_idx, pairs = _collect_tailing_fake_pairs(messages)
    if not pairs:
        return

    last_user = messages[-1]
    fake_block = [m for pair in pairs for m in pair]
    # 重排：prefix → user → assistant_1, tool_1 → ... → assistant_N, tool_N
    messages[:] = messages[:start_idx] + [last_user] + fake_block


def strip_internal_markers(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """返回剥离 ``_from_real_tool_call`` 标记的消息副本，不改动原列表。

    标记只在发送前对副本剥离，payload 中的标记保留供重试时重排继续做误伤防护。
    """
    return [
        {k: v for k, v in msg.items() if k != FROM_REAL_TOOL_CALL_KEY}
        if isinstance(msg, dict)
        else msg
        for msg in messages
    ]


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
            batch_size: 每批处理的文本数量
            tasks_limit: 并发任务数量限制
            max_retries: 失败时的最大重试次数
            progress_callback: 进度回调函数，接收参数 (current, total)

        Returns:
            向量列表

        """
        semaphore = asyncio.Semaphore(tasks_limit)
        batch_results: dict[int, list[list[float]]] = {}
        failed_batches: list[tuple[int, list[str]]] = []
        completed_count = 0
        total_count = len(texts)

        async def process_batch(batch_idx: int, batch_texts: list[str]) -> None:
            nonlocal completed_count
            async with semaphore:
                for attempt in range(max_retries):
                    try:
                        batch_embeddings = await self.get_embeddings(batch_texts)
                        batch_results[batch_idx] = batch_embeddings
                        completed_count += len(batch_texts)
                        if progress_callback:
                            await progress_callback(completed_count, total_count)
                        return
                    except Exception as e:
                        if attempt == max_retries - 1:
                            # 最后一次重试失败，记录失败的批次
                            failed_batches.append((batch_idx, batch_texts))
                            raise Exception(
                                f"批次 {batch_idx} 处理失败，已重试 {max_retries} 次: {e!s}",
                            )
                        # 等待一段时间后重试，使用指数退避
                        await asyncio.sleep(2**attempt)

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
