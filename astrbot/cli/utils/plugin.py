import shutil
import tempfile
import uuid
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


LOCAL_PLUGIN_COPY_IGNORE = shutil.ignore_patterns(
    ".git",
    "__pycache__",
    "*.pyc",
    ".venv",
    "venv",
    ".idea",
    ".vscode",
    ".zed",
)


def _validate_plugin_dir_name(plugin_name: str, source_path: Path) -> str:
    plugin_name = plugin_name.strip()
    plugin_path = Path(plugin_name)
    has_separator = "/" in plugin_name or "\\" in plugin_name
    if (
        not plugin_name
        or plugin_name in {".", ".."}
        or plugin_path.is_absolute()
        or has_separator
        or plugin_path.name != plugin_name
    ):
        raise click.ClickException(
            f"Local plugin {source_path} metadata.yaml has invalid name: {plugin_name}"
        )
    return plugin_name


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
    if plugins_dir.is_dir():
        for plugin_dir in plugins_dir.iterdir():
            if not plugin_dir.is_dir():
                continue

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
    online_plugins_dict = {}
    try:
        with httpx.Client() as client:
            resp = client.get("https://api.soulter.top/astrbot/plugins")
            resp.raise_for_status()
            data = resp.json()
            for plugin_id, plugin_info in data.items():
                online_plugins_dict[str(plugin_id)] = {
                    "name": str(plugin_id),
                    "desc": str(plugin_info.get("desc", "")),
                    "version": str(plugin_info.get("version", "")),
                    "author": str(plugin_info.get("author", "")),
                    "repo": str(plugin_info.get("repo", "")),
                    "status": PluginStatus.NOT_INSTALLED,
                    "local_path": None,
                }
    except Exception as e:
        click.echo(f"Failed to get online plugin list: {e}", err=True)

    # Compare with online plugins and update status
    for local_plugin in result:
        online_plugin = online_plugins_dict.pop(local_plugin["name"], None)
        if online_plugin is None:
            # Local plugin is not published online
            local_plugin["status"] = PluginStatus.NOT_PUBLISHED
            continue

        if (
            VersionComparator.compare_version(
                local_plugin["version"],
                online_plugin["version"],
            )
            < 0
        ):
            local_plugin["status"] = PluginStatus.NEED_UPDATE

    # Add uninstalled online plugins
    result.extend(online_plugins_dict.values())

    return result


def _cleanup_local_plugin_target(target_path: Path) -> None:
    if target_path.is_symlink() or target_path.is_file():
        target_path.unlink(missing_ok=True)
    elif target_path.exists():
        shutil.rmtree(target_path, ignore_errors=True)


def _copy_local_plugin(source_path: Path, plugins_dir: Path, target_path: Path) -> None:
    temp_target = plugins_dir / f".{target_path.name}.tmp-{uuid.uuid4().hex}"
    try:
        shutil.copytree(source_path, temp_target, ignore=LOCAL_PLUGIN_COPY_IGNORE)
        temp_target.rename(target_path)
    except FileExistsError:
        raise click.ClickException(
            f"Plugin {target_path.name} already exists"
        ) from None
    except Exception:
        raise
    finally:
        if temp_target.exists() or temp_target.is_symlink():
            _cleanup_local_plugin_target(temp_target)


def install_local_plugin(
    source_path: Path,
    plugins_dir: Path,
    editable: bool = False,
) -> None:
    """Install a plugin from a local directory."""
    source_path = source_path.expanduser().resolve()
    plugins_dir = plugins_dir.resolve()

    if not source_path.exists() or not source_path.is_dir():
        raise click.ClickException(f"Local plugin path does not exist: {source_path}")

    metadata = load_yaml_metadata(source_path)
    plugin_name = metadata.get("name")
    if not isinstance(plugin_name, str) or not plugin_name.strip():
        raise click.ClickException(
            f"Local plugin {source_path} must contain metadata.yaml with a valid name"
        )
    plugin_name = _validate_plugin_dir_name(plugin_name, source_path)

    target_path = plugins_dir / plugin_name
    if target_path.exists():
        raise click.ClickException(f"Plugin {plugin_name} already exists")

    try:
        plugins_dir.mkdir(parents=True, exist_ok=True)
        if editable:
            try:
                target_path.symlink_to(source_path, target_is_directory=True)
            except OSError as e:
                raise click.ClickException(
                    f"Failed to create symlink for editable install: {e}. "
                    "On Windows, you may need to run as Administrator or enable Developer Mode."
                ) from e
        else:
            _copy_local_plugin(source_path, plugins_dir, target_path)
        click.echo(f"Plugin {plugin_name} installed successfully from {source_path}")
    except FileExistsError:
        raise click.ClickException(f"Plugin {plugin_name} already exists") from None
    except click.ClickException:
        raise
    except Exception as e:
        if editable and target_path.is_symlink():
            _cleanup_local_plugin_target(target_path)
        raise click.ClickException(
            f"Error installing local plugin {plugin_name}: {e}"
        ) from e


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
        raise click.ClickException(
            f"Plugin {plugin_name} is not installed and cannot be updated"
        )

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
        click.echo(
            f"Plugin {plugin_name} {'updated' if is_update else 'installed'} successfully"
        )
    except Exception as e:
        if target_path.exists():
            shutil.rmtree(target_path, ignore_errors=True)
        if is_update and backup_path is not None and backup_path.exists():
            shutil.move(backup_path, target_path)
        raise click.ClickException(
            f"Error {'updating' if is_update else 'installing'} plugin {plugin_name}: {e}",
        )
