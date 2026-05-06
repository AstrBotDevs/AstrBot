import os
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from astrbot.core import logger
from astrbot.core.utils.astrbot_path import get_astrbot_plugin_path
from astrbot.core.utils.io import ensure_dir, on_error, remove_dir

from ..star.star import StarMetadata
from ..updator import RepoZipUpdator

ARCHIVE_METADATA_ROOT_DIRS = {"__MACOSX"}
ARCHIVE_METADATA_FILE_NAMES = {".DS_Store"}


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

        staging_path = self._create_extract_temp_dir(target_path)
        try:
            archive_root_dir = None
            with zipfile.ZipFile(zip_path, "r") as z:
                members = [
                    member
                    for member in z.infolist()
                    if not self._is_archive_metadata_member(member.filename)
                ]
                archive_root_dir = self._get_archive_root_dir(members)
                for member in members:
                    z.extract(member, staging_path)

            source_path = (
                staging_path / archive_root_dir if archive_root_dir else staging_path
            )
            self._move_extracted_children(source_path, target_path)
            self._remove_update_files(zip_path, staging_path)
            if not staging_path.exists():
                staging_path = None
        finally:
            if staging_path:
                self._remove_staging_path_safely(staging_path)

    @staticmethod
    def _create_extract_temp_dir(target_path: Path) -> Path:
        return Path(
            tempfile.mkdtemp(
                prefix=f".{target_path.name}.",
                suffix=".extract",
                dir=target_path.parent,
            )
        )

    def _move_extracted_children(self, source_path: Path, target_path: Path) -> None:
        for child in source_path.iterdir():
            destination = target_path / child.name
            self._remove_existing_path(destination)
            shutil.move(str(child), str(target_path))

    @staticmethod
    def _remove_update_files(zip_path: str, staging_path: Path) -> None:
        try:
            logger.info(f"Removing temporary files: {zip_path} and {staging_path}")
            shutil.rmtree(staging_path, onerror=on_error)
            os.remove(zip_path)
        except Exception:
            logger.warning(
                f"Failed to remove update files; you can manually delete {zip_path} "
                f"and {staging_path}",
            )

    @staticmethod
    def _remove_staging_path_safely(staging_path: Path) -> None:
        if not staging_path.exists():
            return
        try:
            shutil.rmtree(staging_path, onerror=on_error)
        except Exception:
            logger.warning(
                f"Failed to remove temporary extract directory; "
                f"you can manually delete {staging_path}",
            )

    @staticmethod
    def _remove_existing_path(path: Path) -> None:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path, onerror=on_error)
        elif path.exists() or path.is_symlink():
            path.unlink()

    @staticmethod
    def _get_archive_root_dir(members: list[zipfile.ZipInfo]) -> str | None:
        root_dir = None
        has_file = False
        has_root_file = False
        has_multiple_roots = False
        for member in members:
            parts = PluginUpdator._get_safe_member_parts(member.filename)
            if not parts:
                continue
            if not member.is_dir():
                has_file = True
            if len(parts) == 1 and not member.is_dir():
                has_root_file = True
                continue
            if root_dir is None:
                root_dir = parts[0]
            elif root_dir != parts[0]:
                has_multiple_roots = True
        if not has_file:
            raise ValueError("Empty plugin archive")
        if has_root_file or has_multiple_roots:
            return None
        return root_dir

    @staticmethod
    def _is_archive_metadata_member(member_name: str) -> bool:
        parts = PluginUpdator._get_safe_member_parts(member_name)
        if not parts:
            return False
        return (
            parts[0] in ARCHIVE_METADATA_ROOT_DIRS
            or parts[-1] in ARCHIVE_METADATA_FILE_NAMES
        )

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
