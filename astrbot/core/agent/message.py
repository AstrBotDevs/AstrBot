# Partially inspired by MoonshotAI/kosong

from typing import Literal

from pydantic import BaseModel


class ContentPart(BaseModel):
    type: str
    ...


class TextPart(ContentPart):
    """
    >>> TextPart(text="Hello, world!").model_dump()
    {'type': 'text', 'text': 'Hello, world!'}
    """

    type: str = "text"
    text: str


class ImageURLPart(ContentPart):
    """
    >>> ImagePart(image_url="http://example.com/image.jpg").model_dump()
    {'type': 'image', 'image_url': 'http://example.com/image.jpg'}
    """

    class ImageURL(BaseModel):
        url: str
        """The URL of the image, can be data URI scheme like `data:image/png;base64,...`."""
        id: str | None = None
        """The ID of the image, to allow LLMs to distinguish different images."""

    type: str = "image_url"
    image_url: str


class AudioURLPart(ContentPart):
    """
    >>> AudioURLPart(audio_url=AudioURLPart.AudioURL(url="https://example.com/audio.mp3")).model_dump()
    {'type': 'audio_url', 'audio_url': {'url': 'https://example.com/audio.mp3', 'id': None}}
    """

    class AudioURL(BaseModel):
        url: str
        """The URL of the audio, can be data URI scheme like `data:audio/aac;base64,...`."""
        id: str | None = None
        """The ID of the audio, to allow LLMs to distinguish different audios."""

    type: str = "audio_url"
    audio_url: AudioURL


class ToolCall(BaseModel):
    """
    A tool call requested by the assistant.

    >>> ToolCall(
    ...     id="123",
    ...     function=ToolCall.FunctionBody(
    ...         name="function",
    ...         arguments="{}"
    ...     ),
    ... ).model_dump()
    {'type': 'function', 'id': '123', 'function': {'name': 'function', 'arguments': '{}'}}
    """

    class FunctionBody(BaseModel):
        name: str
        arguments: str | None

    type: Literal["function"] = "function"

    id: str
    """The ID of the tool call."""
    function: FunctionBody
    """The function body of the tool call."""


class ToolCallPart(BaseModel):
    """A part of the tool call."""

    arguments_part: str | None = None
    """A part of the arguments of the tool call."""


class Message(BaseModel):
    """A message in a conversation."""

    role: Literal[
        "system",
        "user",
        "assistant",
        "tool",
    ]

    content: str | list[ContentPart]
    """The content of the message."""


class AssistantMessageSegment(Message):
    """A message segment from the assistant."""

    role: str = "assistant"
    tool_calls: list[ToolCall] | list[dict] | None = None


class ToolCallMessageSegment(Message):
    """A message segment representing a tool call."""

    role: str = "tool"
    tool_call_id: str


class UserMessageSegment(Message):
    """A message segment from the user."""

    role: str = "user"


class SystemMessageSegment(Message):
    """A message segment from the system."""

    role: str = "system"
