from astrbot import __version__

DEFAULT_USER_AGENT = f"astrbot/{__version__}"
CONVERSATION_ID_HEADER = "x-astrbot-conversation-id"


def build_provider_headers(custom_headers: object = None) -> dict[str, str]:
    """Build provider headers with an overridable AstrBot user agent.

    Args:
        custom_headers: Optional header mapping from provider configuration.

    Returns:
        A new header dictionary with string values and one User-Agent header.
    """
    headers = {"User-Agent": DEFAULT_USER_AGENT}
    if isinstance(custom_headers, dict):
        for name, value in custom_headers.items():
            name, value = str(name), str(value)
            if name.lower() == "user-agent":
                if value.strip():
                    headers["User-Agent"] = value
            else:
                headers[name] = value
    return headers


def build_conversation_headers(conversation_id: str | None) -> dict[str, str]:
    """Build request headers for a provider conversation.

    Args:
        conversation_id: AstrBot conversation ID to associate with the request.

    Returns:
        A header mapping containing the conversation ID, or an empty mapping when
        no conversation ID is available.
    """
    if not conversation_id:
        return {}
    return {CONVERSATION_ID_HEADER: str(conversation_id)}
