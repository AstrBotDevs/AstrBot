import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

from astrbot.core.utils.string_utils import normalize_and_dedupe_strings

GOOGLE_CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
VERTEX_AI_DEFAULT_LOCATION = "global"
VERTEX_AI_DEFAULT_API_BASE = "https://aiplatform.googleapis.com"
VERTEX_AI_API_VERSION = "v1"
VERTEX_AI_MODEL_GARDEN_API_VERSION = "v1beta1"
VERTEX_AI_API_KEY_AUTH = "api_key"
VERTEX_AI_JSON_AUTH = "json"
VERTEX_AI_SERVICE_ACCOUNT_AUTH = "service_account"
VERTEX_AI_GOOGLE_GENAI_TYPE = "googlegenai_chat_completion"
VERTEX_AI_API_KEY_FIELD = "vertex_ai_api_key"
VERTEX_AI_MODEL_NAME_SEPARATOR = "/models/"
VERTEX_AI_GOOGLE_MODEL_PREFIX = "google/"
VERTEX_AI_GOOGLE_PUBLISHER_MODEL_PREFIX = "publishers/google/models/"
VERTEX_AI_MODEL_LIST_PAGE_SIZE = "300"
VERTEX_AI_NON_CHAT_MODEL_ID_PARTS = (
    "embedding",
    "-tts",
    "gemini-live",
    "native-audio",
)


def normalize_vertex_ai_auth_type(auth_type: Any) -> str:
    normalized = str(auth_type or VERTEX_AI_JSON_AUTH).strip().lower()
    if normalized == VERTEX_AI_SERVICE_ACCOUNT_AUTH:
        return VERTEX_AI_JSON_AUTH
    return normalized


def normalize_vertex_ai_provider_config(
    provider_config: dict[str, Any],
) -> dict[str, Any]:
    """Normalize Vertex AI source configs for runtime compatibility.

    The dashboard stores Vertex AI API keys in a provider-specific field so the
    service-account JSON field can remain separate. Provider implementations
    still use the common ``key`` list for key rotation, so API-key configs are
    mirrored into ``key`` at runtime. Legacy configs that stored either an API
    key or a pasted service-account JSON in ``key`` remain readable.
    """

    if provider_config.get("provider") != "google-vertex-ai":
        return provider_config

    provider_config = dict(provider_config)
    auth_type = normalize_vertex_ai_auth_type(
        provider_config.get("vertex_ai_auth_type")
    )
    provider_config["vertex_ai_auth_type"] = auth_type

    explicit_api_key = provider_config.get(VERTEX_AI_API_KEY_FIELD)
    legacy_key = provider_config.get("key")
    if explicit_api_key is None:
        provider_config[VERTEX_AI_API_KEY_FIELD] = (
            []
            if _key_value_looks_like_json(legacy_key)
            else _normalize_key_list(legacy_key)
        )

    if auth_type == VERTEX_AI_API_KEY_AUTH:
        provider_config["type"] = VERTEX_AI_GOOGLE_GENAI_TYPE
        provider_config["key"] = _normalize_key_list(
            provider_config.get(VERTEX_AI_API_KEY_FIELD)
        )
    return provider_config


def normalize_vertex_ai_provider_source_config(
    provider_config: dict[str, Any],
) -> dict[str, Any]:
    """Normalize a Vertex AI provider source before persisting it."""

    normalized = normalize_vertex_ai_provider_config(provider_config)
    if normalized.get("provider") == "google-vertex-ai":
        normalized.pop("key", None)
    return normalized


def _normalize_key_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _key_value_looks_like_json(value: Any) -> bool:
    keys = _normalize_key_list(value)
    return bool(keys and keys[0].lstrip().startswith("{"))


def extract_vertex_ai_credentials_json(provider_config: dict[str, Any]) -> str:
    """Return service-account JSON from explicit config or the common key field."""

    credentials_json = str(provider_config.get("vertex_ai_credentials_json") or "")
    if credentials_json.strip():
        return credentials_json

    key = provider_config.get("key") or ""
    if isinstance(key, list):
        key = key[0] if key else ""
    key = str(key).strip()
    if key.startswith("{"):
        return key
    return ""


def to_vertex_ai_genai_model_name(model: Any) -> str:
    """Convert AstrBot-facing Vertex AI model ids to google-genai request ids."""

    model_name = str(model or "").strip()
    if not model_name:
        return model_name
    if model_name.startswith(VERTEX_AI_GOOGLE_PUBLISHER_MODEL_PREFIX):
        return model_name
    if model_name.startswith(VERTEX_AI_GOOGLE_MODEL_PREFIX):
        return (
            f"{VERTEX_AI_GOOGLE_PUBLISHER_MODEL_PREFIX}"
            f"{model_name.removeprefix(VERTEX_AI_GOOGLE_MODEL_PREFIX)}"
        )
    if model_name.startswith("models/"):
        return f"{VERTEX_AI_GOOGLE_PUBLISHER_MODEL_PREFIX}{model_name.removeprefix('models/')}"
    if model_name.startswith("gemini-"):
        return f"{VERTEX_AI_GOOGLE_PUBLISHER_MODEL_PREFIX}{model_name}"
    return model_name


def make_vertex_ai_refresh_request(provider_config: dict[str, Any]) -> Any:
    try:
        from google.auth.transport.requests import Request
    except ImportError as exc:
        raise RuntimeError(
            "google-auth requests transport is required for Vertex AI auth."
        ) from exc

    proxy = str(provider_config.get("proxy") or "").strip()
    if not proxy:
        return Request()

    try:
        import requests
    except ImportError:
        return Request()

    session = requests.Session()
    session.proxies.update({"http": proxy, "https": proxy})
    session.trust_env = False
    return Request(session=session)


def normalize_vertex_ai_location(location: Any) -> str:
    normalized = str(location or "").strip()
    return normalized or VERTEX_AI_DEFAULT_LOCATION


def _normalize_base_url(base_url: str) -> str:
    return base_url.strip().rstrip("/")


def _default_vertex_ai_api_base(location: str) -> str:
    if location == VERTEX_AI_DEFAULT_LOCATION:
        return VERTEX_AI_DEFAULT_API_BASE
    return f"https://{location}-aiplatform.googleapis.com"


def _is_default_vertex_ai_api_base(base_url: str) -> bool:
    parsed = urlparse(base_url)
    return (
        parsed.scheme.lower() == "https"
        and parsed.netloc.lower() == "aiplatform.googleapis.com"
        and parsed.path.strip("/") in {"", VERTEX_AI_API_VERSION}
    )


def _read_service_account_info(provider_config: dict[str, Any]) -> dict[str, Any]:
    credentials_json = extract_vertex_ai_credentials_json(provider_config)
    if credentials_json.strip():
        return json.loads(credentials_json)

    credentials_path = str(provider_config.get("vertex_ai_credentials_path") or "")
    if credentials_path.strip():
        return json.loads(
            Path(credentials_path).expanduser().read_text(encoding="utf-8")
        )

    return {}


def resolve_vertex_ai_project_id(provider_config: dict[str, Any]) -> str:
    project_id = str(provider_config.get("vertex_ai_project_id") or "").strip()
    if project_id:
        return project_id

    try:
        credentials_json = extract_vertex_ai_credentials_json(provider_config)
        if credentials_json.strip():
            info = json.loads(credentials_json)
        else:
            info = _read_service_account_info(provider_config)
    except Exception:
        return ""
    return str(info.get("project_id") or "").strip()


def build_vertex_ai_publisher_models_url(provider_config: dict[str, Any]) -> str:
    """Build the native Vertex AI publisher models URL for model discovery."""

    location = normalize_vertex_ai_location(provider_config.get("vertex_ai_location"))
    configured_base_url = _normalize_base_url(
        str(provider_config.get("api_base") or "")
    )
    if not configured_base_url or _is_default_vertex_ai_api_base(configured_base_url):
        base_url = _default_vertex_ai_api_base(location)
    else:
        base_url = configured_base_url

    parsed = urlparse(base_url)
    path_parts = [
        part
        for part in parsed.path.strip("/").split("/")
        if part and part != VERTEX_AI_API_VERSION
    ]
    path = "/".join([VERTEX_AI_MODEL_GARDEN_API_VERSION, *path_parts])
    path = f"/{path}/publishers/google/models"
    return urlunparse(parsed._replace(path=path, query="", fragment=""))


async def fetch_vertex_ai_publisher_models(
    http_client: Any,
    url: str,
    headers: dict[str, str],
) -> list[str]:
    """Fetch Gemini publisher model IDs from Vertex AI Model Garden."""

    params = {
        "pageSize": VERTEX_AI_MODEL_LIST_PAGE_SIZE,
    }
    model_ids: list[str] = []
    next_page_token = None

    while True:
        if next_page_token:
            params["pageToken"] = next_page_token
        else:
            params.pop("pageToken", None)

        response = await http_client.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()

        for model in data.get("publisherModels", data.get("models", [])):
            name = str(model.get("name") or "").strip()
            if not name:
                continue
            if VERTEX_AI_MODEL_NAME_SEPARATOR in name:
                name = name.rsplit(VERTEX_AI_MODEL_NAME_SEPARATOR, 1)[1]
            elif name.startswith("models/"):
                name = name.removeprefix("models/")
            if not _is_vertex_ai_chat_model_id(name):
                continue
            model_ids.append(f"{VERTEX_AI_GOOGLE_MODEL_PREFIX}{name}")

        next_page_token = data.get("nextPageToken") or data.get("next_page_token")
        if not next_page_token:
            break

    return sorted(normalize_and_dedupe_strings(model_ids))


def _is_vertex_ai_chat_model_id(model_id: str) -> bool:
    if not model_id.startswith("gemini-"):
        return False
    return not any(part in model_id for part in VERTEX_AI_NON_CHAT_MODEL_ID_PARTS)
