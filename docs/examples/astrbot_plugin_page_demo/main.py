from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from astrbot.api.star import Context, Star
from astrbot.api.web import (
    PluginUploadFile,
    error_response,
    file_response,
    json_response,
    request,
    stream_response,
)
from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

PLUGIN_NAME = "astrbot_plugin_page_demo"


class PageDemoPlugin(Star):
    """Demo plugin that exercises Plugin Page bridge and backend APIs."""

    def __init__(self, context: Context) -> None:
        super().__init__(context)
        self.data_dir = Path(get_astrbot_plugin_data_path()) / PLUGIN_NAME
        self.upload_dir = self.data_dir / "uploads"
        self.last_settings: dict[str, Any] = {
            "enabled": True,
            "threshold": 0.8,
            "note": "Hello from AstrBot Plugin Pages",
        }
        for route, handler, methods, desc in (
            (
                f"/{PLUGIN_NAME}/echo/<item_id>",
                self.page_echo,
                ["GET"],
                "Echo query and request context",
            ),
            (
                f"/{PLUGIN_NAME}/settings/save",
                self.save_settings,
                ["POST"],
                "Save demo settings",
            ),
            (
                f"/{PLUGIN_NAME}/files/import",
                self.import_file,
                ["POST"],
                "Import uploaded file",
            ),
            (
                f"/{PLUGIN_NAME}/files/export",
                self.export_file,
                ["GET"],
                "Export demo JSON file",
            ),
            (
                f"/{PLUGIN_NAME}/events",
                self.stream_events,
                ["GET"],
                "Stream demo SSE events",
            ),
            (
                f"/{PLUGIN_NAME}/error",
                self.demo_error,
                ["GET"],
                "Return a demo bridge error",
            ),
        ):
            context.register_web_api(route, handler, methods, desc)

    async def page_echo(self, item_id: str):
        """Return request context and query values for bridge.apiGet().

        Args:
            item_id: Dynamic route parameter.

        Returns:
            JSON response containing request context details.
        """
        return json_response(
            {
                "item_id": item_id,
                "path_params": request.path_params,
                "query": {
                    "limit": request.query.get("limit", 20, type=int),
                    "tag": request.query.get("tag", ""),
                    "all_tags": request.query.getlist("tag"),
                },
                "request": {
                    "method": request.method,
                    "path": request.path,
                    "plugin_name": request.plugin_name,
                    "username": request.username,
                    "content_type": request.content_type,
                    "client_host": request.client_host,
                },
                "server_time": int(time.time()),
                "last_settings": self.last_settings,
            }
        )

    async def save_settings(self):
        """Read bridge.apiPost() JSON and keep it in memory.

        Returns:
            JSON response containing the saved payload.
        """
        payload = await request.json(default={})
        if not isinstance(payload, dict):
            return error_response("settings payload must be a JSON object")

        enabled = payload.get("enabled")
        threshold = payload.get("threshold")
        if not isinstance(enabled, bool):
            return error_response("enabled must be a boolean")
        if not isinstance(threshold, int | float):
            return error_response("threshold must be a number")

        self.last_settings = {
            "enabled": enabled,
            "threshold": float(threshold),
            "note": str(payload.get("note") or ""),
            "saved_at": int(time.time()),
        }
        return json_response({"saved": True, "settings": self.last_settings})

    async def import_file(self):
        """Read bridge.upload() multipart data and save the uploaded file.

        Returns:
            JSON response containing uploaded file metadata.
        """
        form = await request.form()
        files = await request.files()
        upload: PluginUploadFile | None = files.get("file")
        if not isinstance(upload, PluginUploadFile):
            return error_response("missing file", status_code=400)

        self.upload_dir.mkdir(parents=True, exist_ok=True)
        filename = Path(upload.filename or "upload.bin").name
        saved_path = self.upload_dir / filename
        await upload.save(saved_path)
        return json_response(
            {
                "filename": filename,
                "content_type": upload.content_type,
                "content_length": upload.content_length,
                "saved_path": str(saved_path),
                "form_fields": dict(form.items()),
            }
        )

    async def export_file(self):
        """Create and return a JSON file for bridge.download().

        Returns:
            File download response.
        """
        self.data_dir.mkdir(parents=True, exist_ok=True)
        export_path = self.data_dir / "plugin-page-demo-export.json"
        export_payload = {
            "plugin": PLUGIN_NAME,
            "generated_at": int(time.time()),
            "format": request.query.get("format", "json"),
            "settings": self.last_settings,
        }
        export_path.write_text(
            json.dumps(export_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return file_response(
            export_path,
            filename="plugin-page-demo-export.json",
            content_type="application/json",
        )

    async def stream_events(self):
        """Stream Server-Sent Events for bridge.subscribeSSE().

        Returns:
            Streaming response using the SSE media type.
        """
        count = max(1, min(request.query.get("count", 5, type=int), 20))
        delay_ms = max(50, min(request.query.get("delay_ms", 500, type=int), 5000))

        async def events():
            for index in range(count):
                payload = {
                    "index": index + 1,
                    "count": count,
                    "time": int(time.time()),
                }
                yield f"id: {index + 1}\ndata: {json.dumps(payload)}\n\n"
                await asyncio.sleep(delay_ms / 1000)

        return stream_response(events())

    async def demo_error(self):
        """Return a predictable error for bridge error handling.

        Returns:
            Standard AstrBot error response.
        """
        return error_response("demo error from plugin backend", status_code=400)
