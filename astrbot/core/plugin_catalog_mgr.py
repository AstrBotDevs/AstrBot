from dataclasses import asdict
from typing import Any

from astrbot.core.db import BaseDatabase
from astrbot.core.db.po import PluginCatalogFolder
from astrbot.core.folder_resource_manager import FolderResourceManager
from astrbot.core.star.star import StarMetadata
from astrbot.core.star.star_manager import PluginManager


class PluginCatalogManager:
    def __init__(self, db: BaseDatabase, plugin_manager: PluginManager) -> None:
        self.db = db
        self.plugin_manager = plugin_manager
        self.folder_manager = FolderResourceManager[PluginCatalogFolder, Any](
            create_folder=lambda **kwargs: self.db.insert_resource_folder(
                "plugin",
                **kwargs,
            ),
            get_folder=lambda folder_id: self.db.get_resource_folder_by_id(
                "plugin",
                folder_id,
            ),
            get_folders=lambda parent_id: self.db.get_resource_folders(
                "plugin",
                parent_id,
            ),
            get_all_folders=lambda: self.db.get_all_resource_folders("plugin"),
            update_folder=lambda **kwargs: self.db.update_resource_folder(
                "plugin",
                **kwargs,
            ),
            delete_folder=lambda folder_id: self.db.delete_resource_folder(
                "plugin",
                folder_id,
            ),
            get_items_by_folder=lambda folder_id: self.db.get_resources_by_folder(
                "plugin",
                folder_id,
            ),
            move_item_to_folder=lambda item_id, folder_id: self.db.move_resource_to_folder(
                "plugin",
                item_id,
                folder_id,
            ),
            batch_update_sort_order=lambda items: self.db.batch_update_resource_sort_order(
                "plugin",
                items,
            ),
        )

    async def initialize(self) -> None:
        await self.sync_catalog()

    async def sync_catalog(self) -> None:
        runtime_plugins = self._get_runtime_plugins()
        for plugin in runtime_plugins:
            existing = await self.db.get_resource_by_id("plugin", plugin.name)
            folder_id = getattr(existing, "folder_id", None) if existing else None
            sort_order = getattr(existing, "sort_order", 0) if existing else 0
            await self.db.upsert_resource(
                "plugin",
                plugin.name,
                folder_id=folder_id,
                sort_order=sort_order,
            )
        await self.db.prune_resources(
            "plugin",
            [plugin.name for plugin in runtime_plugins],
        )

    async def get_plugins_by_folder(self, folder_id: str | None = None) -> list[dict]:
        await self.sync_catalog()
        plugin_rows = await self.folder_manager.get_items_by_folder(folder_id)
        runtime_map = {plugin.name: plugin for plugin in self._get_runtime_plugins()}
        result = []
        for row in plugin_rows:
            plugin_name = getattr(row, "plugin_name")
            runtime_plugin = runtime_map.get(plugin_name)
            if runtime_plugin is None:
                continue
            result.append(self._serialize_plugin(runtime_plugin, row))
        return result

    async def move_plugin_to_folder(
        self, plugin_name: str, folder_id: str | None
    ) -> Any | None:
        await self.sync_catalog()
        return await self.folder_manager.move_item_to_folder(plugin_name, folder_id)

    async def create_folder(
        self,
        name: str,
        parent_id: str | None = None,
        description: str | None = None,
        sort_order: int = 0,
    ) -> PluginCatalogFolder:
        return await self.folder_manager.create_folder(
            name=name,
            parent_id=parent_id,
            description=description,
            sort_order=sort_order,
        )

    async def get_folder(self, folder_id: str) -> PluginCatalogFolder | None:
        return await self.folder_manager.get_folder(folder_id)

    async def get_folders(
        self, parent_id: str | None = None
    ) -> list[PluginCatalogFolder]:
        return await self.folder_manager.get_folders(parent_id)

    async def get_all_folders(self) -> list[PluginCatalogFolder]:
        return await self.folder_manager.get_all_folders()

    async def update_folder(
        self,
        folder_id: str,
        name: str | None = None,
        parent_id: str | None = None,
        description: str | None = None,
        sort_order: int | None = None,
    ) -> PluginCatalogFolder | None:
        return await self.folder_manager.update_folder(
            folder_id=folder_id,
            name=name,
            parent_id=parent_id,
            description=description,
            sort_order=sort_order,
        )

    async def delete_folder(self, folder_id: str) -> None:
        await self.folder_manager.delete_folder(folder_id)

    async def batch_update_sort_order(self, items: list[dict]) -> None:
        await self.sync_catalog()
        await self.folder_manager.batch_update_sort_order(items)

    async def get_folder_tree(self) -> list[dict]:
        return await self.folder_manager.get_folder_tree()

    def _get_runtime_plugins(self) -> list[StarMetadata]:
        return [
            plugin
            for plugin in self.plugin_manager.context.get_all_stars()
            if plugin.name
            and any(
                [
                    plugin.name,
                    plugin.author,
                    plugin.desc,
                    plugin.version,
                    plugin.display_name,
                ]
            )
        ]

    @staticmethod
    def _serialize_plugin(plugin: StarMetadata, row: Any) -> dict[str, Any]:
        data = asdict(plugin)
        data["folder_id"] = getattr(row, "folder_id", None)
        data["sort_order"] = getattr(row, "sort_order", 0)
        data.pop("star_cls_type", None)
        data.pop("star_cls", None)
        data.pop("module", None)
        data.pop("config", None)
        return data
