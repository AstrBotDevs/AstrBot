import asyncio
from pathlib import Path
from typing import Any

import httpx

from astrbot.core.provider.oauth.openai_oauth_audio_input import (
    BoundedOAuthAudioResolver,
)

OPENAI_TRANSCRIPTIONS_URL = "https://api.openai.com/v1/audio/transcriptions"
DEFAULT_MAX_AUDIO_BYTES = 25 * 1024 * 1024
DEFAULT_TRANSCRIPTION_TIMEOUT = 120.0


class OpenAIOAuthTranscriptionClient:
    """Transcribe audio through the fixed OpenAI API using shared OAuth state."""

    def __init__(
        self,
        oauth_provider: Any,
        *,
        max_audio_bytes: int = DEFAULT_MAX_AUDIO_BYTES,
        timeout: float | None = None,
    ) -> None:
        """Initialize a bounded OAuth transcription client.

        Args:
            oauth_provider: ProviderOpenAIOAuth instance owning shared credentials.
            max_audio_bytes: Maximum resolved audio size accepted for one request.
            timeout: Whole-operation timeout in seconds.

        Raises:
            ValueError: If a size or timeout limit is not positive.
        """
        self.oauth_provider = oauth_provider
        self._closed = False
        self._pending: set[asyncio.Task] = set()
        self.max_audio_bytes = int(max_audio_bytes)
        provider_timeout = getattr(oauth_provider, "timeout", None)
        self.timeout = float(
            timeout
            if timeout is not None
            else provider_timeout or DEFAULT_TRANSCRIPTION_TIMEOUT
        )
        if self.max_audio_bytes <= 0:
            raise ValueError("OAuth 转录文件大小上限必须大于 0。")
        if self.timeout <= 0:
            raise ValueError("OAuth 转录超时时间必须大于 0。")

    async def transcribe_audio(
        self,
        audio_url: str,
        model: str = "gpt-4o-transcribe",
        language: str | None = None,
        prompt: str | None = None,
    ) -> str:
        """Resolve and transcribe an audio reference.

        Args:
            audio_url: Local path, URL, file URI, or encoded audio reference.
            model: OpenAI transcription model name.
            language: Optional ISO-639-1 input language hint.
            prompt: Optional transcription context.

        Returns:
            Transcribed text.

        Raises:
            ValueError: If input or returned transcription is invalid.
            PermissionError: If the OAuth account cannot use transcription.
            RuntimeError: If authentication, quota, network, or API handling fails.
            TimeoutError: If the bounded operation exceeds its timeout.
        """
        if not str(audio_url or "").strip():
            raise ValueError("OAuth 转录音频不能为空。")
        if not str(model or "").strip():
            raise ValueError("OAuth 转录模型不能为空。")
        if self._closed:
            raise RuntimeError("OAuth transcription client is closed")
        task = asyncio.create_task(
            self._transcribe_audio(audio_url, str(model).strip(), language, prompt)
        )
        self._pending.add(task)
        try:
            return await asyncio.wait_for(
                task,
                timeout=self.timeout,
            )
        except asyncio.TimeoutError as exc:
            raise TimeoutError(
                f"OpenAI OAuth 音频转录超时：超过 {self.timeout:g} 秒。"
            ) from exc
        finally:
            self._pending.discard(task)

    async def close(self) -> None:
        """Reject new work and cancel all requests owned by this client."""
        self._closed = True
        tasks = list(self._pending)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _transcribe_audio(
        self,
        audio_url: str,
        model: str,
        language: str | None,
        prompt: str | None,
    ) -> str:
        await self.oauth_provider._ensure_fresh_oauth_token()
        async with BoundedOAuthAudioResolver(
            audio_url,
            max_bytes=self.max_audio_bytes,
            timeout=self.timeout,
            proxy=self.oauth_provider.provider_config.get("proxy") or None,
        ).as_wav_path() as audio:
            stat = await asyncio.to_thread(Path(audio.path).stat)
            if stat.st_size > self.max_audio_bytes:
                raise ValueError(
                    f"OAuth 转录音频超过文件大小上限 {self.max_audio_bytes} 字节。"
                )
            audio_bytes = await asyncio.to_thread(Path(audio.path).read_bytes)
            filename = Path(audio.path).name or "audio.wav"
            mime_type = audio.mime_type or "audio/wav"
            form = {"model": model}
            if language:
                form["language"] = str(language)
            if prompt:
                form["prompt"] = str(prompt)

            status_code, payload, attempted_version = await self._post_transcription(
                filename,
                mime_type,
                audio_bytes,
                form,
            )
            if status_code == 401:
                refreshed = await self.oauth_provider._refresh_after_auth_failure(
                    attempted_version
                )
                if refreshed:
                    status_code, payload, _ = await self._post_transcription(
                        filename,
                        mime_type,
                        audio_bytes,
                        form,
                    )

        if status_code == 401:
            raise RuntimeError("OpenAI OAuth 音频转录认证失败，请重新绑定账户。")
        if status_code == 403:
            raise PermissionError("当前 OAuth 账户无权使用 OpenAI 音频转录。")
        if status_code == 429:
            raise RuntimeError("OpenAI OAuth 音频转录配额不足或请求过于频繁。")
        if not 200 <= status_code < 300:
            raise RuntimeError(f"OpenAI OAuth 音频转录失败：HTTP {status_code}。")
        if not isinstance(payload, dict):
            raise ValueError("OpenAI OAuth 音频转录响应格式无效。")
        text = str(payload.get("text") or "").strip()
        if not text:
            raise ValueError("OpenAI OAuth 音频转录响应未包含文本。")
        return text

    async def _post_transcription(
        self,
        filename: str,
        mime_type: str,
        audio_bytes: bytes,
        form: dict[str, str],
    ) -> tuple[int, dict[str, Any] | None, int]:
        headers, attempted_version = (
            self.oauth_provider._build_backend_headers_with_version()
        )
        headers = {
            key: value
            for key, value in headers.items()
            if key.lower() not in {"content-type", "accept"}
        }
        headers["Accept"] = "application/json"
        try:
            async with httpx.AsyncClient(
                proxy=self.oauth_provider.provider_config.get("proxy") or None,
                timeout=self.timeout,
                follow_redirects=False,
            ) as client:
                response = await client.post(
                    OPENAI_TRANSCRIPTIONS_URL,
                    headers=headers,
                    data=form,
                    files={"file": (filename, audio_bytes, mime_type)},
                )
        except httpx.TimeoutException as exc:
            raise TimeoutError(
                f"OpenAI OAuth 音频转录超时：超过 {self.timeout:g} 秒。"
            ) from exc
        except httpx.RequestError as exc:
            raise RuntimeError("OpenAI OAuth 音频转录网络请求失败。") from exc

        payload: dict[str, Any] | None = None
        try:
            decoded = response.json()
            if isinstance(decoded, dict):
                payload = decoded
        except ValueError:
            pass
        return response.status_code, payload, attempted_version
