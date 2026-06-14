from pathlib import Path

import httpx

from astrbot import logger
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.media_utils import MediaResolver, describe_media_ref

DEFAULT_MIMO_API_BASE = "https://api.xiaomimimo.com/v1"
DEFAULT_MIMO_TTS_MODEL = "mimo-v2-tts"
DEFAULT_MIMO_TTS_VOICE = "mimo_default"
DEFAULT_MIMO_TTS_SEED_TEXT = "Hello, MiMo, have you had lunch?"
DEFAULT_MIMO_STT_MODEL = "mimo-v2-omni"
DEFAULT_MIMO_STT_SYSTEM_PROMPT = (
    "You are a speech transcription assistant. "
    "Transcribe the spoken content from the audio exactly and return only the transcription text."
)
DEFAULT_MIMO_STT_USER_PROMPT = (
    "Please transcribe the content of the audio and return only the transcription text."
)


class MiMoAPIError(Exception):
    pass


def normalize_timeout(timeout: int | str | None) -> int | None:
    if timeout in (None, ""):
        return None
    if isinstance(timeout, str):
        return int(timeout)
    return timeout


def build_headers(api_key: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def get_temp_dir() -> Path:
    temp_dir = Path(get_astrbot_temp_path())
    temp_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir


def create_http_client(timeout: int | None, proxy: str) -> httpx.AsyncClient:
    client_kwargs: dict = {
        "timeout": timeout,
        "follow_redirects": True,
    }
    if proxy:
        logger.info("[MiMo API] Using proxy: %s", proxy)
        client_kwargs["proxy"] = proxy
    return httpx.AsyncClient(**client_kwargs)


def build_api_url(api_base: str) -> str:
    normalized_api_base = api_base.rstrip("/")
    if normalized_api_base.endswith("/chat/completions"):
        return normalized_api_base
    return normalized_api_base + "/chat/completions"


async def prepare_audio_input(audio_source: str) -> tuple[str, list[Path]]:
    audio_data = await MediaResolver(
        audio_source,
        media_type="audio",
        default_suffix=".wav",
    ).to_base64_data(
        strict=True,
        target_format="wav",
    )
    if audio_data is None:
        raise ValueError(f"Invalid audio data: {describe_media_ref(audio_source)}")
    return audio_data.base64_data, []


def cleanup_files(paths: list[Path]) -> None:
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except Exception as exc:
            logger.warning("Failed to remove temporary MiMo file %s: %s", path, exc)
