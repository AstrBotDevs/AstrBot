import base64
import json
import uuid
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import httpx

from astrbot import logger
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.io import download_file
from astrbot.core.utils.media_utils import convert_audio_to_wav
from astrbot.core.utils.tencent_record_helper import (
    convert_to_pcm_wav,
    tencent_silk_to_wav,
)

from ..entities import ProviderType
from ..provider import STTProvider
from ..register import register_provider_adapter

DEFAULT_STEPFUN_ASR_API_BASE = "https://api.stepfun.com/step_plan/v1"
DEFAULT_STEPFUN_ASR_MODEL = "stepaudio-2.5-asr"

SUPPORTED_AUDIO_FORMATS = {"mp3", "wav", "ogg", "pcm"}


class StepFunASRError(Exception):
    pass


def normalize_timeout(timeout: int | str | None) -> int | None:
    if timeout in (None, ""):
        return None
    if isinstance(timeout, str):
        return int(timeout)
    return timeout


def normalize_bool(value: bool | str | int | None, default: bool) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "yes", "on", "enabled"}


def build_api_url(api_base: str) -> str:
    normalized_api_base = (api_base or DEFAULT_STEPFUN_ASR_API_BASE).rstrip("/")
    if normalized_api_base.endswith("/audio/asr/sse"):
        return normalized_api_base
    return normalized_api_base + "/audio/asr/sse"


def build_headers(api_key: str) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def sanitize_proxy_url(proxy: str) -> str:
    try:
        parsed = urlparse(proxy)
        if "@" not in parsed.netloc:
            return proxy
        sanitized_netloc = parsed.netloc.split("@", 1)[1]
        return urlunparse(parsed._replace(netloc=sanitized_netloc))
    except Exception:
        return "<redacted>"


def create_http_client(timeout: int | None, proxy: str) -> httpx.AsyncClient:
    client_kwargs: dict[str, object] = {
        "timeout": timeout,
        "follow_redirects": True,
    }
    if proxy:
        logger.info("[StepFun ASR] Using proxy: %s", sanitize_proxy_url(proxy))
        client_kwargs["proxy"] = proxy
    return httpx.AsyncClient(**client_kwargs)


def get_temp_dir() -> Path:
    temp_dir = Path(get_astrbot_temp_path())
    temp_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir


async def detect_audio_format(file_path: Path) -> str | None:
    try:
        with file_path.open("rb") as file:
            header = file.read(64)
    except FileNotFoundError:
        return None

    if header[:4] == b"RIFF" and header[8:12] == b"WAVE":
        return "wav"
    if header.startswith(b"#!AMR"):
        return "amr"
    if (
        header.startswith(b"#!SILK_V3")
        or header.startswith(b"\x02#!SILK_V3")
        or b"SILK" in header[:16]
    ):
        return "silk"
    if header.startswith(b"OggS"):
        return "ogg"
    if header[:3] == b"ID3" or header[:2] == b"\xff\xfb":
        return "mp3"
    return None


def build_audio_format(audio_type: str) -> dict[str, object]:
    if audio_type == "pcm":
        return {
            "type": "pcm",
            "codec": "pcm_s16le",
            "rate": 16000,
            "bits": 16,
            "channel": 1,
        }
    return {"type": audio_type}


async def prepare_audio_input(
    audio_source: str,
) -> tuple[str, dict[str, object], list[Path]]:
    cleanup_paths: list[Path] = []
    source_path = Path(audio_source)
    is_remote = audio_source.startswith(("http://", "https://"))
    is_tencent = "multimedia.nt.qq.com.cn" in audio_source if is_remote else False

    if is_remote:
        parsed_url = urlparse(audio_source)
        suffix = Path(parsed_url.path).suffix or ".input"
        download_path = get_temp_dir() / f"stepfun_asr_{uuid.uuid4().hex[:8]}{suffix}"
        await download_file(audio_source, str(download_path))
        source_path = download_path
        cleanup_paths.append(download_path)

    if not source_path.exists():
        raise FileNotFoundError(f"File does not exist: {source_path}")

    audio_type = await detect_audio_format(source_path)
    if audio_type is None:
        audio_type = source_path.suffix.lower().lstrip(".")

    if source_path.suffix.lower() in {".amr", ".silk"} or is_tencent:
        file_format = await detect_audio_format(source_path)
        if file_format in {"silk", "amr"}:
            converted_path = get_temp_dir() / f"stepfun_asr_{uuid.uuid4().hex[:8]}.wav"
            cleanup_paths.append(converted_path)
            if file_format == "silk":
                logger.info("Converting silk file to wav for StepFun ASR...")
                await tencent_silk_to_wav(str(source_path), str(converted_path))
            else:
                logger.info("Converting amr file to wav for StepFun ASR...")
                await convert_to_pcm_wav(str(source_path), str(converted_path))
            source_path = converted_path
            audio_type = "wav"

    if audio_type not in SUPPORTED_AUDIO_FORMATS:
        converted_path = get_temp_dir() / f"stepfun_asr_{uuid.uuid4().hex[:8]}.wav"
        cleanup_paths.append(converted_path)
        logger.info("Converting audio file to wav for StepFun ASR...")
        await convert_audio_to_wav(str(source_path), str(converted_path))
        source_path = converted_path
        audio_type = "wav"

    encoded_audio = base64.b64encode(source_path.read_bytes()).decode("utf-8")
    return encoded_audio, build_audio_format(audio_type), cleanup_paths


def cleanup_files(paths: list[Path]) -> None:
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except Exception as exc:
            logger.warning(
                "Failed to remove temporary StepFun ASR file %s: %s",
                path,
                exc,
            )


def _iter_sse_payloads(content: str):
    normalized_content = content.replace("\r\n", "\n")
    for event in normalized_content.split("\n\n"):
        data_lines = []
        for line in event.splitlines():
            if line.startswith("data:"):
                data_lines.append(line[5:].strip())
        if not data_lines and event.strip().startswith("{"):
            data_lines.append(event.strip())
        for data in data_lines:
            if data and data != "[DONE]":
                yield data


def _text_candidate(data: dict) -> str:
    for key in ("text", "transcript", "content", "delta"):
        value = data.get(key)
        if isinstance(value, str) and value:
            return value

    nested_data = data.get("data")
    if isinstance(nested_data, dict):
        for key in ("text", "transcript", "content", "delta"):
            value = nested_data.get(key)
            if isinstance(value, str) and value:
                return value

    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        first_choice = choices[0]
        if isinstance(first_choice, dict):
            delta = first_choice.get("delta")
            if isinstance(delta, dict):
                content = delta.get("content")
                if isinstance(content, str) and content:
                    return content
            message = first_choice.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str) and content:
                    return content
    return ""


def parse_sse_transcription(content: str) -> str:
    done_text = ""
    delta_parts: list[str] = []

    for payload in _iter_sse_payloads(content):
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue

        event_type = str(data.get("type") or data.get("event") or "")
        error = data.get("error")
        if event_type == "error" or error:
            message = data.get("message") or error or data
            raise StepFunASRError(f"StepFun ASR returned error: {message}")

        text = _text_candidate(data)
        if not text:
            continue
        if event_type.endswith(".done"):
            done_text = text
        else:
            delta_parts.append(text)

    result = done_text or "".join(delta_parts)
    if not result.strip():
        raise StepFunASRError("StepFun ASR returned empty transcription")
    return result.strip()


@register_provider_adapter(
    "stepfun_asr",
    "StepFun StepAudio ASR API",
    provider_type=ProviderType.SPEECH_TO_TEXT,
)
class ProviderStepFunASR(STTProvider):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        super().__init__(provider_config, provider_settings)
        self.chosen_api_key = provider_config.get("api_key", "")
        self.api_base = provider_config.get(
            "api_base",
            DEFAULT_STEPFUN_ASR_API_BASE,
        )
        self.proxy = provider_config.get("proxy", "")
        self.timeout = normalize_timeout(provider_config.get("timeout", 20))
        self.language = provider_config.get("stepfun-asr-language", "zh")
        self.enable_itn = normalize_bool(
            provider_config.get("stepfun-asr-enable-itn", True),
            True,
        )
        self.set_model(provider_config.get("model", DEFAULT_STEPFUN_ASR_MODEL))
        self.client = create_http_client(self.timeout, self.proxy)

    async def prepare_audio_input(
        self,
        audio_source: str,
    ) -> tuple[str, dict[str, object], list[Path]]:
        return await prepare_audio_input(audio_source)

    def _build_transcription_options(self) -> dict[str, object]:
        transcription: dict[str, object] = {
            "model": self.model_name,
            "language": self.language,
            "enable_itn": self.enable_itn,
        }
        return transcription

    async def get_text(self, audio_url: str) -> str:
        encoded_audio, audio_format, cleanup_paths = await self.prepare_audio_input(
            audio_url
        )
        payload = {
            "audio": {
                "data": encoded_audio,
                "input": {
                    "transcription": self._build_transcription_options(),
                    "format": audio_format,
                },
            },
        }

        try:
            response = await self.client.post(
                build_api_url(self.api_base),
                headers=build_headers(self.chosen_api_key),
                json=payload,
            )
            try:
                response.raise_for_status()
            except Exception as exc:
                error_text = response.text[:1024]
                raise StepFunASRError(
                    "StepFun ASR API request failed: "
                    f"HTTP {response.status_code}, response: {error_text}"
                ) from exc

            return parse_sse_transcription(response.text)
        finally:
            cleanup_files(cleanup_paths)

    async def terminate(self):
        if self.client:
            await self.client.aclose()
