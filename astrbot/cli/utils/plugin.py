import shutil
import tempfile
from enum import Enum
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import click
import httpx
import yaml

from .version_comparator import VersionComparator


class PluginStatus(str, Enum):
    INSTALLED = "installed"
    NEED_UPDATE = "needs-update"
    NOT_INSTALLED = "not-installed"
    NOT_PUBLISHED = "unpublished"


def get_git_repo(url: str, target_path: Path, proxy: str | None = None) -> None:
    """Download code from a Git repository and extract to the specified path"""
    temp_dir = Path(tempfile.mkdtemp())
    try:
        # Parse repository info
        repo_namespace = url.split("/")[-2:]
        author = repo_namespace[0]
        repo = repo_namespace[1]

        # Try to get the latest release
        release_url = f"https://api.github.com/repos/{author}/{repo}/releases"
        try:
            with httpx.Client(
                proxy=proxy if proxy else None,
                follow_redirects=True,
            ) as client:
                resp = client.get(release_url)
                resp.raise_for_status()
                releases = resp.json()

                if releases:
                    # Use the latest release
                    download_url = releases[0]["zipball_url"]
                else:
                    # No release found, use default branch
                    click.echo(f"Downloading {author}/{repo} from default branch")
                    download_url = f"https://github.com/{author}/{repo}/archive/refs/heads/master.zip"
        except Exception as e:
            click.echo(f"Failed to get release info: {e}. Using provided URL directly")
            download_url = url

        # Apply proxy
        if proxy:
            download_url = f"{proxy}/{download_url}"

        # Download and extract
        with httpx.Client(
            proxy=proxy if proxy else None,
            follow_redirects=True,
        ) as client:
            resp = client.get(download_url)
            if (
                resp.status_code == 404
                and "archive/refs/heads/master.zip" in download_url
            ):
                alt_url = download_url.replace("master.zip", "main.zip")
                click.echo("Branch 'master' not found, trying 'main' branch")
                resp = client.get(alt_url)
                resp.raise_for_status()
            else:
                resp.raise_for_status()
            zip_content = BytesIO(resp.content)
        with ZipFile(zip_content) as z:
            z.extractall(temp_dir)
            namelist = z.namelist()
            root_dir = Path(namelist[0]).parts[0] if namelist else ""
            if target_path.exists():
                shutil.rmtree(target_path)
            shutil.move(temp_dir / root_dir, target_path)
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


def load_yaml_metadata(plugin_dir: Path) -> dict:
    """Load plugin metadata from metadata.yaml file

    Args:
        plugin_dir: Plugin directory path

    Returns:
        dict: Dictionary containing metadata, or empty dict if loading fails

    """
    yaml_path = plugin_dir / "metadata.yaml"
    if yaml_path.exists():
        try:
            return yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
        except Exception as e:
            click.echo(f"Failed to read {yaml_path}: {e}", err=True)
    return {}


def build_plug_list(plugins_dir: Path) -> list:
    """Build plugin list containing local and online plugin information

    Args:
        plugins_dir (Path): Plugin directory path

    Returns:
        list: List of dicts containing plugin information

    """
    # Get local plugin info
    result = []
    if plugins_dir.exists():
        for plugin_name in [d.name for d in plugins_dir.glob("*") if d.is_dir()]:
            plugin_dir = plugins_dir / plugin_name

            # Load metadata from metadata.yaml
            metadata = load_yaml_metadata(plugin_dir)

            if "desc" not in metadata and "description" in metadata:
                metadata["desc"] = metadata["description"]

            # If metadata loaded successfully, add to result list
            if metadata and all(
                k in metadata for k in ["name", "desc", "version", "author", "repo"]
            ):
                result.append(
                    {
                        "name": str(metadata.get("name", "")),
                        "desc": str(metadata.get("desc", "")),
                        "version": str(metadata.get("version", "")),
                        "author": str(metadata.get("author", "")),
                        "repo": str(metadata.get("repo", "")),
                        "status": PluginStatus.INSTALLED,
                        "local_path": str(plugin_dir),
                    },
                )

    # Get online plugin list
    online_plugins = []
    try:
        with httpx.Client() as client:
            resp = client.get("https://api.soulter.top/astrbot/plugins")
            resp.raise_for_status()
            data = resp.json()
            for plugin_id, plugin_info in data.items():
                online_plugins.append(
                    {
                        "name": str(plugin_id),
                        "desc": str(plugin_info.get("desc", "")),
                        "version": str(plugin_info.get("version", "")),
                        "author": str(plugin_info.get("author", "")),
                        "repo": str(plugin_info.get("repo", "")),
                        "status": PluginStatus.NOT_INSTALLED,
                        "local_path": None,
                    },
                )
    except Exception as e:
        click.echo(f"Failed to get online plugin list: {e}", err=True)

    # Compare with online plugins and update status
    online_plugin_names = {plugin["name"] for plugin in online_plugins}
    for local_plugin in result:
        if local_plugin["name"] in online_plugin_names:
            # Find the corresponding online plugin
            online_plugin = next(
                p for p in online_plugins if p["name"] == local_plugin["name"]
            )
            if (
                VersionComparator.compare_version(
                    local_plugin["version"],
                    online_plugin["version"],
                )
                < 0
            ):
                local_plugin["status"] = PluginStatus.NEED_UPDATE
        else:
            # Local plugin is not published online
            local_plugin["status"] = PluginStatus.NOT_PUBLISHED

    # Add uninstalled online plugins
    for online_plugin in online_plugins:
        if not any(plugin["name"] == online_plugin["name"] for plugin in result):
            result.append(online_plugin)

    return result


def manage_plugin(
    plugin: dict,
    plugins_dir: Path,
    is_update: bool = False,
    proxy: str | None = None,
) -> None:
    """Install or update a plugin

    Args:
        plugin (dict): Plugin info dict
        plugins_dir (Path): Plugins directory
        is_update (bool, optional): Whether this is an update operation. Defaults to False
        proxy (str, optional): Proxy server address

    """
    plugin_name = plugin["name"]
    repo_url = plugin["repo"]

    # If updating and local path exists, use it directly
    if is_update and plugin.get("local_path"):
        target_path = Path(plugin["local_path"])
    else:
        target_path = plugins_dir / plugin_name

    backup_path = Path(f"{target_path}_backup") if is_update else None

    # Check if plugin exists
    if is_update and not target_path.exists():
        raise click.ClickException(f"Plugin {plugin_name} is not installed and cannot be updated")

    # Backup existing plugin
    if is_update and backup_path is not None and backup_path.exists():
        shutil.rmtree(backup_path)
    if is_update and backup_path is not None:
        shutil.copytree(target_path, backup_path)

    try:
        click.echo(
            f"{'Updating' if is_update else 'Downloading'} plugin {plugin_name} from {repo_url}...",
        )
        get_git_repo(repo_url, target_path, proxy)

        # Update succeeded, delete backup
        if is_update and backup_path is not None and backup_path.exists():
            shutil.rmtree(backup_path)
        click.echo(f"Plugin {plugin_name} {'updated' if is_update else 'installed'} successfully")
    except Exception as e:
        if target_path.exists():
            shutil.rmtree(target_path, ignore_errors=True)
        if is_update and backup_path is not None and backup_path.exists():
            shutil.move(backup_path, target_path)
        raise click.ClickException(
            f"Error {'updating' if is_update else 'installing'} plugin {plugin_name}: {e}",
        )
