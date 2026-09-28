import asyncio
import base64
import binascii
import io
import json
import struct
import wave
from collections.abc import AsyncIterable, AsyncIterator
from pathlib import Path

import aiohttp

from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.datetime_utils import generate_timestamp_id

from ..entities import ProviderType
from ..provider import TTSProvider
from ..register import register_provider_adapter

DEFAULT_API_BASE = "https://api.modelbest.cn/v1"
MAX_AUDIO_BYTES = 100 * 1024 * 1024


class ModelBestVoxCPMError(Exception):
    """Raised when ModelBest cannot synthesize a valid VoxCPM response."""


def _decode_sse_event(data_lines: list[str]) -> dict[str, object]:
    """Decode one Server-Sent Event payload.

    Args:
        data_lines: Values collected from the event's ``data:`` lines.

    Returns:
        The decoded JSON object.

    Raises:
        ModelBestVoxCPMError: If the event does not contain a JSON object.
    """
    try:
        event = json.loads("\n".join(data_lines))
    except json.JSONDecodeError as exc:
        raise ModelBestVoxCPMError(
            "ModelBest VoxCPM returned invalid SSE event data"
        ) from exc
    if not isinstance(event, dict):
        raise ModelBestVoxCPMError("ModelBest VoxCPM returned an invalid SSE event")
    return event


async def _iter_sse_events(
    chunks: AsyncIterable[bytes],
) -> AsyncIterator[dict[str, object]]:
    """Parse SSE events from arbitrarily split network chunks.

    Args:
        chunks: Byte chunks from the HTTP response body.

    Yields:
        Decoded JSON objects from SSE ``data:`` fields.

    Raises:
        ModelBestVoxCPMError: If the stream contains invalid UTF-8 or JSON.
    """
    buffer = bytearray()
    data_lines: list[str] = []

    async for chunk in chunks:
        buffer.extend(chunk)
        while b"\n" in buffer:
            raw_line, _, remainder = buffer.partition(b"\n")
            buffer = bytearray(remainder)
            try:
                line = raw_line.rstrip(b"\r").decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ModelBestVoxCPMError(
                    "ModelBest VoxCPM returned invalid SSE text"
                ) from exc

            if not line:
                if data_lines:
                    yield _decode_sse_event(data_lines)
                    data_lines = []
            elif line.startswith("data:"):
                data_lines.append(line.removeprefix("data:").lstrip())

    if buffer:
        try:
            line = bytes(buffer).rstrip(b"\r").decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ModelBestVoxCPMError(
                "ModelBest VoxCPM returned invalid SSE text"
            ) from exc
        if line.startswith("data:"):
            data_lines.append(line.removeprefix("data:").lstrip())

    if data_lines:
        yield _decode_sse_event(data_lines)


def _finalize_streamed_wav(audio: bytes) -> bytes:
    """Repair placeholder WAV sizes and validate the completed audio.

    Args:
        audio: Concatenated WAV bytes from ModelBest SSE events.

    Returns:
        A valid WAV byte string with final RIFF and data sizes.

    Raises:
        ModelBestVoxCPMError: If the response is not a non-empty PCM WAV.
    """
    if len(audio) < 12 or audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
        raise ModelBestVoxCPMError(
            "ModelBest VoxCPM returned data that is not a RIFF/WAVE file"
        )

    repaired = bytearray(audio)
    struct.pack_into("<I", repaired, 4, len(repaired) - 8)

    cursor = 12
    data_found = False
    while cursor + 8 <= len(repaired):
        chunk_id = bytes(repaired[cursor : cursor + 4])
        chunk_size = int.from_bytes(repaired[cursor + 4 : cursor + 8], "little")
        chunk_start = cursor + 8
        if chunk_id == b"data":
            struct.pack_into("<I", repaired, cursor + 4, len(repaired) - chunk_start)
            data_found = True
            break
        if chunk_size == 0xFFFFFFFF or chunk_start + chunk_size > len(repaired):
            raise ModelBestVoxCPMError(
                "ModelBest VoxCPM returned a malformed WAV chunk"
            )
        cursor = chunk_start + chunk_size + (chunk_size & 1)

    if not data_found:
        raise ModelBestVoxCPMError("ModelBest VoxCPM returned a WAV without audio data")

    try:
        with wave.open(io.BytesIO(repaired), "rb") as wav_file:
            if wav_file.getcomptype() != "NONE":
                raise ModelBestVoxCPMError(
                    "ModelBest VoxCPM returned compressed WAV audio"
                )
            if wav_file.getnframes() < 1 or wav_file.getframerate() < 1:
                raise ModelBestVoxCPMError("ModelBest VoxCPM returned an empty WAV")
    except wave.Error as exc:
        raise ModelBestVoxCPMError("ModelBest VoxCPM returned an invalid WAV") from exc

    return bytes(repaired)


@register_provider_adapter(
    "modelbest_voxcpm_tts_api",
    "ModelBest VoxCPM TTS API",
    provider_type=ProviderType.TEXT_TO_SPEECH,
)
class ProviderModelBestVoxCPMTTSAPI(TTSProvider):
    """VoxCPM speech synthesis through ModelBest's hosted SSE API."""

    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        super().__init__(provider_config, provider_settings)
        self.api_key = str(provider_config.get("api_key", "") or "").strip()
        self.api_base = str(
            provider_config.get("api_base", DEFAULT_API_BASE) or DEFAULT_API_BASE
        ).rstrip("/")
        self.set_model(str(provider_config.get("model", "VoxCPM2") or "").strip())
        self.proxy = str(provider_config.get("proxy", "") or "").strip()
        try:
            self.timeout = int(provider_config.get("timeout", 120))
        except (TypeError, ValueError) as exc:
            raise ValueError("timeout must be a positive integer") from exc
        if self.timeout <= 0:
            raise ValueError("timeout must be a positive integer")

    async def get_audio(self, text: str) -> str:
        """Synthesize text and save the completed WAV to AstrBot's temp path.

        Args:
            text: Text to synthesize.

        Returns:
            Absolute path to the synthesized WAV file.

        Raises:
            ValueError: If required provider configuration is missing.
            ModelBestVoxCPMError: If the request or returned audio is invalid.
        """
        if not self.api_key:
            raise ValueError("ModelBest VoxCPM TTS requires an API key")
        if not self.model_name:
            raise ValueError("ModelBest VoxCPM TTS requires a model ID")

        payload = {
            "model": self.model_name,
            "input": text,
            "voice": "default",
            "response_format": "wav",
            "stream": True,
        }
        headers = {
            **self.request_headers,
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "text/event-stream",
        }
        timeout = aiohttp.ClientTimeout(
            total=None,
            connect=min(10, self.timeout),
            sock_read=self.timeout,
        )

        audio_chunks: list[bytes] = []
        total_audio_bytes = 0
        completed = False
        try:
            async with (
                aiohttp.ClientSession() as session,
                session.post(
                    f"{self.api_base}/audio/speech",
                    headers=headers,
                    json=payload,
                    proxy=self.proxy or None,
                    timeout=timeout,
                ) as response,
            ):
                if response.status != 200:
                    error_text = (await response.text())[:1024]
                    raise ModelBestVoxCPMError(
                        "ModelBest VoxCPM TTS request failed: "
                        f"HTTP {response.status}, response: {error_text}"
                    )

                async for event in _iter_sse_events(
                    response.content.iter_chunked(8192)
                ):
                    event_type = event.get("type")
                    if event_type == "error":
                        raise ModelBestVoxCPMError(
                            str(event.get("error") or "ModelBest returned an error")
                        )
                    if event_type == "speech.audio.done":
                        completed = True
                        break
                    if event_type != "speech.audio.delta":
                        continue

                    encoded_audio = event.get("audio")
                    if not isinstance(encoded_audio, str) or not encoded_audio:
                        raise ModelBestVoxCPMError(
                            "ModelBest VoxCPM returned an empty audio chunk"
                        )
                    try:
                        decoded_audio = base64.b64decode(
                            encoded_audio,
                            validate=True,
                        )
                    except (binascii.Error, ValueError) as exc:
                        raise ModelBestVoxCPMError(
                            "ModelBest VoxCPM returned invalid Base64 audio"
                        ) from exc
                    total_audio_bytes += len(decoded_audio)
                    if total_audio_bytes > MAX_AUDIO_BYTES:
                        raise ModelBestVoxCPMError(
                            "ModelBest VoxCPM audio response exceeds 100 MiB"
                        )
                    audio_chunks.append(decoded_audio)
        except (TimeoutError, asyncio.TimeoutError) as exc:
            raise ModelBestVoxCPMError(
                f"ModelBest VoxCPM TTS request timed out after {self.timeout} seconds"
            ) from exc
        except aiohttp.ClientError as exc:
            raise ModelBestVoxCPMError(
                f"ModelBest VoxCPM TTS request failed: {exc}"
            ) from exc

        if not completed:
            raise ModelBestVoxCPMError(
                "ModelBest VoxCPM stream ended before speech.audio.done"
            )
        if not audio_chunks:
            raise ModelBestVoxCPMError("ModelBest VoxCPM returned no audio")

        wav_audio = _finalize_streamed_wav(b"".join(audio_chunks))
        output_dir = Path(get_astrbot_temp_path())
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / (
            f"modelbest_voxcpm_tts_{generate_timestamp_id()}.wav"
        )
        output_path.write_bytes(wav_audio)
        return str(output_path.resolve())
