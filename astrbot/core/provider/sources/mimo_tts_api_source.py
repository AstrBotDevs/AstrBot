import asyncio
import base64
import uuid
from pathlib import Path

from ..entities import ProviderType
from ..provider import TTSProvider
from ..register import register_provider_adapter
from .mimo_api_common import (
    DEFAULT_MIMO_API_BASE,
    DEFAULT_MIMO_TTS_MODEL,
    DEFAULT_MIMO_TTS_SEED_TEXT,
    DEFAULT_MIMO_TTS_VOICE,
    MiMoAPIError,
    build_api_url,
    build_headers,
    cleanup_files,
    create_http_client,
    get_temp_dir,
    normalize_timeout,
    prepare_audio_input,
)


@register_provider_adapter(
    "mimo_tts_api",
    "MiMo TTS API",
    provider_type=ProviderType.TEXT_TO_SPEECH,
)
class ProviderMiMoTTSAPI(TTSProvider):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        super().__init__(provider_config, provider_settings)
        self.chosen_api_key = provider_config.get("api_key", "")
        self.api_base = provider_config.get("api_base", DEFAULT_MIMO_API_BASE)
        self.proxy = provider_config.get("proxy", "")
        self.timeout = normalize_timeout(provider_config.get("timeout", 20))
        self.voice = provider_config.get("mimo-tts-voice", DEFAULT_MIMO_TTS_VOICE)
        self.voiceclone_audio_source = provider_config.get(
            "mimo-tts-voiceclone-audio", ""
        ).strip()
        self.audio_format = provider_config.get("mimo-tts-format", "wav")
        self.style_prompt = provider_config.get("mimo-tts-style-prompt", "")
        self.dialect = provider_config.get("mimo-tts-dialect", "")
        self.seed_text = provider_config.get(
            "mimo-tts-seed-text", DEFAULT_MIMO_TTS_SEED_TEXT
        )
        self.set_model(provider_config.get("model", DEFAULT_MIMO_TTS_MODEL))
        self.client = create_http_client(self.timeout, self.proxy)
        # 音色复刻(voiceclone)参考音频转换结果缓存，避免每次合成都重新读取/转码同一份样本
        self._voiceclone_cache_source: str | None = None
        self._voiceclone_cache_data_url: str | None = None
        self._voiceclone_cleanup_paths: list[Path] = []
        # TTS provider 实例在管线中是长期共享的，可能被并发请求同时调用；
        # 用锁序列化"检查缓存 -> 转换 -> 写入缓存"这一过程，避免重复转换和临时文件泄漏。
        self._voiceclone_lock = asyncio.Lock()

    def _build_user_prompt(self) -> str | None:
        seed_text = self.seed_text.strip()
        return seed_text or None

    def _build_style_prefix(self) -> str:
        style_parts: list[str] = []

        if self.style_prompt.strip():
            style_parts.append(self.style_prompt.strip())
        if self.dialect.strip():
            style_parts.append(self.dialect.strip())

        style_content = " ".join(style_parts).strip()
        if not style_content:
            return ""

        # MiMo recommends using only the singing style tag at the very beginning.
        if "唱歌" in style_content:
            return "<style>唱歌</style>"

        return f"<style>{style_content}</style>"

    def _build_assistant_content(self, text: str) -> str:
        return f"{self._build_style_prefix()}{text}"

    def _is_voiceclone_model(self) -> bool:
        return "voiceclone" in self.model_name

    async def _resolve_voiceclone_voice(self) -> str:
        """将配置的参考音频样本转换为 voiceclone 所需的 data URL。

        结果会按音频来源缓存，避免每次合成请求都重新读取/转码同一份样本。
        加锁是为了在并发请求下避免重复转换、避免临时文件泄漏或被错误清理。
        """
        if not self.voiceclone_audio_source:
            raise MiMoAPIError(
                "MiMo TTS voiceclone model (mimo-v2.5-tts-voiceclone) requires a "
                "reference audio sample. Please set 'mimo-tts-voiceclone-audio' to "
                "a local path, URL, or base64/data URI."
            )

        async with self._voiceclone_lock:
            if (
                self._voiceclone_cache_data_url is not None
                and self._voiceclone_cache_source == self.voiceclone_audio_source
            ):
                return self._voiceclone_cache_data_url

            try:
                data_url, cleanup_paths = await prepare_audio_input(
                    self.voiceclone_audio_source,
                    # MiMo voiceclone 接受 mp3 或 wav；保留原始 mp3 而不强制转 wav，
                    # 可避免未压缩 PCM 带来的体积膨胀（更容易撞到官方 10 MB 上限）。
                    # 其他格式（ogg/flac/silk 等）仍会兜底转换为 wav。
                    target_format=None,
                    preserve_mp3=True,
                )
            except Exception as exc:
                raise MiMoAPIError(
                    f"Failed to prepare MiMo TTS voiceclone reference audio "
                    f"'{self.voiceclone_audio_source}': {exc}"
                ) from exc

            # 旧缓存的临时文件不再需要，先清理掉再写入新结果
            cleanup_files(self._voiceclone_cleanup_paths)
            self._voiceclone_cleanup_paths = cleanup_paths
            self._voiceclone_cache_source = self.voiceclone_audio_source
            self._voiceclone_cache_data_url = data_url
            return data_url

    def _build_payload(self, text: str, voice_value: str | None = None) -> dict:
        messages: list[dict[str, str]] = []

        user_prompt = self._build_user_prompt()
        if user_prompt:
            messages.append(
                {
                    "role": "user",
                    "content": user_prompt,
                }
            )

        messages.append(
            {
                "role": "assistant",
                "content": self._build_assistant_content(text),
            }
        )

        audio_params = {"format": self.audio_format}
        # voice design 模型不支持 audio.voice 参数
        if "voicedesign" not in self.model_name:
            audio_params["voice"] = (
                voice_value if voice_value is not None else self.voice
            )

        return {
            "model": self.model_name,
            "messages": messages,
            "audio": audio_params,
        }

    async def get_audio(self, text: str) -> str:
        voice_value = None
        if self._is_voiceclone_model():
            voice_value = await self._resolve_voiceclone_voice()

        response = await self.client.post(
            build_api_url(self.api_base),
            headers=build_headers(self.chosen_api_key),
            json=self._build_payload(text, voice_value),
        )

        try:
            response.raise_for_status()
        except Exception as exc:
            error_text = response.text[:1024]
            raise MiMoAPIError(
                f"MiMo TTS API request failed: HTTP {response.status_code}, response: {error_text}"
            ) from exc

        data = response.json()
        choices = data.get("choices") or []
        first_choice = choices[0] if choices else {}
        message = first_choice.get("message", {})
        audio_data = message.get("audio", {}).get("data")
        if not audio_data:
            raise MiMoAPIError(f"MiMo TTS API returned no audio payload: {data}")

        output_path = (
            get_temp_dir() / f"mimo_tts_api_{uuid.uuid4()}.{self.audio_format}"
        )
        output_path.write_bytes(base64.b64decode(audio_data))
        return str(output_path)

    async def terminate(self):
        cleanup_files(self._voiceclone_cleanup_paths)
        self._voiceclone_cleanup_paths = []
        if self.client:
            await self.client.aclose()
