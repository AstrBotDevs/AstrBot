"""Translate portable runtime content at the AstrBot message boundary."""

import json
from collections.abc import Sequence
from urllib.parse import urlsplit

from astrbot.core.agent.output import (
    AudioOutput,
    ExtensionOutput,
    FileOutput,
    ImageOutput,
    InlineMedia,
    MediaReference,
    OutputComponent,
    PathMedia,
    PlainOutput,
    ReasoningOutput,
    URLMedia,
    VideoOutput,
)
from astrbot.core.message import components as Comp
from astrbot.core.message.message_event_result import MessageChain


def content_from_chain(chain: MessageChain | None) -> tuple[OutputComponent, ...]:
    """Snapshot platform content without I/O or retaining mutable components.

    Args:
        chain: Provider or plugin output at the native boundary.

    Returns:
        Portable content preserving component order.

    Raises:
        ValueError: If media has no source or content cannot be serialized.
    """
    result: list[OutputComponent] = []
    for component in chain.chain if chain else []:
        if isinstance(component, Comp.Plain):
            result.append(
                ReasoningOutput(text=component.text)
                if chain and chain.type == "reasoning"
                else PlainOutput(text=component.text)
            )
        elif isinstance(component, (Comp.Image, Comp.File, Comp.Record, Comp.Video)):
            raw = (
                (component.file_ or component.url)
                if isinstance(component, Comp.File)
                else (component.file or component.url or component.path)
            )
            if not raw:
                raise ValueError("Output media has no source")
            source: MediaReference
            if raw.startswith("base64://"):
                mime = "application/octet-stream"
                source = InlineMedia(data=raw.removeprefix("base64://"), mime_type=mime)
            elif raw.startswith("data:"):
                header, data = raw.split(",", 1)
                if not header.endswith(";base64"):
                    raise ValueError("Inline output media requires base64 data")
                source = InlineMedia(data=data, mime_type=header[5:-7])
            elif urlsplit(raw).scheme in ("http", "https"):
                source = URLMedia(url=raw)
            else:
                source = PathMedia(path=raw)
            if isinstance(component, Comp.Image):
                result.append(ImageOutput(source=source))
            elif isinstance(component, Comp.File):
                result.append(FileOutput(source=source, name=component.name or None))
            elif isinstance(component, Comp.Record):
                result.append(AudioOutput(source=source))
            else:
                result.append(VideoOutput(source=source))
        else:
            result.append(
                ExtensionOutput(
                    namespace="astrbot.platform",
                    name=component.type.value,
                    value=json.loads(component.json()),
                )
            )
    return tuple(result)


def chain_from_content(content: Sequence[OutputComponent]) -> MessageChain:
    """Restore runtime output for the existing message pipeline.

    Args:
        content: Standard output including explicit platform extensions.

    Returns:
        A newly allocated platform message chain.

    Raises:
        ValueError: If an extension is unknown or malformed.
    """

    def restore(data: dict):
        kind = str(data.get("type", "")).lower()
        cls = Comp.ComponentTypes.get(kind)
        if cls is None:
            raise ValueError(f"Unsupported platform component: {kind}")
        values = {key: value for key, value in data.items() if key != "type"}
        for key in ("content", "chain", "nodes"):
            if isinstance(values.get(key), list):
                values[key] = [
                    restore(item) if isinstance(item, dict) and "type" in item else item
                    for item in values[key]
                ]
        return cls(**values)

    components: list[Comp.BaseMessageComponent] = []
    for part in content:
        if isinstance(part, (PlainOutput, ReasoningOutput)):
            if part.text:
                components.append(Comp.Plain(part.text))
        elif isinstance(part, ExtensionOutput):
            if part.namespace != "astrbot.platform" or not isinstance(part.value, dict):
                raise ValueError(
                    f"Unsupported output extension: {part.namespace}/{part.name}"
                )
            components.append(restore(part.value))
        else:
            source = part.source
            raw = (
                source.path
                if isinstance(source, PathMedia)
                else source.url
                if isinstance(source, URLMedia)
                else f"base64://{source.data}"
            )
            if isinstance(part, ImageOutput):
                components.append(Comp.Image(file=raw))
            elif isinstance(part, AudioOutput):
                components.append(Comp.Record(file=raw))
            elif isinstance(part, VideoOutput):
                components.append(Comp.Video(file=raw))
            else:
                components.append(
                    Comp.File(
                        name=part.name or "file",
                        file=raw if not isinstance(source, URLMedia) else "",
                        url=raw if isinstance(source, URLMedia) else "",
                    )
                )
    return MessageChain(chain=components)
