"""Conversation-scoped image tools; model arguments never select an owner or path."""

import json

from pydantic import Field
from pydantic.dataclasses import dataclass

from astrbot.core.agent.tool import FunctionTool
from astrbot.core.astr_agent_context import AstrAgentContext


@dataclass
class ImageCatalogTool(FunctionTool[AstrAgentContext]):
    name: str = "image_catalog"
    description: str = (
        "List or search this conversation's image descriptions and separate user notes. "
        "Use returned occurrence IDs with read_image to inspect an image for your own answer, "
        "or with send_message_to_user as an image occurrence_id to send its original to the user. "
        "Ask the user when candidates are ambiguous. "
        "Catalog order is not an absolute image number in the user's conversation."
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "query": {"type": "string", "maxLength": 256},
                "cursor": {
                    "type": "array",
                    "minItems": 2,
                    "maxItems": 2,
                    "items": {"type": ["integer", "string"]},
                },
            },
            "additionalProperties": False,
        }
    )

    async def call(self, context, **kwargs):
        """Return one bounded metadata page.

        Args:
            context: Server execution context.
            **kwargs: Optional literal search and opaque pagination cursor.

        Returns:
            JSON metadata, without image bytes or filesystem paths.
        """
        turn = context.context.image_context
        if turn is None or not turn.configured:
            return "Image catalog is unavailable."
        cursor = kwargs.get("cursor")
        if cursor is not None:
            if (
                not isinstance(cursor, list)
                or len(cursor) != 2
                or type(cursor[0]) is not int
                or not isinstance(cursor[1], str)
            ):
                return "Invalid catalog cursor."
            cursor = tuple(cursor)
        query = kwargs.get("query")
        if query is not None and (not isinstance(query, str) or len(query) > 256):
            return "Search text must be at most 256 characters."
        return json.dumps(
            await turn.catalog(query=query, cursor=cursor), ensure_ascii=False
        )


@dataclass
class ReadImageTool(FunctionTool[AstrAgentContext]):
    name: str = "read_image"
    description: str = (
        "Inspect an authorized image selected from this conversation's catalog for your own answer; "
        "this does not send the image to the user. To share the original image with the user, "
        "use send_message_to_user with an image component and the catalog occurrence_id. "
        "Provide a focused question when details are missing from its description. "
        "Set refresh_description only when explicitly asked to update the stored observation."
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "occurrence_id": {"type": "string", "maxLength": 128},
                "question": {"type": "string", "maxLength": 2048},
                "refresh_description": {"type": "boolean"},
            },
            "required": ["occurrence_id"],
            "additionalProperties": False,
        }
    )

    async def call(self, context, **kwargs):
        """Request a visual step or a directed text answer.

        Args:
            context: Server execution context.
            **kwargs: Occurrence ID, question, and explicit refresh intent.

        Returns:
            Text status or directed answer, never an inline image blob.
        """
        turn = context.context.image_context
        if turn is None or not turn.configured:
            return "Image retrieval is unavailable."
        occurrence = kwargs.get("occurrence_id")
        question = kwargs.get("question", "")
        refresh = kwargs.get("refresh_description", False)
        if (
            not isinstance(occurrence, str)
            or len(occurrence) > 128
            or not isinstance(question, str)
            or len(question) > 2048
            or not isinstance(refresh, bool)
        ):
            return "Invalid image retrieval arguments."
        return await turn.read_existing(
            occurrence, question=question, refresh_description=refresh
        )


@dataclass
class ImageUserNoteTool(FunctionTool[AstrAgentContext]):
    name: str = "image_user_note"
    description: str = (
        "Save a correction or annotation explicitly supplied by the user for an image. "
        "Keep the user's wording; do not write your own visual inference as a user correction. "
        "This does not replace the model-generated image description."
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "occurrence_id": {"type": "string", "maxLength": 128},
                "annotation": {"type": "string", "maxLength": 4096},
            },
            "required": ["occurrence_id", "annotation"],
            "additionalProperties": False,
        }
    )

    async def call(self, context, **kwargs):
        """Apply a separate user annotation with optimistic concurrency.

        Args:
            context: Server execution context.
            **kwargs: Selected occurrence and user-supplied annotation.

        Returns:
            Update status.
        """
        turn = context.context.image_context
        if turn is None or not turn.configured:
            return "Image catalog is unavailable."
        occurrence = kwargs.get("occurrence_id")
        if not isinstance(occurrence, str) or len(occurrence) > 128:
            return "Invalid image occurrence."
        return await turn.update_note(occurrence, kwargs.get("annotation"))
