"""Legacy html_renderer facade over the render capability."""

from __future__ import annotations

from typing import Any


class HtmlRendererFacade:
    """Legacy astrbot.core.html_renderer shape backed by ctx.render."""

    _ctx: Any = None

    @classmethod
    def initialize(cls, ctx: Any) -> None:
        """Bind the plugin context (called once by the compat loader)."""
        cls._ctx = ctx

    async def render_custom_template(
        self,
        tmpl_str: str,
        tmpl_data: dict,
        return_url: bool = False,
        **options: Any,
    ) -> Any:
        """Render a Jinja2 template into an image.

        Returns an AssetRef rather than a local path; media components accept
        it directly, so `event.image_result(asset)` keeps working.
        """
        from ...render import RenderOptions

        if HtmlRendererFacade._ctx is None:
            raise ValueError("html_renderer not initialized")
        return await HtmlRendererFacade._ctx.render.html(
            tmpl_str,
            tmpl_data,
            options=RenderOptions(
                width=options.get("width"),
                extra=options.get("extra"),
            ),
        )

    async def render_t2i(
        self,
        text: str,
        use_network: bool = True,
        return_url: bool = False,
        template_name: str | None = None,
        **_: Any,
    ) -> Any:
        """Render plain text into an image with the default t2i template.

        Returns an AssetRef rather than a local path; media components accept
        it directly.
        """
        from ...render import TextRenderOptions

        if HtmlRendererFacade._ctx is None:
            raise ValueError("html_renderer not initialized")
        return await HtmlRendererFacade._ctx.render.text(
            text,
            options=TextRenderOptions(template_name=template_name),
        )
