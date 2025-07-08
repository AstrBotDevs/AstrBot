import abc
from typing import List
from typing import TypedDict, AsyncGenerator
from astrbot.core.provider.func_tool_manager import FuncCall
from astrbot.core.provider.entities import LLMResponse, ToolCallsResult, ProviderType
from dataclasses import dataclass


class Personality(TypedDict):
    prompt: str = ""
    name: str = ""
    begin_dialogs: List[str] = []
    mood_imitation_dialogs: List[str] = []

    # cache
    _begin_dialogs_processed: List[dict] = []
    _mood_imitation_dialogs_processed: str = ""


@dataclass
class ProviderMeta:
    id: str
    model: str
    type: str
    provider_type: ProviderType


class AbstractProvider(abc.ABC):
    def __init__(self, provider_config: dict) -> None:
        super().__init__()
        self.model_name = ""
        self.provider_config = provider_config

    def set_model(self, model_name: str):
        """设置当前使用的模型名称"""
        self.model_name = model_name

    def get_model(self) -> str:
        """获得当前使用的模型名称"""
        return self.model_name

    def meta(self) -> ProviderMeta:
        """获取 Provider 的元数据"""
        from astrbot.core.provider.register import provider_cls_map

        provider_type_name = self.provider_config["type"]
        meta_data = provider_cls_map.get(provider_type_name)
        provider_type = meta_data.provider_type if meta_data else None
        return ProviderMeta(
            id=self.provider_config["id"],
            model=self.get_model(),
            type=provider_type_name,
            provider_type=provider_type,
        )


class Provider(AbstractProvider):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
        default_persona: Personality | None = None,
    ) -> None:
        super().__init__(provider_config)

        self.provider_settings = provider_settings

        self.curr_personality = default_persona
        """维护了当前的使用的 persona，即人格。可能为 None"""

    @abc.abstractmethod
    def get_current_key(self) -> str:
        raise NotImplementedError()

    def get_keys(self) -> List[str]:
        """获得提供商 Key"""
        return self.provider_config.get("key", [])

    @abc.abstractmethod
    def set_key(self, key: str):
        raise NotImplementedError()

    @abc.abstractmethod
    def get_models(self) -> List[str]:
        """获得支持的模型列表"""
        raise NotImplementedError()

    @abc.abstractmethod
    async def text_chat(
        self,
        prompt: str,
        session_id: str = None,
        image_urls: list[str] = None,
        func_tool: FuncCall = None,
        contexts: list = None,
        system_prompt: str = None,
        tool_calls_result: ToolCallsResult | list[ToolCallsResult] = None,
        model: str | None = None,
        **kwargs,
    ) -> LLMResponse:
        """获得 LLM 的文本对话结果。会使用当前的模型进行对话。

        Args:
            prompt: 提示词
            session_id: 会话 ID(此属性已经被废弃)
            image_urls: 图片 URL 列表
            tools: Function-calling 工具
            contexts: 上下文
            tool_calls_result: 回传给 LLM 的工具调用结果。参考: https://platform.openai.com/docs/guides/function-calling
            kwargs: 其他参数

        Notes:
            - 如果传入了 image_urls，将会在对话时附上图片。如果模型不支持图片输入，将会抛出错误。
            - 如果传入了 tools，将会使用 tools 进行 Function-calling。如果模型不支持 Function-calling，将会抛出错误。
        """
        ...

    async def text_chat_stream(
        self,
        prompt: str,
        session_id: str = None,
        image_urls: list[str] = None,
        func_tool: FuncCall = None,
        contexts: list = None,
        system_prompt: str = None,
        tool_calls_result: ToolCallsResult | list[ToolCallsResult] = None,
        model: str | None = None,
        **kwargs,
    ) -> AsyncGenerator[LLMResponse, None]:
        """获得 LLM 的流式文本对话结果。会使用当前的模型进行对话。在生成的最后会返回一次完整的结果。

        Args:
            prompt: 提示词
            session_id: 会话 ID(此属性已经被废弃)
            image_urls: 图片 URL 列表
            tools: Function-calling 工具
            contexts: 上下文
            tool_calls_result: 回传给 LLM 的工具调用结果。参考: https://platform.openai.com/docs/guides/function-calling
            kwargs: 其他参数

        Notes:
            - 如果传入了 image_urls，将会在对话时附上图片。如果模型不支持图片输入，将会抛出错误。
            - 如果传入了 tools，将会使用 tools 进行 Function-calling。如果模型不支持 Function-calling，将会抛出错误。
        """
        ...

    async def pop_record(self, context: List):
        """
        弹出 context 第一条非系统提示词对话记录
        """
        poped = 0
        indexs_to_pop = []
        for idx, record in enumerate(context):
            if record["role"] == "system":
                continue
            else:
                indexs_to_pop.append(idx)
                poped += 1
                if poped == 2:
                    break

        for idx in reversed(indexs_to_pop):
            context.pop(idx)


class STTProvider(AbstractProvider):
    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config)
        self.provider_config = provider_config
        self.provider_settings = provider_settings

    @abc.abstractmethod
    async def get_text(self, audio_url: str) -> str:
        """获取音频的文本"""
        raise NotImplementedError()


class TTSProvider(AbstractProvider):
    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config)
        self.provider_config = provider_config
        self.provider_settings = provider_settings

    @abc.abstractmethod
    async def get_audio(self, text: str) -> str:
        """获取文本的音频，返回音频文件路径"""
        raise NotImplementedError()


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
