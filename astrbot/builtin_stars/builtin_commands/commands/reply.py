from astrbot.api.event import MessageEventResult


def _plain_text_result(text: str):
    return MessageEventResult().message(text).use_t2i(False)


def reply_text(event, text: str) -> None:
    """Send a plain-text command reply and stop event propagation."""
    event.set_result(_plain_text_result(text).stop_event())


def reply_image_url(event, url: str) -> None:
    """Send a remote image command reply and stop event propagation."""
    event.set_result(MessageEventResult().url_image(url).use_t2i(False).stop_event())


def reply_image_file(event, path: str) -> None:
    """Send a local image command reply and stop event propagation."""
    event.set_result(MessageEventResult().file_image(path).use_t2i(False).stop_event())


async def reply_i18n(context, event, message_key: str, **kwargs) -> None:
    """Translate a command reply, send it, and stop event propagation."""
    reply_text(event, await context.i18n.t(event, message_key, **kwargs))


async def send_text(event, text: str) -> None:
    """Send a progress message without stopping event propagation."""
    await event.send(_plain_text_result(text))


async def send_i18n(context, event, message_key: str, **kwargs) -> None:
    """Translate and send a progress message without stopping event propagation."""
    await send_text(event, await context.i18n.t(event, message_key, **kwargs))
