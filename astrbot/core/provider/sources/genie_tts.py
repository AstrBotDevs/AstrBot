import asyncio
import os
import uuid

from astrbot.core import logger
from astrbot.core.provider.entities import ProviderType
from astrbot.core.provider.provider import TTSProvider
from astrbot.core.provider.register import register_provider_adapter
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

try:
    import genie_tts as genie  # type: ignore
except ImportError:
    genie = None


@register_provider_adapter(
    "genie_tts",
    "Genie TTS",
    provider_type=ProviderType.TEXT_TO_SPEECH,
)
class GenieTTSProvider(TTSProvider):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        super().__init__(provider_config, provider_settings)
        if not genie:
            raise ImportError("Please install genie_tts first.")

        self.character_name = provider_config.get("genie_character_name", "mika")
        language = provider_config.get("genie_language", "Japanese")
        model_dir = provider_config.get("genie_onnx_model_dir", "")
        refer_audio_path = provider_config.get("genie_refer_audio_path", "")
        refer_text = provider_config.get("genie_refer_text", "")

        try:
            genie.load_character(
                character_name=self.character_name,
                language=language,
                onnx_model_dir=model_dir,
            )
            genie.set_reference_audio(
                character_name=self.character_name,
                audio_path=refer_audio_path,
                audio_text=refer_text,
                language=language,
            )
        except Exception as e:
            raise RuntimeError(f"Failed to load character {self.character_name}: {e}")

    def support_stream(self) -> bool:
        return True

    async def get_audio(self, text: str) -> str:
        temp_dir = os.path.join(get_astrbot_data_path(), "temp")
        os.makedirs(temp_dir, exist_ok=True)
        filename = f"genie_tts_{uuid.uuid4()}.wav"
        path = os.path.join(temp_dir, filename)

        loop = asyncio.get_event_loop()

        def _generate(save_path: str):
            assert genie is not None
            genie.tts(
                character_name=self.character_name,
                text=text,
                save_path=save_path,
            )

        try:
            await loop.run_in_executor(None, _generate, path)

            if os.path.exists(path):
                return path

            raise RuntimeError("Genie TTS did not save to file.")

        except Exception as e:
            raise RuntimeError(f"Genie TTS generation failed: {e}")

    async def get_audio_stream(
        self,
        text_queue: asyncio.Queue[str | None],
        audio_queue: "asyncio.Queue[bytes | tuple[str, bytes] | None]",
    ) -> None:
        loop = asyncio.get_event_loop()

        while True:
            text = await text_queue.get()
            if text is None:
                await audio_queue.put(None)
                break

            try:
                temp_dir = os.path.join(get_astrbot_data_path(), "temp")
                os.makedirs(temp_dir, exist_ok=True)
                filename = f"genie_tts_{uuid.uuid4()}.wav"
                path = os.path.join(temp_dir, filename)

                def _generate(save_path: str, t: str):
                    assert genie is not None
                    genie.tts(
                        character_name=self.character_name,
                        text=t,
                        save_path=save_path,
                    )

                await loop.run_in_executor(None, _generate, path, text)

                if os.path.exists(path):
                    with open(path, "rb") as f:
                        audio_data = f.read()

                    # Put (text, bytes) into queue so frontend can display text
                    await audio_queue.put((text, audio_data))

                    # Clean up
                    try:
                        os.remove(path)
                    except OSError:
                        pass
                else:
                    logger.error(f"Genie TTS failed to generate audio for: {text}")

            except Exception as e:
                logger.error(f"Genie TTS stream error: {e}")
