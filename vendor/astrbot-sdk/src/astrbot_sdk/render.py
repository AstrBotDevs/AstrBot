from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .protocol_registry import register_protocol_dataclass

if TYPE_CHECKING:
    from .assets import AssetRef
    from .context import PluginContext

_RENDER_CAPABILITY = "render.image"


@register_protocol_dataclass
@dataclass(frozen=True, slots=True)
class RenderOptions:
    """Options for HTML template rendering."""

    width: int | None = None
    extra: Mapping[str, Any] | None = None


@register_protocol_dataclass
@dataclass(frozen=True, slots=True)
class TextRenderOptions:
    """Options for plain text-to-image rendering."""

    template_name: str | None = None


class RenderService:
    """Render HTML templates or text into images hosted by the Host."""

    def __init__(self, ctx: PluginContext) -> None:
        """Initialize the service.

        Args:
            ctx: Owning plugin context used for Host invocation.
        """
        self._ctx = ctx

    async def html(
        self,
        template: str,
        data: Mapping[str, Any],
        *,
        options: RenderOptions | None = None,
    ) -> AssetRef:
        """Render a Jinja2 HTML template into an image asset.

        Args:
            template: Jinja2 template source.
            data: Template data.
            options: Optional render options.

        Returns:
            Reference to the rendered image asset.
        """
        result = await self._ctx._invoke_capability(
            _RENDER_CAPABILITY,
            "html",
            {"template": template, "data": dict(data), "options": options},
        )
        return result["asset"]

    async def text(
        self,
        text: str,
        *,
        options: TextRenderOptions | None = None,
    ) -> AssetRef:
        """Render plain text into an image asset with the default template.

        Args:
            text: Text to render.
            options: Optional text render options.

        Returns:
            Reference to the rendered image asset.
        """
        result = await self._ctx._invoke_capability(
            _RENDER_CAPABILITY,
            "text",
            {"text": text, "options": options},
        )
        return result["asset"]
