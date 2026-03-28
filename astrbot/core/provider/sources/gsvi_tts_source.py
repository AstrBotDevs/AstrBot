import os
import urllib.parse
import uuid

import aiohttp

from astrbot import logger
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path

from ..entities import ProviderType
from ..provider import TTSProvider
from ..register import register_provider_adapter


@register_provider_adapter(
    "gsvi_tts_api",
    "GSVI TTS API",
    provider_type=ProviderType.TEXT_TO_SPEECH,
)
class ProviderGSVITTS(TTSProvider):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        super().__init__(provider_config, provider_settings)
        self.api_base = provider_config.get("api_base", "http://127.0.0.1:5000")
        self.api_base = self.api_base.removesuffix("/")
        self.character = provider_config.get("character")
        self.emotion = provider_config.get("emotion")
        self.version = provider_config.get("version")
        self.api_key = provider_config.get("api_key", "")
        self.timeout = int(provider_config.get("timeout", 20))
        self.media_type = provider_config.get("media_type", "wav")
        self.text_lang = provider_config.get("text_lang")

    async def get_audio(self, text: str) -> str:
        if not text.strip():
            raise ValueError("GSVI TTS text cannot be empty")

        temp_dir = get_astrbot_temp_path()
        os.makedirs(temp_dir, exist_ok=True)
        path = os.path.join(temp_dir, f"gsvi_tts_{uuid.uuid4()}.wav")
        timeout = aiohttp.ClientTimeout(total=self.timeout)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            if not self.character:
                logger.warning("[GSVI TTS] character is not configured; falling back to legacy /tts")
                await self._download_legacy_tts(session, text, path)
                return path

            infer_config = await self._resolve_infer_config(session)
            payload = self._build_infer_payload(text, infer_config)
            audio_url = await self._request_infer_audio(session, payload)
            await self._download_binary(session, audio_url, path)

        return path

    def _auth_headers(self) -> dict[str, str]:
        if self.api_key:
            return {"Authorization": f"Bearer {self.api_key}"}
        if "acgnai.top" in self.api_base:
            return {"Authorization": "Bearer guest"}
        return {}

    async def _get_json(self, session: aiohttp.ClientSession, url: str) -> dict:
        async with session.get(url, headers=self._auth_headers()) as response:
            if response.status != 200:
                error_text = await response.text()
                raise Exception(
                    f"GSVI TTS API request failed: GET {url} -> {response.status}, error: {error_text}",
                )
            return await response.json(content_type=None)

    async def _post_json(
        self,
        session: aiohttp.ClientSession,
        url: str,
        payload: dict,
    ) -> dict:
        async with session.post(
            url,
            headers={
                "Content-Type": "application/json",
                **self._auth_headers(),
            },
            json=payload,
        ) as response:
            if response.status != 200:
                error_text = await response.text()
                raise Exception(
                    f"GSVI TTS API request failed: POST {url} -> {response.status}, error: {error_text}",
                )
            return await response.json(content_type=None)

    async def _resolve_infer_config(self, session: aiohttp.ClientSession) -> dict[str, str]:
        versions = []
        if self.version:
            versions.append(self.version)

        version_data = await self._get_json(session, f"{self.api_base}/version")
        for version in version_data.get("support_versions", []):
            if version not in versions:
                versions.append(version)

        for version in versions:
            model_data = await self._get_json(session, f"{self.api_base}/models/{version}")
            language_map = (model_data.get("models") or {}).get(self.character) or {}
            if not language_map:
                continue

            prompt_text_lang = self._select_prompt_text_lang(language_map)
            emotions = language_map.get(prompt_text_lang) or []
            emotion = self._select_emotion(emotions)

            return {
                "version": version,
                "prompt_text_lang": prompt_text_lang,
                "emotion": emotion,
            }

        raise Exception(
            f"GSVI TTS model not found in remote catalog: {self.character}",
        )

    def _select_prompt_text_lang(self, language_map: dict[str, list[str]]) -> str:
        if not language_map:
            raise Exception("GSVI TTS model has no prompt_text_lang options")

        non_empty_languages = [lang for lang, emotions in language_map.items() if emotions]
        if non_empty_languages:
            return non_empty_languages[0]

        return next(iter(language_map))

    def _normalize_emotion(self, emotion: str | None) -> str:
        if not emotion:
            return "默认"

        normalized = emotion.strip()
        english_aliases = {
            "default": "默认",
            "neutral": "中立",
            "happy": "开心",
            "sad": "难过",
            "angry": "生气",
            "fear": "恐惧",
            "surprise": "吃惊",
            "surprised": "吃惊",
            "disgust": "厌恶",
            "other": "其他",
            "random": "随机",
        }
        return english_aliases.get(normalized.lower(), normalized)

    def _select_emotion(self, emotions: list[str]) -> str:
        requested = self._normalize_emotion(self.emotion)
        if requested in emotions:
            return requested
        if "默认" in emotions:
            return "默认"
        if emotions:
            return emotions[0]
        return requested

    def _resolve_text_lang(self, prompt_text_lang: str) -> str:
        if self.text_lang:
            return self.text_lang

        mapping = {
            "中文": "中文",
            "zh": "中文",
            "zh_cn": "中文",
            "英语": "英语",
            "en": "英语",
            "日语": "日语",
            "ja": "日语",
            "jp": "日语",
            "粤语": "粤语",
            "yue": "粤语",
            "韩语": "韩语",
            "ko": "韩语",
        }
        return mapping.get(prompt_text_lang.lower(), prompt_text_lang)

    def _build_infer_payload(self, text: str, infer_config: dict[str, str]) -> dict:
        return {
            "version": infer_config["version"],
            "model_name": self.character,
            "prompt_text_lang": infer_config["prompt_text_lang"],
            "emotion": infer_config["emotion"],
            "text": text,
            "text_lang": self._resolve_text_lang(infer_config["prompt_text_lang"]),
            "top_k": 10,
            "top_p": 1,
            "temperature": 1,
            "text_split_method": "凑四句一切",
            "batch_size": 1,
            "batch_threshold": 0.75,
            "split_bucket": True,
            "speed_facter": 1,
            "fragment_interval": 0.3,
            "media_type": self.media_type,
            "parallel_infer": True,
            "repetition_penalty": 1.35,
            "seed": -1,
            "sample_steps": 16,
            "if_sr": False,
        }

    async def _request_infer_audio(
        self,
        session: aiohttp.ClientSession,
        payload: dict,
    ) -> str:
        data = await self._post_json(session, f"{self.api_base}/infer_single", payload)
        audio_url = data.get("audio_url", "")
        if not audio_url:
            raise Exception(data.get("msg", "GSVI TTS infer_single did not return audio_url"))
        return audio_url

    async def _download_binary(
        self,
        session: aiohttp.ClientSession,
        url: str,
        path: str,
    ) -> None:
        async with session.get(url) as response:
            if response.status != 200:
                error_text = await response.text()
                raise Exception(
                    f"Failed to download synthesized audio: GET {url} -> {response.status}, error: {error_text}",
                )
            with open(path, "wb") as f:
                f.write(await response.read())

    async def _download_legacy_tts(
        self,
        session: aiohttp.ClientSession,
        text: str,
        path: str,
    ) -> None:
        encoded_text = urllib.parse.quote(str(text))
        url = f"{self.api_base}/tts?text={encoded_text}"

        async with session.get(url, headers=self._auth_headers()) as response:
            if response.status == 200:
                with open(path, "wb") as f:
                    f.write(await response.read())
            else:
                error_text = await response.text()
                raise Exception(
                    f"GSVI TTS API legacy /tts request failed, status: {response.status}, error: {error_text}",
                )
