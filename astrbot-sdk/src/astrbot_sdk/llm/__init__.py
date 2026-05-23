"""Canonical SDK LLM/tool/provider entrypoints for P0.5."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .agents import AgentSpec, BaseAgentRunner
    from .entities import (
        LLMToolSpec,
        ProviderMeta,
        ProviderRequest,
        ProviderType,
        RerankResult,
        ToolCallsResult,
    )
    from .providers import (
        EmbeddingProvider,
        ProviderProxy,
        RerankProvider,
        STTProvider,
        TTSAudioChunk,
        TTSProvider,
    )
    from .tools import LLMToolManager

__all__ = [
    "AgentSpec",
    "BaseAgentRunner",
    "EmbeddingProvider",
    "LLMToolManager",
    "LLMToolSpec",
    "ProviderMeta",
    "ProviderProxy",
    "ProviderRequest",
    "ProviderType",
    "RerankProvider",
    "RerankResult",
    "STTProvider",
    "TTSAudioChunk",
    "TTSProvider",
    "ToolCallsResult",
]


def __getattr__(name: str) -> Any:
    if name in {"AgentSpec", "BaseAgentRunner"}:
        from .agents import AgentSpec, BaseAgentRunner

        return {"AgentSpec": AgentSpec, "BaseAgentRunner": BaseAgentRunner}[name]
    if name in {
        "LLMToolSpec",
        "ProviderMeta",
        "ProviderRequest",
        "ProviderType",
        "RerankResult",
        "ToolCallsResult",
    }:
        from .entities import (
            LLMToolSpec,
            ProviderMeta,
            ProviderRequest,
            ProviderType,
            RerankResult,
            ToolCallsResult,
        )

        return {
            "LLMToolSpec": LLMToolSpec,
            "ProviderMeta": ProviderMeta,
            "ProviderRequest": ProviderRequest,
            "ProviderType": ProviderType,
            "RerankResult": RerankResult,
            "ToolCallsResult": ToolCallsResult,
        }[name]
    if name in {
        "EmbeddingProvider",
        "ProviderProxy",
        "RerankProvider",
        "STTProvider",
        "TTSAudioChunk",
        "TTSProvider",
    }:
        from .providers import (
            EmbeddingProvider,
            ProviderProxy,
            RerankProvider,
            STTProvider,
            TTSAudioChunk,
            TTSProvider,
        )

        return {
            "EmbeddingProvider": EmbeddingProvider,
            "ProviderProxy": ProviderProxy,
            "RerankProvider": RerankProvider,
            "STTProvider": STTProvider,
            "TTSAudioChunk": TTSAudioChunk,
            "TTSProvider": TTSProvider,
        }[name]
    if name == "LLMToolManager":
        from .tools import LLMToolManager

        return LLMToolManager
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
