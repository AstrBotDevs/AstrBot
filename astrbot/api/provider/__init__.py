"""
astrbot.api.provider
该模块包含了 AstrBot 有关大模型供应商的所有模块
"""

from astrbot.core.provider import (
    Provider,
    STTProvider,
    TTSProvider,
    EmbeddingProvider,
    Personality,
)
from astrbot.core.provider.entities import (
    ProviderRequest,  # 供应商请求
    ProviderType,  # 供应商类型
    ProviderMetaData,  # 供应商元数据
    LLMResponse,  # 大模型响应
    ToolCallsResult,  # 工具调用结果
    AssistantMessageSegment,  # role 为 assistant 的消息片段
    ToolCallMessageSegment,  # role 为 tool_call 的消息片段
)
from astrbot.core.provider.manager import ProviderManager

from astrbot.core.provider.sources.anthropic_source import ProviderAnthropic  # Claude
from astrbot.core.provider.sources.azure_tts_source import (
    OTTSProvider,
    AzureNativeProvider,
    AzureTTSProvider,
)  # Azure TTS (包括微软官方和OTTS)
from astrbot.core.provider.sources.dashscope_source import (
    ProviderDashscope,
)  # Dashscope (包括文本生成和嵌入)
from astrbot.core.provider.sources.dashscope_tts import (
    ProviderDashscopeTTSAPI,
)  # Dashscope TTS
from astrbot.core.provider.sources.dify_source import ProviderDify  # Dify
from astrbot.core.provider.sources.edge_tts_source import ProviderEdgeTTS  # Edge TTS
from astrbot.core.provider.sources.fishaudio_tts_api_source import (
    ProviderFishAudioTTSAPI,
    ServeTTSRequest,
    ServeReferenceAudio,
)  # FishAudio TTS
from astrbot.core.provider.sources.gemini_embedding_source import (
    GeminiEmbeddingProvider,
)  # Gemini 嵌入
from astrbot.core.provider.sources.gemini_source import (
    ProviderGoogleGenAI,
)  # Google Gemini
from astrbot.core.provider.sources.gemini_tts_source import (
    ProviderGeminiTTSAPI,
)  # Gemini TTS
from astrbot.core.provider.sources.gsv_selfhosted_source import (
    ProviderGSVTTS,
)  # GSV 自托管
from astrbot.core.provider.sources.gsvi_tts_source import ProviderGSVITTS  # GSVI TTS
from astrbot.core.provider.sources.minimax_tts_api_source import (
    ProviderMiniMaxTTSAPI,
)  # MiniMax TTS
from astrbot.core.provider.sources.openai_embedding_source import (
    OpenAIEmbeddingProvider,
)  # OpenAI 嵌入
from astrbot.core.provider.sources.openai_source import (
    ProviderOpenAIOfficial,
)  # OpenAI 官方 (包括 ChatGPT 和 GPT-4)
from astrbot.core.provider.sources.openai_tts_api_source import (
    ProviderOpenAITTSAPI,
)  # OpenAI TTS API (包括 Whisper 和 TTS)
from astrbot.core.provider.sources.sensevoice_selfhosted_source import (
    ProviderSenseVoiceSTTSelfHost,
)  # SenseVoice 自托管 STT
from astrbot.core.provider.sources.volcengine_tts import (
    ProviderVolcengineTTS,
)  # 火山引擎 TTS
from astrbot.core.provider.sources.whisper_api_source import (
    ProviderOpenAIWhisperAPI,
)  # OpenAI Whisper API
from astrbot.core.provider.sources.whisper_selfhosted_source import (
    ProviderOpenAIWhisperSelfHost,
)  # OpenAI Whisper 自托管
from astrbot.core.provider.sources.zhipu_source import (
    ProviderZhipu,
)  # 智谱 (包括 ChatGLM 和 MOSS)

__all__ = [
    "Provider",
    "STTProvider",
    "TTSProvider",
    "EmbeddingProvider",
    "Personality",
    "ProviderRequest",
    "ProviderType",
    "ProviderMetaData",
    "LLMResponse",
    "ToolCallsResult",
    "AssistantMessageSegment",
    "ToolCallMessageSegment",
    "ProviderManager",
    "ProviderAnthropic",
    "OTTSProvider",
    "AzureNativeProvider",
    "AzureTTSProvider",
    "ProviderDashscope",
    "ProviderDashscopeTTSAPI",
    "ProviderDify",
    "ProviderEdgeTTS",
    "ProviderFishAudioTTSAPI",
    "ServeTTSRequest",
    "ServeReferenceAudio",
    "GeminiEmbeddingProvider",
    "ProviderGoogleGenAI",
    "ProviderGeminiTTSAPI",
    "ProviderGSVTTS",
    "ProviderGSVITTS",
    "ProviderMiniMaxTTSAPI",
    "OpenAIEmbeddingProvider",
    "ProviderOpenAIOfficial",
    "ProviderOpenAITTSAPI",
    "ProviderSenseVoiceSTTSelfHost",
    "ProviderVolcengineTTS",
    "ProviderOpenAIWhisperAPI",
    "ProviderOpenAIWhisperSelfHost",
    "ProviderZhipu",
]
