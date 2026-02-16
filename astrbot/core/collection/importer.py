from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
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
        installed = self._get_installed_names()

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

    def _get_installed_names(self) -> set[str]:
        return {p.name for p in self.plugin_manager.context.get_all_stars() if p.name}

    async def _run_install_tasks(
        self, tasks: list[Awaitable[dict[str, Any]]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        installed_results: list[dict[str, Any]] = []
        failed_results: list[dict[str, Any]] = []

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

        return installed_results, failed_results

    def _build_install_task_factory(
        self, *, proxy: str
    ) -> Callable[[str, str], Awaitable[dict[str, Any]]]:
        sem = asyncio.Semaphore(3)

        async def _install_one(name: str, repo: str) -> dict[str, Any]:
            async with sem:
                try:
                    await self.plugin_manager.install_plugin(repo, proxy)
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

        return _install_one

    async def _uninstall_for_clean_mode(
        self, *, keep_set: set[str], import_mode: str
    ) -> dict[str, Any]:
        if import_mode != "clean":
            return {"ok": [], "failed": [], "skipped": []}

        ok: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []

        for p in list(self.plugin_manager.context.get_all_stars()):
            if p.reserved:
                skipped.append(
                    {"name": p.name, "status": "skipped", "reason": "reserved"}
                )
                continue
            if not p.name:
                skipped.append(
                    {"name": p.name, "status": "skipped", "reason": "empty_name"}
                )
                continue
            if p.name in keep_set:
                skipped.append({"name": p.name, "status": "skipped", "reason": "kept"})
                continue

            try:
                await self.plugin_manager.uninstall_plugin(p.name)
                ok.append({"name": p.name, "status": "ok", "message": "uninstalled"})
            except Exception as e:
                logger.error(f"Uninstall plugin failed ({p.name}): {e!s}")
                failed.append({"name": p.name, "status": "error", "message": str(e)})

        return {"ok": ok, "failed": failed, "skipped": skipped}

    async def _install_plugins(
        self,
        collection: PluginCollection,
        *,
        options: ImportOptions,
        installed_before: set[str],
    ) -> dict[str, Any]:
        ok: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []

        install_one = self._build_install_task_factory(proxy=options.proxy)
        tasks = []
        for p in collection.plugins:
            if not p.name:
                skipped.append(
                    {"name": p.name, "status": "skipped", "reason": "empty_name"}
                )
                continue
            if options.import_mode == "add" and p.name in installed_before:
                skipped.append(
                    {"name": p.name, "status": "skipped", "reason": "already_installed"}
                )
                continue
            tasks.append(install_one(p.name, p.repo))

        installed_results, failed_results = await self._run_install_tasks(tasks)
        ok.extend(installed_results)
        failed.extend(failed_results)

        return {"ok": ok, "failed": failed, "skipped": skipped}

    async def _apply_configs(
        self,
        collection: PluginCollection,
        *,
        options: ImportOptions,
        installed_before: set[str],
    ) -> dict[str, Any]:
        if not options.apply_configs or not isinstance(collection.plugin_configs, dict):
            return {"ok": [], "failed": [], "skipped": [], "reload_queue": []}

        ok: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        reload_queue: list[str] = []

        for plugin_name, cfg in collection.plugin_configs.items():
            if not isinstance(cfg, dict):
                skipped.append(
                    {
                        "name": str(plugin_name),
                        "status": "skipped",
                        "reason": "invalid_config",
                    }
                )
                continue

            md = self.plugin_manager.context.get_registered_star(plugin_name)
            config = getattr(md, "config", None) if md is not None else None
            if config is None:
                skipped.append(
                    {"name": plugin_name, "status": "skipped", "reason": "no_config"}
                )
                continue

            is_existing = plugin_name in installed_before
            if (
                options.import_mode == "add"
                and is_existing
                and not options.overwrite_existing_configs
            ):
                skipped.append(
                    {
                        "name": plugin_name,
                        "status": "skipped",
                        "reason": "existing_config_not_overwritten",
                    }
                )
                continue

            try:
                current_cfg = dict(config)
            except Exception:
                current_cfg = {}

            merged_cfg = {**current_cfg, **cfg}

            try:
                config.save_config(merged_cfg)
                ok.append(
                    {"name": plugin_name, "status": "ok", "message": "config_applied"}
                )
                if plugin_name not in reload_queue:
                    reload_queue.append(plugin_name)
            except Exception as e:
                logger.error(f"Apply config failed ({plugin_name}): {e!s}")
                failed.append(
                    {"name": plugin_name, "status": "error", "message": str(e)}
                )

        return {
            "ok": ok,
            "failed": failed,
            "skipped": skipped,
            "reload_queue": reload_queue,
        }

    async def _reload_plugins(self, *, reload_queue: list[str]) -> dict[str, Any]:
        ok: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []

        for plugin_name in reload_queue:
            try:
                await self.plugin_manager.reload(plugin_name)
                ok.append({"name": plugin_name, "status": "ok", "message": "reloaded"})
            except Exception as e:
                logger.error(f"Reload plugin failed ({plugin_name}): {e!s}")
                failed.append(
                    {"name": plugin_name, "status": "error", "message": str(e)}
                )

        return {"ok": ok, "failed": failed}

    async def _apply_priority_overrides(
        self, collection: PluginCollection, *, options: ImportOptions
    ) -> dict[str, Any]:
        if not options.apply_priority or not isinstance(
            collection.handler_priority_overrides, dict
        ):
            return {
                "ok": [],
                "failed": [],
                "skipped": [
                    {
                        "name": "priority",
                        "status": "skipped",
                        "reason": "disabled_or_missing",
                    }
                ],
                "priority_persisted": False,
                "priority_applied_in_memory": False,
                "priority_note": "",
            }

        apply_result = await PriorityCompatibility.apply_priority_overrides(
            collection.handler_priority_overrides,
        )
        priority_note = ""
        if apply_result.applied_in_memory and not apply_result.persisted:
            priority_note = "Priority overrides could not be persisted; applied in memory only for this process."

        return {
            "ok": [{"name": "priority", "status": "ok", "message": "applied"}],
            "failed": [],
            "skipped": [],
            "priority_persisted": apply_result.persisted,
            "priority_applied_in_memory": apply_result.applied_in_memory,
            "priority_note": priority_note,
        }

    async def import_collection(
        self, collection: PluginCollection, options: ImportOptions
    ) -> dict[str, Any]:
        if options.import_mode not in {"add", "clean"}:
            raise ValueError("import_mode must be 'add' or 'clean'")

        installed_before = self._get_installed_names()

        conflict_report = await ConflictDetectionCompatibility.check_conflicts(
            [p.name for p in collection.plugins],
        )

        keep = {p.name for p in collection.plugins if p.name}
        uninstall_result = await self._uninstall_for_clean_mode(
            keep_set=keep,
            import_mode=options.import_mode,
        )

        install_result = await self._install_plugins(
            collection,
            options=options,
            installed_before=installed_before,
        )

        config_result = await self._apply_configs(
            collection,
            options=options,
            installed_before=installed_before,
        )

        reload_queue = list(config_result.get("reload_queue") or [])
        reload_result = await self._reload_plugins(reload_queue=reload_queue)

        priority_result = await self._apply_priority_overrides(
            collection,
            options=options,
        )

        uninstalled = list(uninstall_result.get("ok") or [])
        uninstall_failed = [
            i.get("name")
            for i in (uninstall_result.get("failed") or [])
            if i.get("name")
        ]

        configs_applied = len(config_result.get("ok") or [])
        configs_failed = [
            {"name": i.get("name"), "message": i.get("message")}
            for i in (config_result.get("failed") or [])
            if i.get("name")
        ]

        result: dict[str, Any] = {
            "installed": list(install_result.get("ok") or []),
            "failed": list(install_result.get("failed") or []),
            "skipped": list(install_result.get("skipped") or []),
            "uninstalled": uninstalled,
            "uninstall_failed": uninstall_failed,
            "configs_applied": configs_applied,
            "configs_failed": configs_failed,
            "reloaded": reload_queue,
            "reload_failed": [
                {"name": i.get("name"), "message": i.get("message")}
                for i in (reload_result.get("failed") or [])
                if i.get("name")
            ],
            "priority_persisted": bool(priority_result.get("priority_persisted")),
            "priority_applied_in_memory": bool(
                priority_result.get("priority_applied_in_memory")
            ),
        }

        priority_note = str(priority_result.get("priority_note") or "")
        if priority_note:
            result["priority_note"] = priority_note
        if conflict_report is not None:
            result["conflicts"] = conflict_report

        return result
