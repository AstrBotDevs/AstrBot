from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from astrbot_sdk.errors import InvalidRequest, NotFound
from astrbot_sdk.render import RenderOptions, TextRenderOptions

from .assets import AssetStore

if TYPE_CHECKING:
    from astrbot.core.star.context import Context


class RenderImageService:
    """Serve the render.image capability through the AstrBot HTML renderer."""

    capability_id = "render.image"

    def __init__(self, context: Context, store: AssetStore) -> None:
        """Initialize the service.

        Args:
            context: AstrBot star context with the HTML renderer.
            store: Asset store holding rendered images.
        """
        self._context = context
        self._store = store

    async def handle(self, operation: str, payload: dict[str, Any]) -> Any:
        """Render and store the result image, returning its asset reference."""
        if operation == "html":
            options = payload.get("options")
            if options is not None and not isinstance(options, RenderOptions):
                raise InvalidRequest("html requires a RenderOptions payload")
            path = await self._context.html_renderer.render_custom_template(
                str(payload["template"]),
                payload.get("data") or {},
                return_url=False,
                options=(dict(options.extra or {}) if options is not None else None),
            )
        elif operation == "text":
            options = payload.get("options")
            if options is not None and not isinstance(options, TextRenderOptions):
                raise InvalidRequest("text requires a TextRenderOptions payload")
            path = await self._context.html_renderer.render_t2i(
                str(payload["text"]),
                return_url=False,
                template_name=(options.template_name if options is not None else None),
            )
        else:
            raise NotFound(f"unknown render operation: {operation}")

        if isinstance(path, str) and path.startswith(("http://", "https://")):
            raise InvalidRequest("renderer returned a URL, expected a local file")
        data = Path(path).read_bytes()
        asset = self._store.put(
            data,
            filename=Path(path).name,
            media_type="image/png",
        )
        return {"asset": asset}
