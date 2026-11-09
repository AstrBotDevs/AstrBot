"""Portable output values, independent of model messages and IM protocols."""

from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class OutputValue(BaseModel):
    """A serializable value detached from mutable execution objects."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class PathMedia(OutputValue):
    kind: Literal["path"] = "path"
    path: str
    mime_type: str | None = None


class URLMedia(OutputValue):
    kind: Literal["url"] = "url"
    url: str
    mime_type: str | None = None


class InlineMedia(OutputValue):
    kind: Literal["inline"] = "inline"
    data: str
    mime_type: str


MediaReference: TypeAlias = Annotated[
    PathMedia | URLMedia | InlineMedia, Field(discriminator="kind")
]


class PlainOutput(OutputValue):
    type: Literal["plain"] = "plain"
    text: str


class ReasoningOutput(OutputValue):
    type: Literal["reasoning"] = "reasoning"
    text: str | None = None
    redacted: bool = False


class ImageOutput(OutputValue):
    type: Literal["image"] = "image"
    source: MediaReference


class FileOutput(OutputValue):
    type: Literal["file"] = "file"
    source: MediaReference
    name: str | None = None


class AudioOutput(OutputValue):
    type: Literal["audio"] = "audio"
    source: MediaReference


class VideoOutput(OutputValue):
    type: Literal["video"] = "video"
    source: MediaReference


class ExtensionOutput(OutputValue):
    type: Literal["extension"] = "extension"
    namespace: str
    name: str
    value: JsonValue


OutputComponent: TypeAlias = Annotated[
    PlainOutput
    | ReasoningOutput
    | ImageOutput
    | FileOutput
    | AudioOutput
    | VideoOutput
    | ExtensionOutput,
    Field(discriminator="type"),
]
