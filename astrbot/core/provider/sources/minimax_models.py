"""Current MiniMax text choices, separate from saved request model IDs."""

import re
from urllib.parse import urlsplit

MINIMAX_TEXT_MODELS = ("MiniMax-M3.1-Flash", "MiniMax-M3")
MINIMAX_SUBSCRIPTION_MODELS = ("MiniMax-M3.1-Flash",)


def is_minimax_api(api_base: str) -> bool:
    return urlsplit(api_base).hostname in {
        "api.minimax.cn",
        "api.minimax.io",
        "api.minimaxi.com",
        "api.minimax.chat",
    }


def filter_minimax_gateway_models(api_base: str, models: list[str]) -> list[str]:
    """Filter only MiniMax text entries on verified gateway routes."""
    host = urlsplit(api_base).hostname
    if host == "openrouter.ai":
        text_pattern = r"^minimax/minimax-(?:m\d|01(?:$|:))"
        current = ("minimax/minimax-m3.1-flash:free", "minimax/minimax-m3")
    elif host == "integrate.api.nvidia.com":
        text_pattern = r"^minimaxai/minimax-(?:m\d|01(?:$|:))"
        current = ("minimaxai/minimax-m3",)
    else:
        return models
    # Do not advertise a gateway model absent from that gateway's response.
    return [model for model in current if model in models] + [
        model for model in models if not re.match(text_pattern, model, re.IGNORECASE)
    ]
