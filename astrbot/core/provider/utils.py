from typing import Literal


def resolve_openai_compatible_base_url(
    api_base: str,
    mode: Literal["auto", "force_v1", "as_is"] = "auto",
    default_base: str = "https://api.openai.com/v1",
) -> str:
    """Resolve OpenAI-compatible API base URL with configurable /v1 suffix handling.

    Args:
        api_base: The user-provided API base URL.
        mode: How to handle the /v1 suffix:
            - "auto": Add /v1 if not present (default).
            - "force_v1": Always add /v1 suffix.
            - "as_is": Keep the URL as-is without modification.
        default_base: Default base URL to use if api_base is empty.

    Returns:
        The resolved API base URL.
    """
    api_base = api_base.strip()
    if not api_base:
        return default_base

    if mode == "as_is":
        return api_base.removesuffix("/")

    if mode == "force_v1":
        api_base = api_base.removesuffix("/")
        if not api_base.endswith("/v1"):
            api_base = f"{api_base}/v1"
        return api_base

    # mode == "auto"
    api_base = api_base.removesuffix("/")
    if not api_base.endswith("/v1"):
        api_base = f"{api_base}/v1"
    return api_base
