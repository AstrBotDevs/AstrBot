# This file was originally created to adapt to glm-4v-flash, which only supports one image in the context.
# It is no longer specifically adapted to Zhipu's models. To ensure compatibility, this

import re
from typing import Any

from openai.types.chat import ChatCompletion

from astrbot.core.agent.tool import ToolSet

from ..entities import LLMResponse
from ..register import register_provider_adapter
from .openai_source import ProviderOpenAIOfficial

# GLM role/control tokens that may leak into response text.
# e.g. <|endoftext|>, <|user|>, <|assistant|>, <|system|>, <|observation|>
_GLM_ROLE_TOKEN_RE = re.compile(
    r"<\|(?:endoftext|user|assistant|system|observation)\|>",
    re.IGNORECASE,
)

# GLM's "null response" signal — the model outputs exactly <None> (capital N, like Python's
# None literal) to indicate it has nothing to say.  We intentionally do NOT use re.IGNORECASE
# here: GLM always emits <None> with a capital N, and a case-insensitive match could
# accidentally remove unrelated HTML/XML-like content that merely starts with "none".
_GLM_NULL_TOKEN_RE = re.compile(r"<None>")


@register_provider_adapter("zhipu_chat_completion", "智谱 Chat Completion 提供商适配器")
class ProviderZhipu(ProviderOpenAIOfficial):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        super().__init__(provider_config, provider_settings)

    @staticmethod
    def _clean_glm_special_tokens(text: str) -> str:
        """Remove GLM-specific non-standard special tokens from response text.

        GLM models sometimes emit internal control tokens that are not meant to be
        shown to users:

        - ``<None>``  — model's signal for "no response needed"
        - ``<|endoftext|>``, ``<|user|>``, ``<|assistant|>``, etc. — role / EOS tokens
          that occasionally leak out of the model into the visible content.
        """
        text = _GLM_ROLE_TOKEN_RE.sub("", text)
        text = _GLM_NULL_TOKEN_RE.sub("", text)
        # Collapse multiple spaces left behind after token removal
        text = re.sub(r"[ \t]{2,}", " ", text)
        return text.strip()

    @staticmethod
    def _normalize_content(raw_content: Any, strip: bool = True) -> str:
        """Normalize content and strip GLM-specific non-standard tokens."""
        base = ProviderOpenAIOfficial._normalize_content(raw_content, strip)
        return ProviderZhipu._clean_glm_special_tokens(base)

    async def _parse_openai_completion(
        self, completion: ChatCompletion, tools: ToolSet | None
    ) -> LLMResponse:
        """Parse completion and apply an extra GLM token-cleaning pass.

        Even though ``_normalize_content`` is already overridden above, we do a
        second cleaning pass here to handle cases where special tokens span
        multiple streaming chunks and therefore survive the per-chunk normalization
        but appear in the fully-assembled final text.
        """
        llm_response = await super()._parse_openai_completion(completion, tools)

        # Apply GLM special token cleaning to the assembled completion text.
        # Use the completion_text setter so that non-Plain components (e.g. tool calls)
        # in the chain are preserved; only the Plain text segments are updated in-place.
        if llm_response.completion_text:
            cleaned = self._clean_glm_special_tokens(llm_response.completion_text)
            if cleaned != llm_response.completion_text:
                llm_response.completion_text = cleaned

        return llm_response
