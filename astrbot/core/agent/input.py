"""Portable input components without platform serialization or media I/O."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, StrictStr, model_validator


class PlainInput(BaseModel):
    """Plain text supplied in the current input, independent of model history."""

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True, extra="forbid")

    type: Literal["plain"] = "plain"
    text: StrictStr = Field(min_length=1)


class AttachmentInput(BaseModel):
    """A media reference and optional label; reading it belongs to the runtime."""

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True, extra="forbid")

    path: StrictStr | None = Field(default=None, min_length=1)
    url: StrictStr | None = Field(default=None, min_length=1)
    text: StrictStr | None = None

    @model_validator(mode="after")
    def validate_reference(self) -> AttachmentInput:
        """Require one unambiguous reference without touching the resource.

        Returns:
            The validated attachment.

        Raises:
            ValueError: If both references are set, or neither is provided.
        """
        if (self.path is None) == (self.url is None):
            raise ValueError("An attachment requires exactly one path or url")
        return self

    @property
    def source(self) -> str:
        """Return the validated path or URL without resolving or downloading it."""
        if self.path is not None:
            return self.path
        assert self.url is not None
        return self.url


class ImageInput(AttachmentInput):
    """An image supplied explicitly as part of the input."""

    type: Literal["image"] = "image"


class FileInput(AttachmentInput):
    """A file reference supplied explicitly as part of the input."""

    type: Literal["file"] = "file"


InputComponent: TypeAlias = PlainInput | ImageInput | FileInput


def parse_input_content(messages: list[dict]) -> list[InputComponent]:
    """Validate external components and create detached, immutable input values.

    Args:
        messages: Ordered plain, image, and file dictionaries from a tool or store.

    Returns:
        Typed components preserving order and the existing path-first convention.

    Raises:
        ValueError: If the input is empty, malformed, or has unsupported components.
    """
    if not isinstance(messages, list) or not messages:
        raise ValueError("messages must be a nonempty list of components")
    content: list[InputComponent] = []
    for index, item in enumerate(messages):
        if not isinstance(item, dict):
            raise ValueError(f"messages[{index}] must be an object")
        kind = item.get("type")
        if kind == "plain":
            text = item.get("text")
            if not isinstance(text, str) or not text.strip():
                raise ValueError(f"messages[{index}].text must be nonempty")
            content.append(PlainInput(text=text))
        elif kind in ("image", "file"):
            key = "path" if item.get("path") else "url"
            reference = item.get(key)
            if not isinstance(reference, str) or not reference.strip():
                raise ValueError(f"messages[{index}] requires a nonempty path or url")
            label = item.get("text", "")
            if not isinstance(label, str):
                raise ValueError(f"messages[{index}].text must be a string")
            component = ImageInput if kind == "image" else FileInput
            content.append(
                component(
                    path=reference if key == "path" else None,
                    url=reference if key == "url" else None,
                    text=label.strip() or None,
                )
            )
        else:
            raise ValueError(f"Unsupported messages[{index}].type: {kind!r}")
    return content


def format_input_content(content: Sequence[InputComponent]) -> str:
    """Format typed content as text, retaining ordered attachment references.

    Args:
        content: Validated input components.

    Returns:
        Plain instructions and attachment references, without opening resources.
    """
    return "\n".join(
        item.text
        if isinstance(item, PlainInput)
        else f"[{item.type}] " + (f"{item.text} " if item.text else "") + item.source
        for item in content
    )
