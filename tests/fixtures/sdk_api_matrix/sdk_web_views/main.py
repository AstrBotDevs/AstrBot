"""Dedicated new-SDK plugin covering views, ui_action, WebRequest, and WebResponse."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from astrbot_sdk import MessageEvent, Plugin, ViewResult, ViewSpec, on
from astrbot_sdk.views import load_i18n, read_view_file, scan_views
from astrbot_sdk.web import (
    WebRequest,
    WebResponse,
    WebRouteRegistration,
    error_response,
    file_response,
    json_response,
    normalize_web_result,
    stream_response,
)


class SdkWebViewsPlugin(Plugin):
    """Exercise ChatUI views, views helpers, WebRequest, and WebResponse."""

    def __init__(self, context: Any) -> None:
        super().__init__(context)
        self._plugin_root = Path(__file__).resolve().parent
        self.ctx.web.route(
            "/wv/inspect/<item>",
            methods=("GET", "POST"),
            description="Inspect WebRequest and exercise every WebResponse mode",
        )(self._inspect_route)
        self._reg: WebRouteRegistration = next(
            r for r in self.ctx.web.routes if r.route == "/wv/inspect/<item>"
        )

    async def _inspect_route(self, req: WebRequest, item: str) -> WebResponse:
        """Handle `/wv/inspect/<item>` across rich WebResponse modes."""
        mode = req.query.get("mode", "json")
        if mode == "text":
            return WebResponse.text(f"text:{item}:{req.query.get('q', '')}", status=201)
        if mode == "redirect":
            return WebResponse.redirect(f"/next/{item}", status=307)
        if mode == "response_json":
            return WebResponse.json(
                {
                    "item": item,
                    "method": req.method,
                    "path": req.path,
                    "params": req.path_params,
                    "username": req.username,
                    "client_host": req.client_host,
                    "header_x": req.headers.get("x-test", ""),
                    "body_text": await req.text(),
                    "body_json": await req.json(),
                },
                status=200,
            )
        if mode == "stream_in":
            total = 0
            chunks = 0
            async for chunk in req.stream():
                total += len(chunk)
                chunks += 1
            return json_response({"total": total, "chunks": chunks})
        if mode == "error":
            return error_response("wv-err", status_code=418, data={"item": item})
        if mode == "stream":

            async def _sse():
                yield "wv-s1\n"
                yield b"wv-s2\n"

            return stream_response(_sse(), headers={"x-stream": "1"})
        if mode == "file":
            out = Path(self.ctx.storage.data_dir) / "wv_file.txt"
            os.makedirs(out.parent, exist_ok=True)
            out.write_text(f"FILE:{item}", encoding="utf-8")
            return file_response(out, filename="wv_file.txt")
        if mode == "view_helpers":
            spec = ViewSpec(name="panel", target="plugin_page", title="Panel")
            pages = scan_views(self._plugin_root)
            i18n_data = load_i18n(self._plugin_root)
            meta, stream = await read_view_file(
                self._plugin_root, "panel", "index.html"
            )
            html_bytes = b"".join([part async for part in stream])
            info, norm_stream = await normalize_web_result(WebResponse.text("probe"))
            _ = [part async for part in norm_stream]
            return json_response(
                {
                    "entry": str(spec.entry),
                    "pages": [p.name for p in pages],
                    "i18n_locales": sorted(i18n_data.keys()),
                    "view_meta_len": meta.get("size"),
                    "view_has_title": b"Web Views Panel" in html_bytes,
                    "norm_status": info.status,
                    "route_registered": self._reg.route == "/wv/inspect/<item>",
                }
            )
        return json_response({"item": item, "mode": mode})

    @on.command("wv open", description="Emit mini_card ViewResult")
    async def wv_open(self, event: MessageEvent):
        """Create mini_card ChatUI view."""
        res = event.view_result(
            name="mini_card",
            data={"clicks": 10},
            text="mini-fallback",
            title="Mini Card",
        )
        assert isinstance(res, ViewResult)
        yield res

    @on.ui_action("wv_inc")
    async def wv_inc(self, event: MessageEvent):
        """Increment mini_card click counter via UIInteraction."""
        inter = event.ui_interaction
        assert inter is not None
        prev = int(inter.view.data.get("clicks", 0))
        yield event.view_result(data={"clicks": prev + 1})

    @on.command("wv meta", description="Report view metadata")
    async def wv_meta(self, event: MessageEvent):
        """Return scanned view page count via JSON."""
        yield event.reply(
            json.dumps({"pages": [p.name for p in scan_views(self._plugin_root)]})
        )
