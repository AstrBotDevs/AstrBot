import os
import shutil
import zipfile
from pathlib import Path, PurePosixPath

from astrbot.core import logger
from astrbot.core.utils.astrbot_path import get_astrbot_plugin_path
from astrbot.core.utils.io import ensure_dir, on_error, remove_dir

from ..star.star import StarMetadata
from ..updator import RepoZipUpdator


class PluginUpdator(RepoZipUpdator):
    def __init__(self, repo_mirror: str = "", verify: str | bool | None = None) -> None:
        super().__init__(repo_mirror, verify=verify)
        self.plugin_store_path = get_astrbot_plugin_path()

    def get_plugin_store_path(self) -> str:
        return self.plugin_store_path

    async def install(self, repo_url: str, proxy="", download_url: str = "") -> str:
        _, repo_name, _ = self.parse_github_url(repo_url)
        repo_name = self.format_name(repo_name)
        plugin_path = os.path.join(self.plugin_store_path, repo_name)
        if download_url:
            logger.info(f"Downloading plugin archive for {repo_name}: {download_url}")
            await self._download_file(download_url, plugin_path + ".zip")
        else:
            await self.download_from_repo_url(plugin_path, repo_url, proxy)
        self.unzip_file(plugin_path + ".zip", plugin_path)

        return plugin_path

    async def update(
        self, plugin: StarMetadata, proxy="", download_url: str = ""
    ) -> str:
        repo_url = plugin.repo

        if not repo_url and not download_url:
            raise Exception(
                f"Plugin {plugin.name} does not specify a repository URL or download URL."
            )

        if not plugin.root_dir_name:
            raise Exception(
                f"Plugin {plugin.name} does not specify a root directory name."
            )

        plugin_path = os.path.join(self.plugin_store_path, plugin.root_dir_name)

        logger.info(
            f"Updating plugin at path: {plugin_path}, repository URL: {repo_url}",
        )
        if download_url:
            logger.info(
                f"Downloading plugin update archive for {plugin.name}: {download_url}"
            )
            await self._download_file(download_url, plugin_path + ".zip")
        else:
            await self.download_from_repo_url(plugin_path, repo_url, proxy=proxy)

        try:
            remove_dir(plugin_path)
        except BaseException as e:
            logger.error(
                f"Failed to remove old plugin directory {plugin_path}: {e!s}; using overwrite installation.",
            )

        self.unzip_file(plugin_path + ".zip", plugin_path)

        return plugin_path

    def unzip_file(self, zip_path: str, target_dir: str) -> None:
        target_path = Path(target_dir)
        ensure_dir(target_path)
        logger.info(f"Extracting archive: {zip_path}")

        archive_root_dir = None
        with zipfile.ZipFile(zip_path, "r") as z:
            archive_root_dir = self._get_archive_root_dir(z.infolist())
            self._extract_archive_safely(z, target_path)

        extracted_root = target_path / archive_root_dir if archive_root_dir else None
        if extracted_root and extracted_root.is_dir():
            for child in extracted_root.iterdir():
                destination = target_path / child.name
                if destination.is_dir() and not destination.is_symlink():
                    shutil.rmtree(destination, onerror=on_error)
                elif destination.exists() or destination.is_symlink():
                    destination.unlink()
                shutil.move(str(child), str(target_path))

        try:
            logger.info(
                f"Removing temporary files: {zip_path}"
                + (f" and {extracted_root}" if extracted_root else ""),
            )
            if extracted_root and extracted_root.exists():
                shutil.rmtree(extracted_root, onerror=on_error)
            os.remove(zip_path)
        except BaseException:
            logger.warning(
                f"Failed to remove update files; you can manually delete {zip_path}"
                + (f" and {extracted_root}" if extracted_root else ""),
            )

    @classmethod
    def _get_archive_root_dir(cls, members: list[zipfile.ZipInfo]) -> str | None:
        root_dir = None
        for member in members:
            parts = cls._get_safe_member_parts(member.filename)
            if not parts or member.is_dir():
                continue
            if len(parts) == 1:
                return None
            if root_dir is None:
                root_dir = parts[0]
            elif root_dir != parts[0]:
                return None
        return root_dir

    @classmethod
    def _extract_archive_safely(
        cls, archive: zipfile.ZipFile, target_path: Path
    ) -> None:
        for member in archive.infolist():
            cls._get_safe_member_parts(member.filename)
        for member in archive.infolist():
            archive.extract(member, target_path)

    @staticmethod
    def _get_safe_member_parts(member_name: str) -> tuple[str, ...]:
        if not member_name:
            return ()
        if "\\" in member_name:
            raise ValueError(f"Unsafe path in zip archive: {member_name}")

        member_path = PurePosixPath(member_name)
        parts = tuple(part for part in member_path.parts if part)
        if (
            member_path.is_absolute()
            or any(part in {".", ".."} for part in parts)
            or any(":" in part for part in parts)
        ):
            raise ValueError(f"Unsafe path in zip archive: {member_name}")
        return parts
