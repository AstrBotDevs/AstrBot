from __future__ import annotations

import asyncio
from typing import Any

from astrbot.core import logger
from astrbot.core.star.star_manager import PluginManager

from .compatibility import ConflictDetectionCompatibility, PriorityCompatibility
from .models import ImportOptions, PluginCollection


class CollectionImporter:
    def __init__(self, plugin_manager: PluginManager) -> None:
        self.plugin_manager = plugin_manager

    async def preview(
        self, collection: PluginCollection, *, import_mode: str
    ) -> dict[str, Any]:
        installed = {p.name for p in self.plugin_manager.context.get_all_stars()}

        plugins_to_install = []
        plugins_to_skip = []
        for p in collection.plugins:
            if p.name in installed:
                plugins_to_skip.append(
                    {"name": p.name, "repo": p.repo, "status": "installed"}
                )
            else:
                plugins_to_install.append(
                    {
                        "name": p.name,
                        "repo": p.repo,
                        "exported_version": p.exported_version,
                        "status": "not_installed",
                    },
                )

        plugins_to_uninstall: list[dict[str, Any]] = []
        if import_mode == "clean":
            keep = {p.name for p in collection.plugins}
            for p in self.plugin_manager.context.get_all_stars():
                if p.reserved:
                    continue
                if p.name in keep:
                    continue
                plugins_to_uninstall.append({"name": p.name})

        configs_count = 0
        if isinstance(collection.plugin_configs, dict):
            configs_count = len(collection.plugin_configs)

        return {
            "metadata": collection.metadata.to_dict(),
            "plugins_to_install": plugins_to_install,
            "plugins_to_skip": plugins_to_skip,
            "plugins_to_uninstall": plugins_to_uninstall,
            "configs_count": configs_count,
            "has_priority_overrides": bool(collection.handler_priority_overrides),
            "conflict_detection_available": ConflictDetectionCompatibility.is_conflict_detection_available(),
        }

    async def import_collection(
        self, collection: PluginCollection, options: ImportOptions
    ) -> dict[str, Any]:
        if options.import_mode not in {"add", "clean"}:
            raise ValueError("import_mode must be 'add' or 'clean'")

        installed_before = {p.name for p in self.plugin_manager.context.get_all_stars()}

        conflict_report = await ConflictDetectionCompatibility.check_conflicts(
            [p.name for p in collection.plugins],
        )

        uninstalled: list[dict[str, Any]] = []
        uninstall_failed: list[str] = []
        if options.import_mode == "clean":
            keep = {p.name for p in collection.plugins}
            for p in list(self.plugin_manager.context.get_all_stars()):
                if p.reserved:
                    continue
                if not p.name:
                    continue
                if p.name in keep:
                    continue
                try:
                    await self.plugin_manager.uninstall_plugin(p.name)
                    uninstalled.append({"name": p.name, "status": "ok"})
                except Exception as e:
                    logger.error(f"Uninstall plugin failed ({p.name}): {e!s}")
                    uninstall_failed.append(p.name)
                    uninstalled.append(
                        {"name": p.name, "status": "error", "message": str(e)}
                    )

        installed_results: list[dict[str, Any]] = []
        failed_results: list[dict[str, Any]] = []
        skipped_results: list[dict[str, Any]] = []

        sem = asyncio.Semaphore(3)

        async def _install_one(name: str, repo: str):
            async with sem:
                try:
                    await self.plugin_manager.install_plugin(repo, options.proxy)
                    return {
                        "name": name,
                        "status": "ok",
                        "message": "installed",
                        "exported_version_note": (
                            "Recorded for reference only; collection import does not lock plugin version."
                        ),
                    }
                except Exception as e:
                    return {"name": name, "status": "error", "message": str(e)}

        tasks = []
        for p in collection.plugins:
            if options.import_mode == "add" and p.name in installed_before:
                skipped_results.append({"name": p.name, "reason": "already_installed"})
                continue
            tasks.append(_install_one(p.name, p.repo))

        raw = await asyncio.gather(*tasks, return_exceptions=True)
        for r in raw:
            if isinstance(r, asyncio.CancelledError):
                raise r
            if isinstance(r, BaseException):
                failed_results.append(
                    {"name": "unknown", "status": "error", "message": str(r)}
                )
            elif r.get("status") == "ok":
                installed_results.append(r)
            else:
                failed_results.append(r)

        configs_applied = 0
        configs_failed: list[dict[str, str]] = []
        reload_queue: list[str] = []
        reload_failed: list[dict[str, Any]] = []
        if options.apply_configs and isinstance(collection.plugin_configs, dict):
            for plugin_name, cfg in collection.plugin_configs.items():
                if not isinstance(cfg, dict):
                    continue

                md = self.plugin_manager.context.get_registered_star(plugin_name)
                if not md or not md.config:
                    continue

                is_existing = plugin_name in installed_before

                if (
                    options.import_mode == "add"
                    and is_existing
                    and not options.overwrite_existing_configs
                ):
                    continue

                try:
                    current_cfg = dict(md.config)
                except Exception:
                    current_cfg = {}

                merged_cfg = {**current_cfg, **cfg}

                try:
                    md.config.save_config(merged_cfg)
                    configs_applied += 1
                    if plugin_name not in reload_queue:
                        reload_queue.append(plugin_name)
                except Exception as e:
                    logger.error(f"Apply config failed ({plugin_name}): {e!s}")
                    configs_failed.append({"name": plugin_name, "message": str(e)})

        for plugin_name in reload_queue:
            try:
                await self.plugin_manager.reload(plugin_name)
            except Exception as e:
                logger.error(f"Reload plugin failed ({plugin_name}): {e!s}")
                reload_failed.append({"name": plugin_name, "message": str(e)})

        priority_persisted = False
        priority_applied_in_memory = False
        priority_note = ""
        if options.apply_priority and isinstance(
            collection.handler_priority_overrides, dict
        ):
            apply_result = await PriorityCompatibility.apply_priority_overrides(
                collection.handler_priority_overrides,
            )
            priority_persisted = apply_result.persisted
            priority_applied_in_memory = apply_result.applied_in_memory
            if priority_applied_in_memory and not priority_persisted:
                priority_note = "Priority overrides could not be persisted; applied in memory only for this process."

        result: dict[str, Any] = {
            "installed": installed_results,
            "failed": failed_results,
            "skipped": skipped_results,
            "uninstalled": uninstalled,
            "uninstall_failed": uninstall_failed,
            "configs_applied": configs_applied,
            "configs_failed": configs_failed,
            "reloaded": reload_queue,
            "reload_failed": reload_failed,
            "priority_persisted": priority_persisted,
            "priority_applied_in_memory": priority_applied_in_memory,
        }
        if priority_note:
            result["priority_note"] = priority_note
        if conflict_report is not None:
            result["conflicts"] = conflict_report

        return result
