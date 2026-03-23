import base64
import uuid
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

import httpx

from astrbot import logger
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.io import download_file
from astrbot.core.utils.tencent_record_helper import (
    convert_to_pcm_wav,
    tencent_silk_to_wav,
)

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
    client_kwargs: dict[str, object] = {
        "timeout": timeout,
        "follow_redirects": True,
    }
    if proxy:
        logger.info("[MiMo API] Using proxy: %s", proxy)
        client_kwargs["proxy"] = proxy
    return httpx.AsyncClient(**cast(dict[str, Any], client_kwargs))


def build_api_url(api_base: str) -> str:
    normalized_api_base = api_base.rstrip("/")
    if normalized_api_base.endswith("/chat/completions"):
        return normalized_api_base
    return normalized_api_base + "/chat/completions"


async def _detect_audio_format(file_path: Path) -> str | None:
    silk_header = b"SILK"
    amr_header = b"#!AMR"

    try:
        with file_path.open("rb") as file:
            file_header = file.read(8)
    except FileNotFoundError:
        return None

    if silk_header in file_header:
        return "silk"
    if amr_header in file_header:
        return "amr"
    return None


async def prepare_audio_input(audio_source: str) -> tuple[str, list[Path]]:
    cleanup_paths: list[Path] = []
    source_path = Path(audio_source)
    is_remote = audio_source.startswith(("http://", "https://"))
    is_tencent = "multimedia.nt.qq.com.cn" in audio_source if is_remote else False

    if is_remote:
        parsed_url = urlparse(audio_source)
        suffix = Path(parsed_url.path).suffix or ".input"
        download_path = get_temp_dir() / f"mimo_audio_{uuid.uuid4().hex[:8]}{suffix}"
        await download_file(audio_source, str(download_path))
        source_path = download_path
        cleanup_paths.append(download_path)

    if not source_path.exists():
        raise FileNotFoundError(f"File does not exist: {source_path}")

    if source_path.suffix.lower() in {".amr", ".silk"} or is_tencent:
        file_format = await _detect_audio_format(source_path)
        if file_format in {"silk", "amr"}:
            converted_path = get_temp_dir() / f"mimo_audio_{uuid.uuid4().hex[:8]}.wav"
            cleanup_paths.append(converted_path)
            if file_format == "silk":
                logger.info("Converting silk file to wav for MiMo STT...")
                await tencent_silk_to_wav(str(source_path), str(converted_path))
            else:
                logger.info("Converting amr file to wav for MiMo STT...")
                await convert_to_pcm_wav(str(source_path), str(converted_path))
            source_path = converted_path

    encoded_audio = base64.b64encode(source_path.read_bytes()).decode("utf-8")
    return encoded_audio, cleanup_paths


def cleanup_files(paths: list[Path]) -> None:
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except Exception as exc:
            logger.warning("Failed to remove temporary MiMo file %s: %s", path, exc)
