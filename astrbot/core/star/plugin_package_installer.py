"""Download, stage, validate, and update plugin packages."""

from __future__ import annotations

import asyncio
import os
import tempfile
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from astrbot import logger
from astrbot.core.runtime_catalogs import RuntimeCatalogs
from astrbot.core.utils.io import remove_dir
from astrbot.core.utils.metrics import MetricsSink
from astrbot.core.utils.pip_installer import PipInstaller
from astrbot.core.utils.task_utils import create_tracked_task

from .plugin_runtime_common import ensure_plugin_requirements
from .updator import PluginUpdator

if TYPE_CHECKING:
    from astrbot.core.execution_context import CoreExecutionContext

    from .star import StarMetadata


class PluginLoaderPort(Protocol):
    """Minimal loader surface needed while staging a plugin package."""

    @staticmethod
    def plugin_dir_name_from_metadata(plugin_path: str) -> str: ...

    @staticmethod
    def load_metadata(plugin_path: str) -> StarMetadata: ...

    def record_failed_install(
        self,
        *,
        dir_name: str,
        plugin_path: str,
        error: Exception,
    ) -> None: ...


LoadPlugin = Callable[..., Awaitable[tuple[bool, str | None]]]
ReloadPlugin = Callable[[str | None], Awaitable[tuple[bool, str | None]]]


class PluginPackageInstaller:
    """Own package-file mutations for one runtime's plugin store."""

    def __init__(
        self,
        *,
        execution_context: CoreExecutionContext,
        catalogs: RuntimeCatalogs,
        pip_installer: PipInstaller,
        plugin_store_path: str,
        plugin_config_path: str,
        background_tasks: set[asyncio.Task[Any]],
        metrics: MetricsSink,
    ) -> None:
        self._execution_context = execution_context
        self._catalogs = catalogs
        self._pip_installer = pip_installer
        self._plugin_store_path = plugin_store_path
        self._plugin_config_path = plugin_config_path
        self._background_tasks = background_tasks
        self._metrics = metrics
        self._updator = PluginUpdator()

    @property
    def store_path(self) -> str:
        """Return the user-plugin root owned by this package installer."""
        return self._plugin_store_path

    @property
    def config_path(self) -> str:
        """Return the plugin configuration root owned by this installer."""
        return self._plugin_config_path

    async def ensure_requirements(
        self,
        plugin_dir_path: str,
        plugin_label: str,
    ) -> None:
        """Install the requirement set for a staged or installed plugin."""
        await ensure_plugin_requirements(
            plugin_dir_path=plugin_dir_path,
            plugin_label=plugin_label,
            pip_installer=self._pip_installer,
        )

    def prefer_installed_dependencies(self, requirements_path: str) -> None:
        """Prioritize already installed plugin dependencies during import recovery."""
        self._pip_installer.prefer_installed_dependencies(
            requirements_path=requirements_path,
        )

    @staticmethod
    def _read_plugin_info(plugin_path: str, plugin) -> dict[str, str | None] | None:
        readme_content = None
        readme_path = Path(plugin_path, "README.md")
        if not readme_path.exists():
            readme_path = Path(plugin_path, "readme.md")
        if readme_path.exists():
            try:
                readme_content = readme_path.read_text(encoding="utf-8")
            except OSError as exc:
                logger.warning("读取插件 README.md 失败 %s: %s", plugin_path, exc)
        if plugin is None:
            return None
        return {
            "repo": plugin.repo,
            "readme": readme_content,
            "name": plugin.name,
        }

    def _plugin_for_directory(self, dir_name: str):
        return next(
            (
                plugin
                for plugin in self._catalogs.plugins.all()
                if plugin.root_dir_name == dir_name
            ),
            None,
        )

    async def install_from_repository(
        self,
        *,
        repo_url: str,
        proxy: str,
        ignore_version_check: bool,
        download_url: str,
        loader: PluginLoaderPort,
        load_plugin: LoadPlugin,
    ) -> dict[str, str | None] | None:
        """Download a plugin and publish it only after loading succeeds."""
        create_tracked_task(
            self._background_tasks,
            self._metrics.upload(et="install_star", repo=repo_url),
            name="metric:install-star",
        )
        plugin_path = ""
        dir_name = ""
        try:
            _, repo_name, _ = self._updator.parse_github_url(repo_url)
            repo_name = self._updator.format_name(repo_name)
            plugin_path = os.path.join(self._plugin_store_path, repo_name)
            if os.path.exists(plugin_path):
                raise Exception(
                    f"安装失败：目录 {os.path.basename(plugin_path)} 已存在。"
                )

            if download_url:
                plugin_path = await self._updator.install(
                    repo_url,
                    proxy,
                    download_url=download_url,
                )
            else:
                plugin_path = await self._updator.install(repo_url, proxy)
            dir_name = os.path.basename(plugin_path)
            metadata_dir_name = loader.plugin_dir_name_from_metadata(plugin_path)
            target_plugin_path = os.path.join(
                self._plugin_store_path, metadata_dir_name
            )
            if target_plugin_path != plugin_path and os.path.exists(target_plugin_path):
                raise Exception(f"安装失败：目录 {metadata_dir_name} 已存在。")
            if target_plugin_path != plugin_path:
                os.rename(plugin_path, target_plugin_path)
                plugin_path = target_plugin_path
                dir_name = metadata_dir_name

            loader.load_metadata(plugin_path=plugin_path)
            await self.ensure_requirements(plugin_path, dir_name)
            success, error_message = await load_plugin(
                specified_dir_name=dir_name,
                ignore_version_check=ignore_version_check,
            )
            if not success:
                raise Exception(
                    error_message
                    or f"安装插件 {dir_name} 失败，请检查插件依赖或兼容性。"
                )
            return self._read_plugin_info(
                plugin_path, self._plugin_for_directory(dir_name)
            )
        except Exception as exc:
            loader.record_failed_install(
                dir_name=dir_name,
                plugin_path=plugin_path,
                error=exc,
            )
            if dir_name and plugin_path:
                logger.warning(
                    "安装插件 %s 失败，插件安装目录：%s", dir_name, plugin_path
                )
            raise

    async def install_from_file(
        self,
        *,
        zip_file_path: str,
        ignore_version_check: bool,
        loader: PluginLoaderPort,
        load_plugin: LoadPlugin,
    ) -> dict[str, str | None] | None:
        """Extract a plugin upload and publish it only after successful load."""
        dir_name = os.path.splitext(os.path.basename(zip_file_path))[0]
        destination = tempfile.mkdtemp(
            dir=self._plugin_store_path,
            prefix="plugin_upload_",
        )
        temporary_destination = destination
        skip_failed_tracking = False
        try:
            self._updator.unzip_file(zip_file_path, destination)
            metadata_dir_name = loader.plugin_dir_name_from_metadata(destination)
            target_plugin_path = os.path.join(
                self._plugin_store_path, metadata_dir_name
            )
            if target_plugin_path != destination and os.path.exists(target_plugin_path):
                skip_failed_tracking = True
                raise Exception(f"安装失败：目录 {metadata_dir_name} 已存在。")
            if target_plugin_path != destination:
                os.rename(destination, target_plugin_path)
                dir_name = metadata_dir_name
                destination = target_plugin_path

            try:
                os.remove(zip_file_path)
            except OSError as exc:
                logger.warning("删除插件压缩包失败: %s", exc)
            loader.load_metadata(plugin_path=destination)
            await self.ensure_requirements(destination, dir_name)
            success, error_message = await load_plugin(
                specified_dir_name=dir_name,
                ignore_version_check=ignore_version_check,
            )
            if not success:
                raise Exception(
                    error_message
                    or f"安装插件 {dir_name} 失败，请检查插件依赖或兼容性。"
                )

            plugin = self._plugin_for_directory(dir_name)
            plugin_info = self._read_plugin_info(destination, plugin)
            if plugin_info and plugin and plugin.repo:
                create_tracked_task(
                    self._background_tasks,
                    self._metrics.upload(et="install_star_f", repo=plugin.repo),
                    name="metric:install-star-success",
                )
            return plugin_info
        except Exception as exc:
            if not skip_failed_tracking:
                loader.record_failed_install(
                    dir_name=dir_name,
                    plugin_path=destination,
                    error=exc,
                )
            logger.warning("安装插件 %s 失败，插件安装目录：%s", dir_name, destination)
            raise
        finally:
            if (
                skip_failed_tracking or temporary_destination != destination
            ) and os.path.isdir(temporary_destination):
                try:
                    remove_dir(temporary_destination)
                except OSError as exc:
                    logger.warning("清理临时插件解压目录失败: %s", exc)

    async def update(
        self,
        plugin_name: str,
        *,
        proxy: str = "",
        download_url: str = "",
        repo_url: str = "",
        loader: PluginLoaderPort,
        reload_plugin: ReloadPlugin,
    ) -> None:
        """Update an installed non-bundled plugin and reload it."""
        plugin = self._catalogs.plugins.get_by_name(plugin_name)
        if not plugin:
            raise Exception("插件不存在。")
        if plugin.reserved:
            raise Exception("该插件是 AstrBot 保留插件，无法更新。")

        await self._updator.update(
            plugin,
            proxy=proxy,
            download_url=download_url,
            repo_url=repo_url,
        )
        if plugin.root_dir_name:
            plugin_dir_path = os.path.join(
                self._plugin_store_path, plugin.root_dir_name
            )
            loader.load_metadata(plugin_path=plugin_dir_path)
            await self.ensure_requirements(plugin_dir_path, plugin_name)
        await reload_plugin(plugin_name)

    async def cleanup_optional_artifacts(
        self,
        *,
        root_dir_name: str,
        plugin_label: str,
        plugin_id: str | None,
        delete_config: bool,
        delete_data: bool,
    ) -> None:
        """Delete optional configuration, files, and KV state for an uninstall."""
        if delete_config:
            config_file = os.path.join(
                self._plugin_config_path,
                f"{root_dir_name}_config.json",
            )
            if os.path.exists(config_file):
                try:
                    os.remove(config_file)
                    logger.info("已删除插件 %s 的配置文件", plugin_label)
                except OSError as exc:
                    logger.warning("删除插件配置文件失败 (%s): %s", plugin_label, exc)

        if not delete_data:
            return
        data_base_dir = os.path.dirname(self._plugin_store_path)
        for data_dir_name in ("plugin_data", "plugins_data"):
            plugin_data_dir = os.path.join(data_base_dir, data_dir_name, root_dir_name)
            if os.path.exists(plugin_data_dir):
                try:
                    remove_dir(plugin_data_dir)
                    logger.info(
                        "已删除插件 %s 的持久化数据 (%s)",
                        plugin_label,
                        data_dir_name,
                    )
                except OSError as exc:
                    logger.warning(
                        "删除插件持久化数据失败 (%s, %s): %s",
                        data_dir_name,
                        plugin_label,
                        exc,
                    )
        if plugin_id:
            try:
                await self._execution_context.database.clear_preferences(
                    "plugin",
                    plugin_id,
                )
                logger.info("已删除插件 %s 的偏好设置 (%s)", plugin_label, plugin_id)
            except Exception as exc:
                logger.warning("删除插件偏好设置失败 (%s): %s", plugin_label, exc)
