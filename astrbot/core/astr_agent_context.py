from dataclasses import dataclass
from astrbot.core.provider import Provider
from astrbot.core.provider.entities import ProviderRequest


@dataclass
class AstrAgentContext:
    provider: Provider
    first_provider_request: ProviderRequest
    curr_provider_request: ProviderRequest
    streaming: bool
