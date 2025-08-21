import os
import uuid
import re
import ormsgpack
from pydantic import BaseModel, conint
from httpx import AsyncClient
from typing import Annotated, Literal
from ..provider import TTSProvider
from ..entities import ProviderType
from ..register import register_provider_adapter
from astrbot.core.utils.astrbot_path import get_astrbot_data_path


class ServeReferenceAudio(BaseModel):
    audio: bytes
    text: str


class ServeTTSRequest(BaseModel):
    text: str
    chunk_length: Annotated[int, conint(ge=100, le=300, strict=True)] = 200
    # 音频格式
    format: Literal["wav", "pcm", "mp3"] = "mp3"
    mp3_bitrate: Literal[64, 128, 192] = 128
    # 参考音频
    references: list[ServeReferenceAudio] = []
    # 参考模型 ID
    # 例如 https://fish.audio/m/626bb6d3f3364c9cbc3aa6a67300a664/
    # 其中reference_id为 626bb6d3f3364c9cbc3aa6a67300a664
    reference_id: str | None = None
    # 对中英文文本进行标准化，这可以提高数字的稳定性
    normalize: bool = True
    # 平衡模式将延迟减少到300毫秒，但可能会降低稳定性
    latency: Literal["normal", "balanced"] = "normal"


@register_provider_adapter(
    "fishaudio_tts_api", "FishAudio TTS API", provider_type=ProviderType.TEXT_TO_SPEECH
)
class ProviderFishAudioTTSAPI(TTSProvider):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        super().__init__(provider_config, provider_settings)
        self.chosen_api_key: str = provider_config.get("api_key", "")
        self.reference_id: str = provider_config.get("fishaudio-tts-reference-id", "")
        self.character: str = provider_config.get("fishaudio-tts-character", "可莉")
        self.api_base: str = provider_config.get(
            "api_base", "https://api.fish-audio.cn/v1"
        )
        self.headers = {
            "Authorization": f"Bearer {self.chosen_api_key}",
        }
        self.set_model(provider_config.get("model", None))

    async def _get_reference_id_by_character(self, character: str) -> str:
        """
        获取角色的reference_id

        Args:
            character: 角色名称

        Returns:
            reference_id: 角色的reference_id

        exception:
            APIException: 获取语音角色列表为空
        """
        sort_options = ["score", "task_count", "created_at"]
        async with AsyncClient(base_url=self.api_base.replace("/v1", "")) as client:
            for sort_by in sort_options:
                params = {"title": character, "sort_by": sort_by}
                response = await client.get(
                    "/model", params=params, headers=self.headers
                )
                resp_data = response.json()
                if resp_data["total"] == 0:
                    continue
                for item in resp_data["items"]:
                    if character in item["title"]:
                        return item["_id"]
            return None

    def _validate_reference_id(self, reference_id: str) -> bool:
        """
        验证reference_id格式是否有效

        Args:
            reference_id: 参考模型ID

        Returns:
            bool: ID是否有效
        """
        if not reference_id or not reference_id.strip():
            return False

        # FishAudio的reference_id通常是32位十六进制字符串
        # 例如: 626bb6d3f3364c9cbc3aa6a67300a664
        pattern = r'^[a-fA-F0-9]{32}$'
        return bool(re.match(pattern, reference_id.strip()))

    async def _generate_request(self, text: str) -> dict:
        # 向前兼容逻辑：优先使用reference_id，如果没有则使用角色名称查询
        if self.reference_id and self.reference_id.strip():
            # 验证reference_id格式
            if not self._validate_reference_id(self.reference_id):
                raise ValueError(
                    f"无效的FishAudio参考模型ID: '{self.reference_id}'. "
                    f"请确保ID是32位十六进制字符串（例如: 626bb6d3f3364c9cbc3aa6a67300a664）。"
                    f"您可以从 https://fish.audio/zh-CN/discovery 获取有效的模型ID。"
                )
            reference_id = self.reference_id.strip()
        else:
            # 回退到原来的角色名称查询逻辑
            reference_id = await self._get_reference_id_by_character(self.character)

        return ServeTTSRequest(
            text=text,
            format="wav",
            reference_id=reference_id,
        )

    async def get_audio(self, text: str) -> str:
        temp_dir = os.path.join(get_astrbot_data_path(), "temp")
        path = os.path.join(temp_dir, f"fishaudio_tts_api_{uuid.uuid4()}.wav")
        self.headers["content-type"] = "application/msgpack"
        request = await self._generate_request(text)
        async with AsyncClient(base_url=self.api_base).stream(
            "POST",
            "/tts",
            headers=self.headers,
            content=ormsgpack.packb(request, option=ormsgpack.OPT_SERIALIZE_PYDANTIC),
        ) as response:
            if response.headers["content-type"] == "audio/wav":
                with open(path, "wb") as f:
                    async for chunk in response.aiter_bytes():
                        f.write(chunk)
                return path
            text = await response.aread()
            raise Exception(f"Fish Audio API请求失败: {text}")
