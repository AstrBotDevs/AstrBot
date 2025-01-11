import uuid
import os
import io
from openai import AsyncOpenAI, NOT_GIVEN
from ..provider import STTProvider
from ..entites import ProviderType
from astrbot.core.utils.io import download_file
from ..register import register_provider_adapter
from astrbot.core import logger

@register_provider_adapter("openai_whisper_api", "OpenAI Whisper API", provider_type=ProviderType.SPEECH_TO_TEXT)
class ProviderOpenAIWhisperAPI(STTProvider):
    def __init__(
        self, 
        provider_config: dict, 
        provider_settings: dict,
    ) -> None:
        super().__init__(provider_config, provider_settings)
        self.chosen_api_key = provider_config.get("api_key", "")

        self.client = AsyncOpenAI(
            api_key=self.chosen_api_key,
            base_url=provider_config.get("api_base", None),
            timeout=provider_config.get("timeout", NOT_GIVEN),
        )
        
        self.set_model(provider_config.get("model", None))
        
    async def _convert_audio(self, path: str) -> str:
        from pyffmpeg import FFmpeg
        filename = str(uuid.uuid4()) + '.mp3'
        ff = FFmpeg()
        output_path = ff.convert(path, os.path.join('data/temp', filename))
        return output_path
    
    async def _pcm_to_wav(self, input_io: io.BytesIO, output_path: str) -> str:
        import wave
        
        with wave.open(output_path, 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(24000)
            wav.writeframes(input_io.read())
            
        return output_path

    async def _convert_silk(self, path: str) -> str:
        import pysilk
        filename = str(uuid.uuid4()) + '.wav'
        output_path = os.path.join('data/temp', filename)
        with open(path, "rb") as f:
            input_data = f.read()
            if input_data.startswith(b'\x02'):
                # tencent 我爱你
                input_data = input_data[1:]
            input_io = io.BytesIO(input_data)
            output_io = io.BytesIO()
            pysilk.decode(input_io, output_io, 24000)
            output_io.seek(0)
            await self._pcm_to_wav(output_io, output_path)
        
        return output_path
    
    async def _is_silk_file(self, file_path):
        silk_header = b"SILK"
        with open(file_path, "rb") as f:
            file_header = f.read(8)

        if silk_header in file_header:
            return True
        else:
            return False

    async def get_text(self, audio_url: str) -> str:
        '''only supports mp3, mp4, mpeg, m4a, wav, webm'''
        if audio_url.startswith("http"):
            name = str(uuid.uuid4())
            path = os.path.join("data/temp", name)
            audio_url = await download_file(audio_url, path)
        
        if not os.path.exists(audio_url):
            raise FileNotFoundError(f"文件不存在: {audio_url}")
        
        if audio_url.endswith(".amr") or audio_url.endswith(".silk"):
            is_silk = await self._is_silk_file(audio_url)
            if is_silk:
                logger.info("Converting silk file to wav ...")
                audio_url = await self._convert_silk(audio_url)

        
        result = await self.client.audio.transcriptions.create(
            model=self.model_name,
            file=open(audio_url, "rb"),
        )
        return result.text