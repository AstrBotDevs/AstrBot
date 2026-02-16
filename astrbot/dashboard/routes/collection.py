from __future__ import annotations

import traceback
from dataclasses import dataclass
from typing import Any

from quart import request

from astrbot.core import DEMO_MODE, logger
from astrbot.core.collection.exporter import CollectionExporter, ExportOptions
from astrbot.core.collection.importer import CollectionImporter
from astrbot.core.collection.models import (
    CollectionValidationError,
    ImportOptions,
    PluginCollection,
)
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.star.star_manager import PluginManager

from .route import Response, Route, RouteContext


@dataclass(slots=True)
class _ImportRequest:
    collection: dict[str, Any]
    import_mode: str = "add"
    apply_configs: bool = True
    overwrite_existing_configs: bool = False
    apply_priority: bool = True
    proxy: str = ""


class CollectionRoute(Route):
    def __init__(
        self,
        context: RouteContext,
        core_lifecycle: AstrBotCoreLifecycle,
        plugin_manager: PluginManager,
    ) -> None:
        super().__init__(context)
        self.core_lifecycle = core_lifecycle
        self.plugin_manager = plugin_manager
        self.exporter = CollectionExporter(plugin_manager)
        self.importer = CollectionImporter(plugin_manager)

        self.routes = {
            "/plugin/collection/export": ("GET", self.export_collection_get),
            "/plugin/collection/import": ("POST", self.import_collection),
            "/plugin/collection/preview": ("POST", self.preview_collection),
            "/plugin/collection/validate": ("POST", self.validate_collection),
        }
        self.register_routes()

    async def export_collection_get(self):
        if DEMO_MODE:
            return (
                Response()
                .error("You are not permitted to do this operation in demo mode")
                .__dict__
            )

        name = str(request.args.get("name") or "").strip()
        if not name:
            return Response().error("name is required").__dict__

        options = ExportOptions(
            name=name,
            description=str(request.args.get("description") or ""),
            author=str(request.args.get("author") or ""),
            version=str(request.args.get("version") or "1.0.0"),
            include_configs=str(request.args.get("include_configs", "true")).lower()
            not in {"0", "false", "no"},
            include_priority=str(request.args.get("include_priority", "true")).lower()
            not in {"0", "false", "no"},
            exclude_plugins=(
                request.args.getlist("exclude_plugins")
                if request.args.getlist("exclude_plugins")
                else None
            ),
        )

        try:
            payload = await self.exporter.export(options)
            return Response().ok(payload).__dict__
        except Exception as e:
            logger.error(
                f"/api/plugin/collection/export(GET): {traceback.format_exc()}"
            )
            return Response().error(str(e)).__dict__

    async def _parse_collection(self, body: Any) -> PluginCollection:
        if not isinstance(body, dict):
            raise CollectionValidationError("collection must be an object")
        if "collection" in body and isinstance(body.get("collection"), dict):
            body = body["collection"]
        if not isinstance(body, dict):
            raise CollectionValidationError("collection must be an object")
        return PluginCollection.from_dict(body)

    async def validate_collection(self):
        try:
            data = await request.get_json()
            _ = await self._parse_collection(data)
            return Response().ok({"valid": True}).__dict__
        except CollectionValidationError as e:
            return Response().ok({"valid": False, "errors": [str(e)]}).__dict__
        except Exception as e:
            logger.error(f"/api/plugin/collection/validate: {traceback.format_exc()}")
            return Response().error(str(e)).__dict__

    async def preview_collection(self):
        try:
            data = await request.get_json()
            import_mode = "add"
            if isinstance(data, dict) and data.get("import_mode") in {"add", "clean"}:
                import_mode = str(data.get("import_mode"))
            collection = await self._parse_collection(data)
            preview = await self.importer.preview(collection, import_mode=import_mode)
            return Response().ok(preview).__dict__
        except CollectionValidationError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"/api/plugin/collection/preview: {traceback.format_exc()}")
            return Response().error(str(e)).__dict__

    async def import_collection(self):
        if DEMO_MODE:
            return (
                Response()
                .error("You are not permitted to do this operation in demo mode")
                .__dict__
            )

        try:
            data = await request.get_json()
            if not isinstance(data, dict):
                return Response().error("Invalid request body").__dict__

            raw_collection = data.get("collection")
            req = _ImportRequest(
                collection=raw_collection if isinstance(raw_collection, dict) else {},
                import_mode=str(data.get("import_mode") or "add"),
                apply_configs=bool(data.get("apply_configs", True)),
                overwrite_existing_configs=bool(
                    data.get("overwrite_existing_configs", False)
                ),
                apply_priority=bool(data.get("apply_priority", True)),
                proxy=str(data.get("proxy") or ""),
            )

            collection = PluginCollection.from_dict(req.collection)
            result = await self.importer.import_collection(
                collection,
                ImportOptions(
                    import_mode=req.import_mode,
                    apply_configs=req.apply_configs,
                    overwrite_existing_configs=req.overwrite_existing_configs,
                    apply_priority=req.apply_priority,
                    proxy=req.proxy,
                ),
            )
            return Response().ok(result).__dict__

        except CollectionValidationError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"/api/plugin/collection/import: {traceback.format_exc()}")
            return Response().error(str(e)).__dict__
