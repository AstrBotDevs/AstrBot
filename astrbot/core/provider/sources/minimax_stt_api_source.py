import mimetypes
import uuid
from pathlib import Path
from urllib.parse import urlparse

import httpx

from astrbot.core import logger
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.io import download_file
from astrbot.core.utils.tencent_record_helper import (
    convert_to_pcm_wav,
    tencent_silk_to_wav,
)

from ..entities import ProviderType
from ..provider import STTProvider
from ..register import register_provider_adapter

DEFAULT_MINIMAX_STT_API_BASE = "https://api.minimax.cn/v1/speech_to_text"
DEFAULT_MINIMAX_STT_MODEL = "asr-1.0"


class MiniMaxSTTAPIError(Exception):
    pass


@register_provider_adapter(
    "minimax_stt_api",
    "MiniMax STT API",
    provider_type=ProviderType.SPEECH_TO_TEXT,
)
class ProviderMiniMaxSTTAPI(STTProvider):
    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.chosen_api_key = provider_config.get("api_key", "")
        self.api_base = provider_config.get("api_base", DEFAULT_MINIMAX_STT_API_BASE)
        self.language = provider_config.get("minimax-stt-language", "")
        self.set_model(provider_config.get("model", DEFAULT_MINIMAX_STT_MODEL))

        timeout = provider_config.get("timeout", 120)
        client_kwargs: dict[str, object] = {
            "timeout": float(timeout) if timeout not in (None, "") else None,
            "follow_redirects": True,
        }
        if proxy := provider_config.get("proxy", ""):
            client_kwargs["proxy"] = proxy
        self.client = httpx.AsyncClient(**client_kwargs)

    async def _prepare_audio_file(self, audio_source: str) -> tuple[Path, list[Path]]:
        cleanup_paths: list[Path] = []
        try:
            source_path = Path(audio_source)
            is_remote = audio_source.startswith(("http://", "https://"))

            if is_remote:
                suffix = Path(urlparse(audio_source).path).suffix or ".input"
                temp_dir = Path(get_astrbot_temp_path())
                temp_dir.mkdir(parents=True, exist_ok=True)
                source_path = temp_dir / f"minimax_stt_{uuid.uuid4().hex[:8]}{suffix}"
                cleanup_paths.append(source_path)
                await download_file(audio_source, str(source_path))

            if not source_path.exists():
                raise FileNotFoundError(f"File does not exist: {source_path}")

            with source_path.open("rb") as audio_file:
                file_header = audio_file.read(8)
            is_silk = b"SILK" in file_header
            is_amr = b"#!AMR" in file_header
            needs_conversion = (
                is_silk or is_amr or source_path.suffix.lower() in {".silk", ".amr"}
            )
            if not needs_conversion:
                return source_path, cleanup_paths

            temp_dir = Path(get_astrbot_temp_path())
            temp_dir.mkdir(parents=True, exist_ok=True)
            converted_path = temp_dir / f"minimax_stt_{uuid.uuid4().hex[:8]}.wav"
            cleanup_paths.append(converted_path)
            if is_silk or source_path.suffix.lower() == ".silk":
                logger.info("Converting silk audio to WAV for MiniMax STT...")
                await tencent_silk_to_wav(str(source_path), str(converted_path))
            else:
                logger.info("Converting AMR audio to WAV for MiniMax STT...")
                await convert_to_pcm_wav(str(source_path), str(converted_path))
            return converted_path, cleanup_paths
        except Exception:
            self._cleanup_files(cleanup_paths)
            raise

    @staticmethod
    def _cleanup_files(paths: list[Path]) -> None:
        for path in paths:
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning(
                    "Failed to remove temporary MiniMax STT file %s: %s",
                    path,
                    exc,
                )

    async def get_text(self, audio_url: str) -> str:
        audio_path, cleanup_paths = await self._prepare_audio_file(audio_url)
        headers = {
            **self.request_headers,
            "Authorization": f"Bearer {self.chosen_api_key}",
        }
        if self.language:
            headers["language"] = self.language

        try:
            content_type = (
                mimetypes.guess_type(audio_path.name)[0] or "application/octet-stream"
            )
            with audio_path.open("rb") as audio_file:
                response = await self.client.post(
                    self.api_base,
                    headers=headers,
                    data={"model": self.model_name, "response_format": "json"},
                    files={
                        "file": (
                            audio_path.name,
                            audio_file,
                            content_type,
                        ),
                    },
                )

            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise MiniMaxSTTAPIError(
                    "MiniMax STT API request failed: "
                    f"HTTP {response.status_code}, response: {response.text[:1024]}"
                ) from exc

            try:
                data = response.json()
            except ValueError as exc:
                raise MiniMaxSTTAPIError(
                    "MiniMax STT API returned an invalid JSON response"
                ) from exc
            text = data.get("text")
            if not isinstance(text, str):
                raise MiniMaxSTTAPIError(
                    "MiniMax STT API returned an invalid transcription"
                )
            return text.strip()
        finally:
            self._cleanup_files(cleanup_paths)

    async def terminate(self):
        if self.client:
            await self.client.aclose()
