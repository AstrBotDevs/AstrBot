import uuid
import wave
from contextlib import suppress
from pathlib import Path

import httpx

from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.media_utils import MediaResolver, ensure_wav

from ..entities import ProviderType
from ..provider import STTProvider
from ..register import register_provider_adapter

_DEEPSEEK_STT_MAX_BYTES = 8 * 1024 * 1024
_DEEPSEEK_STT_MAX_DURATION_SECONDS = 120
_DEEPSEEK_STT_WAV_SAMPLE_RATES = {8000, 16000, 22050, 24000, 32000, 44100, 48000}


class DeepSeekSTTError(Exception):
    """Raised when DeepSeek STT cannot return a valid transcription."""


@register_provider_adapter(
    "deepseek_stt_api",
    "DeepSeek STT API",
    provider_type=ProviderType.SPEECH_TO_TEXT,
)
class ProviderDeepSeekSTTAPI(STTProvider):
    """DeepSeek speech recognition provider using the official ASR endpoint."""

    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        super().__init__(provider_config, provider_settings)
        self.chosen_api_key = provider_config.get("api_key", "")
        self.api_base = (
            provider_config.get("api_base") or "https://api.deepseek.com/v1"
        ).rstrip("/")

        timeout = provider_config.get("timeout", 120)
        if isinstance(timeout, str):
            timeout = timeout.strip()
        request_headers = {
            key: value
            for key, value in self.request_headers.items()
            if key.lower() not in {"authorization", "content-type"}
        }
        self.client = httpx.AsyncClient(
            timeout=float(timeout) if timeout else None,
            proxy=provider_config.get("proxy") or None,
            follow_redirects=True,
            headers=request_headers,
        )

    async def get_text(self, audio_url: str) -> str:
        """Transcribe an audio reference with DeepSeek ASR.

        Existing compatible WAV files are uploaded directly. Other audio is
        converted once to mono 16 kHz, 16-bit PCM WAV. Resolver-owned files and
        this provider's conversion output are removed on every exit path.

        Args:
            audio_url: Local path, file URI, URL, or encoded audio reference.

        Returns:
            The transcription, or an empty string when no speech was recognized.

        Raises:
            FileNotFoundError: If a local input file does not exist.
            ValueError: If the input is empty or the upload exceeds API limits.
            DeepSeekSTTError: If conversion output, HTTP, or response data is invalid.
        """
        temp_dir = Path(get_astrbot_temp_path())
        temp_dir.mkdir(parents=True, exist_ok=True)
        converted_path = temp_dir / f"deepseek_stt_api_{uuid.uuid4().hex}.wav"

        try:
            async with MediaResolver(
                audio_url,
                media_type="file",
                default_suffix=".wav",
            ).as_path() as source:
                if not source.path.is_file():
                    raise FileNotFoundError("DeepSeek STT input audio does not exist")
                if source.path.stat().st_size == 0:
                    raise ValueError("DeepSeek STT input audio is empty")

                try:
                    with wave.open(str(source.path), "rb") as wav_file:
                        compatible_wav = (
                            wav_file.getcomptype() == "NONE"
                            and wav_file.getsampwidth() == 2
                            and wav_file.getnchannels() in {1, 2}
                            and wav_file.getframerate()
                            in _DEEPSEEK_STT_WAV_SAMPLE_RATES
                        )
                except (wave.Error, EOFError):
                    compatible_wav = False

                if compatible_wav:
                    upload_path = source.path
                else:
                    # The pipeline may already have converted platform audio to WAV;
                    # compatible output above is reused instead of being transcoded.
                    await ensure_wav(
                        str(source.path),
                        str(converted_path),
                        sample_rate=16000,
                        channels=1,
                    )
                    upload_path = converted_path

                try:
                    with wave.open(str(upload_path), "rb") as wav_file:
                        if (
                            wav_file.getcomptype() != "NONE"
                            or wav_file.getsampwidth() != 2
                            or wav_file.getnchannels() not in {1, 2}
                            or wav_file.getframerate()
                            not in _DEEPSEEK_STT_WAV_SAMPLE_RATES
                        ):
                            raise DeepSeekSTTError(
                                "DeepSeek STT audio conversion produced an incompatible WAV"
                            )
                        duration = wav_file.getnframes() / wav_file.getframerate()
                except (wave.Error, EOFError) as exc:
                    raise DeepSeekSTTError(
                        "DeepSeek STT audio conversion did not produce valid PCM WAV"
                    ) from exc

                upload_size = upload_path.stat().st_size
                if upload_size == 0:
                    raise ValueError("DeepSeek STT upload audio is empty")
                if upload_size > _DEEPSEEK_STT_MAX_BYTES:
                    raise ValueError("DeepSeek STT audio exceeds the 8 MiB limit")
                if duration > _DEEPSEEK_STT_MAX_DURATION_SECONDS:
                    raise ValueError("DeepSeek STT audio exceeds the 120 second limit")

                url = (
                    self.api_base
                    if self.api_base.endswith("/tools/asr")
                    else f"{self.api_base}/tools/asr"
                )
                with upload_path.open("rb") as audio_file:
                    response = await self.client.post(
                        url,
                        headers={"Authorization": f"Bearer {self.chosen_api_key}"},
                        files={"file": ("audio.wav", audio_file, "audio/wav")},
                    )

                if response.status_code != 200:
                    raise DeepSeekSTTError(
                        f"DeepSeek STT request failed with HTTP {response.status_code}"
                    )
                try:
                    data = response.json()
                except ValueError as exc:
                    raise DeepSeekSTTError(
                        "DeepSeek STT returned a non-JSON response"
                    ) from exc
                if not isinstance(data, dict) or not isinstance(data.get("text"), str):
                    raise DeepSeekSTTError(
                        "DeepSeek STT response is missing a string text field"
                    )
                return data["text"].strip()
        except httpx.HTTPError as exc:
            raise DeepSeekSTTError("DeepSeek STT request failed") from exc
        finally:
            # Never remove the caller's original audio; this path is unique to us.
            with suppress(OSError):
                converted_path.unlink(missing_ok=True)

    async def terminate(self) -> None:
        """Close the shared asynchronous HTTP client."""
        await self.client.aclose()
