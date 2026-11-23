import os

from google.genai import types


def set_gemini_user_agent(http_options: types.HttpOptions, user_agent: str) -> None:
    """Set one AstrBot user-agent header even when SDK headers are absent."""
    headers = http_options.headers
    if headers is None:
        headers = {}
        http_options.headers = headers
    headers["user-agent"] = user_agent
    headers.pop("User-Agent", None)


def gemini_api_version() -> str | None:
    """Keep the Developer API on v1beta by default for preview models.

    Returns:
        The Developer API default, or None to let the SDK resolve an explicit
        environment override or its Enterprise (Vertex AI) default.
    """
    enterprise = os.getenv(
        "GOOGLE_GENAI_USE_ENTERPRISE", os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "")
    )
    if os.getenv("GOOGLE_GENAI_API_VERSION") or enterprise.lower() in {"true", "1"}:
        return None
    return "v1beta"


def build_gemini_http_options(
    api_base: str | None, timeout: int, headers: dict[str, str]
) -> types.HttpOptions:
    """Apply common SDK version, timeout, headers, and endpoint settings."""
    options = types.HttpOptions(
        api_version=gemini_api_version(), timeout=timeout * 1000, headers=headers
    )
    if api_base:
        options.base_url = api_base.removesuffix("/")
    return options
