# Inspired by MoonshotAI/kosong, credits to MoonshotAI/kosong authors for the original implementation.
# License: Apache License 2.0

from typing import Any, ClassVar, Literal, cast

from pydantic import BaseModel, GetCoreSchemaHandler, model_serializer, model_validator
from pydantic_core import core_schema


class ContentPart(BaseModel):
    """A part of the content in a message."""

    __content_part_registry: ClassVar[dict[str, type["ContentPart"]]] = {}

    type: Literal["text", "think", "image_url", "audio_url"]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)

        invalid_subclass_error_msg = f"ContentPart subclass {cls.__name__} must have a `type` field of type `str`"

        type_value = getattr(cls, "type", None)
        if type_value is None or not isinstance(type_value, str):
            raise ValueError(invalid_subclass_error_msg)

        cls.__content_part_registry[type_value] = cls

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        # If we're dealing with the base ContentPart class, use custom validation
        if cls.__name__ == "ContentPart":

            def validate_content_part(value: Any) -> Any:
                # if it's already an instance of a ContentPart subclass, return it
                if hasattr(value, "__class__") and issubclass(value.__class__, cls):
                    return value

                # if it's a dict with a type field, dispatch to the appropriate subclass
                if isinstance(value, dict) and "type" in value:
                    type_value: Any | None = cast(dict[str, Any], value).get("type")
                    if not isinstance(type_value, str):
                        raise ValueError(f"Cannot validate {value} as ContentPart")
                    target_class = cls.__content_part_registry[type_value]
                    return target_class.model_validate(value)

                raise ValueError(f"Cannot validate {value} as ContentPart")

            return core_schema.no_info_plain_validator_function(validate_content_part)

        # for subclasses, use the default schema
        return handler(source_type)


class TextPart(ContentPart):
    """
    >>> TextPart(text="Hello, world!").model_dump()
    {'type': 'text', 'text': 'Hello, world!'}
    """

    type: str = "text"
    text: str


class ThinkPart(ContentPart):
    """
    >>> ThinkPart(think="I think I need to think about this.").model_dump()
    {'type': 'think', 'think': 'I think I need to think about this.', 'encrypted': None}
    """

    type: str = "think"
    think: str
    encrypted: str | None = None
    """Encrypted thinking content, or signature."""

    def merge_in_place(self, other: Any) -> bool:
        if not isinstance(other, ThinkPart):
            return False
        if self.encrypted:
            return False
        self.think += other.think
        if other.encrypted:
            self.encrypted = other.encrypted
        return True


class ImageURLPart(ContentPart):
    """
    >>> ImageURLPart(image_url="http://example.com/image.jpg").model_dump()
    {'type': 'image_url', 'image_url': 'http://example.com/image.jpg'}
    """

    class ImageURL(BaseModel):
        url: str
        """The URL of the image, can be data URI scheme like `data:image/png;base64,...`."""
        id: str | None = None
        """The ID of the image, to allow LLMs to distinguish different images."""

    type: str = "image_url"
    image_url: ImageURL


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
    extra_content: dict[str, Any] | None = None
    """Extra metadata for the tool call."""

    @model_serializer(mode="wrap")
    def serialize(self, handler):
        data = handler(self)
        if self.extra_content is None:
            data.pop("extra_content", None)
        return data


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

    content: str | list[ContentPart] | None = None
    """The content of the message."""

    tool_calls: list[ToolCall] | list[dict] | None = None
    """The tool calls of the message."""

    tool_call_id: str | None = None
    """The ID of the tool call."""

    @model_validator(mode="after")
    def check_content_required(self):
        # assistant + tool_calls is not None: allow content to be None
        if self.role == "assistant" and self.tool_calls is not None:
            return self

        # other all cases: content is required
        if self.content is None:
            raise ValueError(
                "content is required unless role='assistant' and tool_calls is not None"
            )
        return self

    @model_serializer(mode="wrap")
    def serialize(self, handler):
        data = handler(self)
        if self.tool_calls is None:
            data.pop("tool_calls", None)
        if self.tool_call_id is None:
            data.pop("tool_call_id", None)
        return data


class AssistantMessageSegment(Message):
    """A message segment from the assistant."""

    role: Literal["assistant"] = "assistant"


class ToolCallMessageSegment(Message):
    """A message segment representing a tool call."""

    role: Literal["tool"] = "tool"


class UserMessageSegment(Message):
    """A message segment from the user."""

    role: Literal["user"] = "user"


class SystemMessageSegment(Message):
    """A message segment from the system."""

    role: Literal["system"] = "system"
