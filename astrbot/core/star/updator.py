import os
import zipfile

import yaml

from astrbot.core import logger
from astrbot.core.utils.astrbot_path import get_astrbot_plugin_path
from astrbot.core.utils.io import ensure_dir, remove_dir

from ..star.star import StarMetadata
from ..updator import RepoZipUpdator

PLUGIN_METADATA_FILENAMES = ("metadata.yaml", "metadata.yml")
PLUGIN_METADATA_REQUIRED_FIELDS = ("name", "desc", "version", "author")


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
        elif repo_url:
            await self.download_from_repo_url(plugin_path, repo_url, proxy=proxy)

        self.validate_plugin_archive(plugin_path + ".zip")
        try:
            remove_dir(plugin_path)
        except BaseException as e:
            logger.error(
                f"Failed to remove old plugin directory {plugin_path}: {e!s}; using overwrite installation.",
            )

        self.unzip_file(plugin_path + ".zip", plugin_path)

        return plugin_path

    @classmethod
    def find_plugin_metadata_entry(cls, entries: list[str]) -> str | None:
        """Find AstrBot plugin metadata in archive entries.

        Args:
            entries: Zip archive member names.

        Returns:
            The original archive entry name for plugin metadata, or None.
        """
        update_dir = cls._resolve_archive_root_dir(entries)
        portable_update_dir = os.path.normpath(update_dir).replace("\\", "/")
        if portable_update_dir == ".":
            portable_update_dir = ""

        entries_by_portable_path = {}
        for entry in entries:
            portable_entry = os.path.normpath(entry).replace("\\", "/")
            if portable_entry in ("", "."):
                continue
            entries_by_portable_path[portable_entry] = entry

        metadata_candidates = (
            [
                f"{portable_update_dir}/{filename}"
                for filename in PLUGIN_METADATA_FILENAMES
            ]
            if portable_update_dir
            else list(PLUGIN_METADATA_FILENAMES)
        )
        for candidate in metadata_candidates:
            if candidate in entries_by_portable_path:
                return entries_by_portable_path[candidate]
        return None

    @staticmethod
    def validate_plugin_metadata(metadata: object, metadata_label: str) -> None:
        """Validate AstrBot plugin metadata content.

        Args:
            metadata: Parsed metadata YAML content.
            metadata_label: Metadata filename or archive entry for error messages.

        Raises:
            ValueError: If metadata is malformed or misses required fields.
        """
        if not isinstance(metadata, dict):
            raise ValueError(f"{metadata_label} 格式错误。")

        normalized_metadata = dict(metadata)
        if "desc" not in normalized_metadata and "description" in normalized_metadata:
            normalized_metadata["desc"] = normalized_metadata["description"]

        missing_fields = [
            field
            for field in PLUGIN_METADATA_REQUIRED_FIELDS
            if field not in normalized_metadata
        ]
        if missing_fields:
            raise ValueError(
                f"{metadata_label} 中缺少必需字段: {', '.join(missing_fields)}。"
            )

        invalid_fields = [
            field
            for field in PLUGIN_METADATA_REQUIRED_FIELDS
            if not isinstance(normalized_metadata[field], str)
            or not normalized_metadata[field].strip()
        ]
        if invalid_fields:
            raise ValueError(
                f"{metadata_label} 中字段 {', '.join(invalid_fields)} 必须是非空字符串。"
            )

    @classmethod
    def inspect_plugin_archive(cls, zip_path: str) -> dict[str, object]:
        """Inspect plugin metadata in an AstrBot plugin archive.

        Args:
            zip_path: Path to the plugin archive.

        Returns:
            A dict containing the metadata entry and parsed metadata.

        Raises:
            ValueError: If the archive is not a valid AstrBot plugin.
        """
        try:
            with zipfile.ZipFile(zip_path, "r") as z:
                metadata_entry = cls.find_plugin_metadata_entry(z.namelist())
                if metadata_entry is None:
                    raise ValueError(
                        "压缩包不是合法的 AstrBot 插件：未找到 metadata.yaml 或 metadata.yml。"
                    )

                try:
                    metadata_text = z.read(metadata_entry).decode("utf-8")
                    metadata = yaml.safe_load(metadata_text)
                except UnicodeDecodeError as exc:
                    raise ValueError(f"{metadata_entry} 必须使用 UTF-8 编码。") from exc
                except yaml.YAMLError as exc:
                    raise ValueError(f"{metadata_entry} 格式错误。") from exc

                cls.validate_plugin_metadata(metadata, metadata_entry)
                return {
                    "metadata_entry": metadata_entry,
                    "metadata": metadata,
                }
        except zipfile.BadZipFile as exc:
            raise ValueError("插件压缩包格式错误。") from exc

    @classmethod
    def validate_plugin_archive(cls, zip_path: str) -> str:
        """Validate that an archive contains a valid AstrBot plugin.

        Args:
            zip_path: Path to the plugin archive.

        Returns:
            The archive entry name of the plugin metadata file.

        Raises:
            ValueError: If the archive is not a valid AstrBot plugin.
        """
        inspection = cls.inspect_plugin_archive(zip_path)
        return str(inspection["metadata_entry"])

    def unzip_file(self, zip_path: str, target_dir: str) -> None:
        self.validate_plugin_archive(zip_path)
        ensure_dir(target_dir)
        logger.info(f"Extracting archive: {zip_path}")
        with zipfile.ZipFile(zip_path, "r") as z:
            update_dir = self._resolve_archive_root_dir(z.namelist())
            z.extractall(target_dir)

        self._finalize_extracted_archive(zip_path, target_dir, update_dir)
