import json
import uuid
from contextlib import suppress
from pathlib import Path

import httpx

from astrbot.core.utils.astrbot_path import get_astrbot_temp_path

from ..entities import ProviderType
from ..provider import TTSProvider
from ..register import register_provider_adapter


class DeepSeekTTSError(Exception):
    """Raised when DeepSeek TTS cannot produce a complete WAV response."""


@register_provider_adapter(
    "deepseek_tts_api",
    "DeepSeek TTS API",
    provider_type=ProviderType.TEXT_TO_SPEECH,
)
class ProviderDeepSeekTTSAPI(TTSProvider):
    """DeepSeek TTS provider using the official streaming HTTP endpoint."""

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
        self.voice_id = provider_config.get("deepseek-tts-voice", "stella")
        self.filter_markdown = provider_config.get("deepseek-tts-filter-markdown", True)

        timeout = provider_config.get("timeout", 20)
        if isinstance(timeout, str):
            timeout = timeout.strip()
        self.client = httpx.AsyncClient(
            timeout=float(timeout) if timeout else None,
            proxy=provider_config.get("proxy") or None,
            follow_redirects=True,
        )

    async def get_audio(self, text: str) -> str:
        """Synthesize text into a local WAV file.

        Args:
            text: Text to synthesize. The input is never truncated.

        Returns:
            Path to the completed WAV file.

        Raises:
            ValueError: If the text is blank or exceeds an official input limit.
            DeepSeekTTSError: If the request, transfer, or WAV validation fails.
        """
        if not text.strip():
            raise ValueError("DeepSeek TTS text must not be blank")

        # DeepSeek counts CJK ideographs as two billable characters.
        billable_characters = sum(
            2
            if (
                0x3400 <= ord(char) <= 0x4DBF
                or 0x4E00 <= ord(char) <= 0x9FFF
                or 0xF900 <= ord(char) <= 0xFAFF
                or 0x20000 <= ord(char) <= 0x323AF
            )
            else 1
            for char in text
        )
        if billable_characters > 10000:
            raise ValueError(
                "DeepSeek TTS text contains "
                f"{billable_characters} billable characters; the maximum is 10000"
            )

        payload = json.dumps(
            {
                "text": text,
                "voice_id": self.voice_id,
                "format": "wav",
                "filter_markdown": self.filter_markdown,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(payload) > 64 * 1024:
            raise ValueError(
                f"DeepSeek TTS request body is {len(payload)} bytes; "
                "the maximum is 65536 bytes"
            )

        temp_dir = Path(get_astrbot_temp_path())
        temp_dir.mkdir(parents=True, exist_ok=True)
        output_path = temp_dir / f"deepseek_tts_api_{uuid.uuid4().hex}.wav"
        url = (
            self.api_base
            if self.api_base.endswith("/tools/tts")
            else f"{self.api_base}/tools/tts"
        )
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.chosen_api_key}",
            **self.request_headers,
        }
        completed = False
        try:
            async with self.client.stream(
                "POST", url, headers=headers, content=payload
            ) as response:
                if response.status_code != 200:
                    raise DeepSeekTTSError(
                        f"DeepSeek TTS request failed with HTTP {response.status_code}"
                    )

                content_type = (
                    response.headers.get("Content-Type", "")
                    .split(";", 1)[0]
                    .strip()
                    .lower()
                )
                if content_type and content_type not in {
                    "audio/wav",
                    "audio/x-wav",
                    "audio/wave",
                    "application/octet-stream",
                }:
                    raise DeepSeekTTSError(
                        "DeepSeek TTS returned a non-audio response "
                        f"(Content-Type: {content_type})"
                    )

                header = bytearray()
                wav_header_written = False
                with output_path.open("wb") as audio_file:
                    async for chunk in response.aiter_bytes(65536):
                        if not chunk:
                            continue
                        if not wav_header_written:
                            header_size = 12 - len(header)
                            header.extend(chunk[:header_size])
                            chunk = chunk[header_size:]
                            if len(header) < 12:
                                continue
                            if header[:4] != b"RIFF" or header[8:12] != b"WAVE":
                                raise DeepSeekTTSError(
                                    "DeepSeek TTS returned invalid WAV audio"
                                )
                            audio_file.write(header)
                            wav_header_written = True
                        audio_file.write(chunk)

                if not header:
                    raise DeepSeekTTSError("DeepSeek TTS returned an empty response")
                if not wav_header_written:
                    raise DeepSeekTTSError(
                        "DeepSeek TTS returned an incomplete WAV header"
                    )

            completed = True
        except (httpx.HTTPError, OSError) as exc:
            raise DeepSeekTTSError(
                "DeepSeek TTS request or audio transfer failed"
            ) from exc
        finally:
            if not completed:
                with suppress(OSError):
                    output_path.unlink(missing_ok=True)

        return str(output_path)

    async def terminate(self) -> None:
        """Close the shared HTTP client."""
        await self.client.aclose()
