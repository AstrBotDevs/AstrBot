"""Show failed speech and knowledge-base model calls in ChatUI.

Speech-to-text, text-to-speech and knowledge-base retrieval fall back quietly
when their model fails: the voice message is dropped, the reply is sent as
text, or the answer is given without the retrieved knowledge. Other platforms
keep that behavior; ChatUI also shows a card, so the user knows which model to
fix instead of finding only a log line.
"""

from astrbot.core import logger
from astrbot.core.message.components import Json
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.astr_message_event import AstrMessageEvent

AUXILIARY_MODEL_ERROR_CODE = "auxiliaryModelFailed"


async def notify_auxiliary_model_failure(
    event: AstrMessageEvent, model: str, detail: str
) -> None:
    """Show a ChatUI card for a failed speech or knowledge-base model call.

    The reply goes on without the model, so a failure to show the card is only
    logged.

    Args:
        event: Message event whose reply the failure affects.
        model: Which model failed, e.g. "Speech-to-text (whisper)".
        detail: The provider's error, shown under the card's details.
    """
    if event.get_platform_name() != "webchat":
        return
    try:
        await event.send(
            MessageChain(
                type="chatui_error",
                chain=[
                    Json(
                        {
                            "code": AUXILIARY_MODEL_ERROR_CODE,
                            "message": f"{model}: {detail}",
                        }
                    )
                ],
            )
        )
    except Exception as exc:
        logger.warning(f"Failed to show the {model} failure in ChatUI: {exc}")
