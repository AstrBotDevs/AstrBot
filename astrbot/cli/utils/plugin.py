import asyncio
import shutil
import tempfile
import uuid
from enum import StrEnum
from io import BytesIO
from pathlib import Path
from typing import TypedDict
from zipfile import ZipFile

import click
import httpx
import yaml

from astrbot.core.utils.io import extract_zip_safely
from astrbot.core.utils.outbound_http import (
    DEFAULT_PLUGIN_MARKET_URLS,
    PLUGIN_REGISTRY,
    fetch_json,
)
from astrbot.utils.version_comparator import VersionComparator


class PluginStatus(StrEnum):
    INSTALLED = "installed"
    NEED_UPDATE = "needs-update"
    NOT_INSTALLED = "not-installed"
    NOT_PUBLISHED = "unpublished"


class PluginRecord(TypedDict):
    name: str
    desc: str
    version: str
    author: str
    repo: str
    status: PluginStatus
    local_path: str | None


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


def _resolve_download_url(url: str, proxy: str | None = None) -> str:
    """Resolve the preferred archive URL for a GitHub repository.

    Args:
        url: Repository URL or direct archive URL.
        proxy: Optional GitHub URL-prefix mirror origin.

    Returns:
        The archive URL to download.
    """
    from astrbot.core.utils.outbound_http import (
        JSON_FETCH,
        validate_github_mirror_origin,
        validate_outbound_url,
    )

    if proxy:
        validate_github_mirror_origin(proxy)
    repo_namespace = url.split("/")[-2:]
    if len(repo_namespace) != 2:
        return url

    author, repo = repo_namespace
    release_url = f"https://api.github.com/repos/{author}/{repo}/releases"
    validate_outbound_url(release_url, JSON_FETCH)
    try:
        with httpx.Client(
            trust_env=False,
            follow_redirects=False,
        ) as client:
            resp = client.get(release_url)
            resp.raise_for_status()
            releases = resp.json()
    except Exception as e:
        click.echo(f"Failed to get release info: {e}. Using provided URL directly")
        return url

    if releases:
        return str(releases[0]["zipball_url"])

    click.echo(f"Downloading {author}/{repo} from default branch")
    return f"https://github.com/{author}/{repo}/archive/refs/heads/master.zip"


def _download_plugin_archive(
    download_url: str,
    proxy: str | None = None,
) -> BytesIO:
    """Download a plugin archive and return it as an in-memory ZIP stream.

    Args:
        download_url: Archive URL to fetch.
        proxy: Optional proxy prefix or HTTP proxy address.

    Returns:
        Downloaded archive bytes wrapped in ``BytesIO``.
    """
    import asyncio
    import tempfile

    from astrbot.core.utils.outbound_http import (
        PLUGIN_DOWNLOAD_URL,
        PLUGIN_REPOSITORY,
        compose_github_mirror_url,
        download_to_path,
        policy_for_github_mirror_download,
        validate_github_mirror_origin,
        validate_outbound_url,
    )

    policy = PLUGIN_DOWNLOAD_URL
    if proxy:
        mirror = validate_github_mirror_origin(proxy)
        if download_url.startswith("https://github.com/") or download_url.startswith(
            "https://codeload.github.com/"
        ):
            policy = policy_for_github_mirror_download(mirror.hostname)
            download_url = compose_github_mirror_url(proxy, download_url)
        else:
            validate_outbound_url(download_url, PLUGIN_DOWNLOAD_URL)
    else:
        try:
            validate_outbound_url(download_url, PLUGIN_REPOSITORY)
            policy = PLUGIN_REPOSITORY
        except Exception:
            validate_outbound_url(download_url, PLUGIN_DOWNLOAD_URL)

    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as handle:
        temp_path = Path(handle.name)
    try:
        try:
            asyncio.run(download_to_path(download_url, temp_path, policy))
        except Exception:
            if "archive/refs/heads/master.zip" in download_url:
                alt_url = download_url.replace("master.zip", "main.zip")
                click.echo("Branch 'master' not found, trying 'main' branch")
                asyncio.run(download_to_path(alt_url, temp_path, policy))
            else:
                raise
        return BytesIO(temp_path.read_bytes())
    finally:
        temp_path.unlink(missing_ok=True)


def get_git_repo(url: str, target_path: Path, proxy: str | None = None) -> None:
    """Download code from a Git repository and extract to the specified path.

    Args:
        url: Repository URL or direct archive URL.
        target_path: Local target directory for extracted content.
        proxy: Optional proxy prefix or HTTP proxy address.
    """
    temp_dir = Path(tempfile.mkdtemp())
    try:
        zip_content = _download_plugin_archive(
            _resolve_download_url(url, proxy),
            proxy,
        )
        with ZipFile(zip_content) as z:
            try:
                extract_zip_safely(z, temp_dir, archive_label="plugin archive")
            except ValueError as exc:
                raise click.ClickException(str(exc)) from exc
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


def _build_plugin_record(
    *,
    name: str,
    desc: str,
    version: str,
    author: str,
    repo: str,
    status: PluginStatus,
    local_path: str | None,
) -> PluginRecord:
    return {
        "name": name,
        "desc": desc,
        "version": version,
        "author": author,
        "repo": repo,
        "status": status,
        "local_path": local_path,
    }


def _load_local_plugin(plugin_dir: Path) -> PluginRecord | None:
    metadata = load_yaml_metadata(plugin_dir)
    required_keys = {"name", "desc", "version", "author", "repo"}
    if not metadata or not required_keys.issubset(metadata):
        return None

    return _build_plugin_record(
        name=str(metadata.get("name", "")),
        desc=str(metadata.get("desc", "")),
        version=str(metadata.get("version", "")),
        author=str(metadata.get("author", "")),
        repo=str(metadata.get("repo", "")),
        status=PluginStatus.INSTALLED,
        local_path=str(plugin_dir),
    )


def _fetch_online_plugins() -> dict[str, PluginRecord]:
    online_plugins: dict[str, PluginRecord] = {}
    data = None
    last_error: Exception | None = None
    for url in DEFAULT_PLUGIN_MARKET_URLS:
        try:
            payload = asyncio.run(fetch_json(url, PLUGIN_REGISTRY))
        except Exception as e:
            last_error = e
            continue
        if not isinstance(payload, dict):
            last_error = ValueError("response is not a JSON object")
            continue
        data = payload
        break
    if not isinstance(data, dict):
        click.echo(f"Failed to get online plugin list: {last_error}", err=True)
        return online_plugins

    for plugin_id, plugin_info in data.items():
        if plugin_id == "$meta" or not isinstance(plugin_info, dict):
            continue
        online_plugins[str(plugin_id)] = _build_plugin_record(
            name=str(plugin_id),
            desc=str(plugin_info.get("desc", "")),
            version=str(plugin_info.get("version", "")),
            author=str(plugin_info.get("author", "")),
            repo=str(plugin_info.get("repo", "")),
            status=PluginStatus.NOT_INSTALLED,
            local_path=None,
        )
    return online_plugins


def _get_plugin_target_paths(
    plugin: PluginRecord,
    plugins_dir: Path,
    *,
    is_update: bool,
) -> tuple[str, str, Path, Path | None]:
    plugin_name = plugin["name"]
    repo_url = plugin["repo"]
    local_path = plugin.get("local_path")
    target_path = (
        Path(local_path) if is_update and local_path else plugins_dir / plugin_name
    )
    backup_path = (
        target_path.with_name(f"{target_path.name}_backup") if is_update else None
    )
    return plugin_name, repo_url, target_path, backup_path


def _prepare_plugin_backup(target_path: Path, backup_path: Path | None) -> None:
    if backup_path is None:
        return
    if backup_path.exists():
        shutil.rmtree(backup_path)
    shutil.copytree(target_path, backup_path)


def _cleanup_plugin_backup(backup_path: Path | None) -> None:
    if backup_path is not None and backup_path.exists():
        shutil.rmtree(backup_path)


def _restore_plugin_backup(target_path: Path, backup_path: Path | None) -> None:
    if target_path.exists():
        shutil.rmtree(target_path, ignore_errors=True)
    if backup_path is not None and backup_path.exists():
        shutil.move(backup_path, target_path)


def build_plug_list(plugins_dir: Path) -> list[PluginRecord]:
    """Build plugin list containing local and online plugin information

    Args:
        plugins_dir: Plugin directory path

    Returns:
        List of dicts containing plugin information.
    """
    result: list[PluginRecord] = []
    if plugins_dir.is_dir():
        for plugin_dir in plugins_dir.iterdir():
            if not plugin_dir.is_dir():
                continue
            plugin_record = _load_local_plugin(plugin_dir)
            if plugin_record is not None:
                result.append(plugin_record)

    online_plugins_dict = _fetch_online_plugins()

    for local_plugin in result:
        plugin_name = str(local_plugin["name"])
        online_plugin = online_plugins_dict.pop(plugin_name, None)
        if online_plugin is None:
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
    plugin: PluginRecord,
    plugins_dir: Path,
    is_update: bool = False,
    proxy: str | None = None,
) -> None:
    """Install or update a plugin.

    Args:
        plugin: Plugin info dict.
        plugins_dir: Plugins directory.
        is_update: Whether this is an update operation.
        proxy: Proxy server address.
    """
    plugin_name, repo_url, target_path, backup_path = _get_plugin_target_paths(
        plugin,
        plugins_dir,
        is_update=is_update,
    )

    if is_update and not target_path.exists():
        raise click.ClickException(
            f"Plugin {plugin_name} is not installed and cannot be updated"
        )

    _prepare_plugin_backup(target_path, backup_path)

    try:
        click.echo(
            f"{'Updating' if is_update else 'Downloading'} plugin {plugin_name} from {repo_url}...",
        )
        get_git_repo(repo_url, target_path, proxy)

        _cleanup_plugin_backup(backup_path)
        click.echo(
            f"Plugin {plugin_name} {'updated' if is_update else 'installed'} successfully"
        )
    except Exception as e:
        _restore_plugin_backup(target_path, backup_path)
        raise click.ClickException(
            f"Error {'updating' if is_update else 'installing'} plugin {plugin_name}: {e}",
        )
