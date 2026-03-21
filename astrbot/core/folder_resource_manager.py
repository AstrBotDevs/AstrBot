from collections.abc import Awaitable, Callable
from typing import Any, Generic, TypeVar

from astrbot.core.sentinels import NOT_GIVEN

TFolder = TypeVar("TFolder")
TItem = TypeVar("TItem")


class FolderResourceManager(Generic[TFolder, TItem]):
    """Reusable folder manager for folder-bound resources."""

    def __init__(
        self,
        *,
        create_folder: Callable[..., Awaitable[TFolder]],
        get_folder: Callable[[str], Awaitable[TFolder | None]],
        get_folders: Callable[[str | None], Awaitable[list[TFolder]]],
        get_all_folders: Callable[[], Awaitable[list[TFolder]]],
        update_folder: Callable[..., Awaitable[TFolder | None]],
        delete_folder: Callable[[str], Awaitable[None]],
        get_items_by_folder: Callable[[str | None], Awaitable[list[TItem]]],
        move_item_to_folder: Callable[[str, str | None], Awaitable[TItem | None]],
        batch_update_sort_order: Callable[[list[dict[str, Any]]], Awaitable[None]],
        on_item_moved: Callable[[TItem], Awaitable[None]] | None = None,
        on_sort_order_updated: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self._create_folder = create_folder
        self._get_folder = get_folder
        self._get_folders = get_folders
        self._get_all_folders = get_all_folders
        self._update_folder = update_folder
        self._delete_folder = delete_folder
        self._get_items_by_folder = get_items_by_folder
        self._move_item_to_folder = move_item_to_folder
        self._batch_update_sort_order = batch_update_sort_order
        self._on_item_moved = on_item_moved
        self._on_sort_order_updated = on_sort_order_updated

    async def create_folder(
        self,
        name: str,
        parent_id: str | None = None,
        description: str | None = None,
        sort_order: int = 0,
    ) -> TFolder:
        return await self._create_folder(
            name=name,
            parent_id=parent_id,
            description=description,
            sort_order=sort_order,
        )

    async def get_folder(self, folder_id: str) -> TFolder | None:
        return await self._get_folder(folder_id)

    async def get_folders(self, parent_id: str | None = None) -> list[TFolder]:
        return await self._get_folders(parent_id)

    async def get_all_folders(self) -> list[TFolder]:
        return await self._get_all_folders()

    async def update_folder(
        self,
        folder_id: str,
        name: str | None = None,
        parent_id: Any = NOT_GIVEN,
        description: Any = NOT_GIVEN,
        sort_order: int | None = None,
    ) -> TFolder | None:
        return await self._update_folder(
            folder_id=folder_id,
            name=name,
            parent_id=parent_id,
            description=description,
            sort_order=sort_order,
        )

    async def delete_folder(self, folder_id: str) -> None:
        await self._delete_folder(folder_id)

    async def get_items_by_folder(self, folder_id: str | None = None) -> list[TItem]:
        return await self._get_items_by_folder(folder_id)

    async def move_item_to_folder(
        self,
        item_id: str,
        folder_id: str | None,
    ) -> TItem | None:
        item = await self._move_item_to_folder(item_id, folder_id)
        if item and self._on_item_moved:
            await self._on_item_moved(item)
        return item

    async def batch_update_sort_order(
        self,
        items: list[dict[str, Any]],
    ) -> None:
        await self._batch_update_sort_order(items)
        if self._on_sort_order_updated:
            await self._on_sort_order_updated()

    async def get_folder_tree(self) -> list[dict[str, Any]]:
        all_folders = await self.get_all_folders()
        folder_map: dict[str, dict[str, Any]] = {}

        for folder in all_folders:
            folder_id = getattr(folder, "folder_id")
            folder_map[folder_id] = {
                "folder_id": folder_id,
                "name": getattr(folder, "name"),
                "parent_id": getattr(folder, "parent_id"),
                "description": getattr(folder, "description"),
                "sort_order": getattr(folder, "sort_order"),
                "children": [],
            }

        root_folders: list[dict[str, Any]] = []
        for folder_data in folder_map.values():
            parent_id = folder_data["parent_id"]
            if parent_id is None:
                root_folders.append(folder_data)
            elif parent_id in folder_map:
                folder_map[parent_id]["children"].append(folder_data)

        def sort_folders(
            folders: list[dict[str, Any]],
        ) -> list[dict[str, Any]]:
            folders.sort(key=lambda folder: (folder["sort_order"], folder["name"]))
            for folder in folders:
                children = folder["children"]
                if children:
                    folder["children"] = sort_folders(children)
            return folders

        return sort_folders(root_folders)
