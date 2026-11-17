import os


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
