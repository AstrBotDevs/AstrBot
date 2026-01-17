import asyncio
import os
import uuid

from astrbot.core.provider.entities import ProviderType
from astrbot.core.provider.provider import TTSProvider
from astrbot.core.provider.register import register_provider_adapter
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

# genie_data_dir = os.path.join(get_astrbot_data_path(), "genie_tts_data")
# os.makedirs(genie_data_dir, exist_ok=True)
# os.environ["GENIE_DATA_DIR"] = genie_data_dir

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

        self.character_name = provider_config.get("character_name", "mika")

        # Automatically downloads required files on first run
        # This is done synchronously as per the library usage, might block on first run.
        try:
            genie.load_predefined_character(self.character_name)
        except Exception as e:
            raise RuntimeError(f"Failed to load character {self.character_name}: {e}")

    async def get_audio(self, text: str) -> str:
        temp_dir = os.path.join(get_astrbot_data_path(), "temp")
        os.makedirs(temp_dir, exist_ok=True)
        filename = f"genie_tts_{uuid.uuid4()}.wav"
        path = os.path.join(temp_dir, filename)

        loop = asyncio.get_event_loop()

        def _generate(save_path: str):
            assert genie is not None
            # Assuming it returns bytes:
            genie.tts(
                character_name=self.character_name,
                text=text,
                save_path=save_path,
            )

        try:
            await loop.run_in_executor(None, _generate, path)

            if os.path.exists(path):
                return path
            raise RuntimeError("Genie TTS did not return audio bytes or save to file.")

        except Exception as e:
            raise RuntimeError(f"Genie TTS generation failed: {e}")
