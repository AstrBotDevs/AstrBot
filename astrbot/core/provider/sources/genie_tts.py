import asyncio
import os
import threading
import uuid
from contextlib import suppress

from astrbot.core import logger
from astrbot.core.agent.stop_policy import event_requests_agent_stop
from astrbot.core.provider.entities import ProviderType
from astrbot.core.provider.provider import TTSProvider
from astrbot.core.provider.register import register_provider_adapter
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path

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
        temp_dir = get_astrbot_temp_path()
        os.makedirs(temp_dir, exist_ok=True)
        filename = f"genie_tts_{uuid.uuid4()}.wav"
        path = os.path.join(temp_dir, filename)

        loop = asyncio.get_running_loop()
        cleanup_requested = threading.Event()

        def _generate(save_path: str) -> None:
            assert genie is not None
            try:
                genie.tts(
                    character_name=self.character_name,
                    text=text,
                    save_path=save_path,
                )
            finally:
                if cleanup_requested.is_set():
                    with suppress(OSError):
                        os.remove(save_path)

        try:
            generation_future = loop.run_in_executor(None, _generate, path)
            await asyncio.shield(generation_future)

            if os.path.exists(path):
                return path

            raise RuntimeError("Genie TTS did not save to file.")

        except asyncio.CancelledError:
            cleanup_requested.set()
            generation_future.add_done_callback(
                lambda future: future.exception() if not future.cancelled() else None
            )
            with suppress(OSError):
                os.remove(path)
            raise
        except Exception as e:
            with suppress(OSError):
                os.remove(path)
            raise RuntimeError(f"Genie TTS generation failed: {e}")

    async def get_audio_stream(
        self,
        text_queue: asyncio.Queue[str | None],
        audio_queue: "asyncio.Queue[bytes | tuple[str, bytes] | None]",
    ) -> None:
        loop = asyncio.get_running_loop()
        astr_event = getattr(text_queue, "astr_event", None)

        while True:
            text = await text_queue.get()
            if text is None:
                await audio_queue.put(None)
                break

            try:
                temp_dir = get_astrbot_temp_path()
                os.makedirs(temp_dir, exist_ok=True)
                filename = f"genie_tts_{uuid.uuid4()}.wav"
                path = os.path.join(temp_dir, filename)
                cleanup_requested = threading.Event()

                def _generate(save_path: str, t: str) -> None:
                    assert genie is not None
                    try:
                        genie.tts(
                            character_name=self.character_name,
                            text=t,
                            save_path=save_path,
                        )
                    finally:
                        if cleanup_requested.is_set():
                            with suppress(OSError):
                                os.remove(save_path)

                if astr_event is not None:
                    astr_event.track_temporary_local_file(path)
                generation_future = loop.run_in_executor(None, _generate, path, text)
                try:
                    await asyncio.shield(generation_future)
                except asyncio.CancelledError:
                    # The worker may outlive this coroutine, so let it remove any
                    # file created after cancellation without delaying shutdown.
                    cleanup_requested.set()
                    generation_future.add_done_callback(
                        lambda future: (
                            future.exception() if not future.cancelled() else None
                        )
                    )
                    with suppress(OSError):
                        os.remove(path)
                    raise

                if os.path.exists(path):
                    try:
                        if event_requests_agent_stop(astr_event):
                            continue
                        with open(path, "rb") as f:
                            audio_data = f.read()
                        if not event_requests_agent_stop(astr_event):
                            # Put (text, bytes) into queue so frontend can display text
                            await audio_queue.put((text, audio_data))
                    finally:
                        # The event cleanup remains a fallback if immediate removal fails.
                        try:
                            os.remove(path)
                        except OSError:
                            pass
                else:
                    logger.error(f"Genie TTS failed to generate audio for: {text}")

            except Exception as e:
                logger.error(f"Genie TTS stream error: {e}")
