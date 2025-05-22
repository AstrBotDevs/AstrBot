import shutil
import tempfile

import httpx
import yaml
from enum import Enum
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import click
from .version_comparator import VersionComparator


class PluginStatus(str, Enum):
    INSTALLED = "已安装"
    NEED_UPDATE = "需更新"
    NOT_INSTALLED = "未安装"
    NOT_PUBLISHED = "未发布"


def get_git_repo(url: str, target_path: Path, proxy: str | None = None):
    """从 Git 仓库下载代码并解压到指定路径"""
    temp_dir = Path(tempfile.mkdtemp())
    try:
        # 解析仓库信息
        repo_namespace = url.split("/")[-2:]
        author = repo_namespace[0]
        repo = repo_namespace[1]

        # 尝试获取最新的 release
        release_url = f"https://api.github.com/repos/{author}/{repo}/releases"
        try:
            with httpx.Client(
                proxy=proxy if proxy else None, follow_redirects=True
            ) as client:
                resp = client.get(release_url)
                resp.raise_for_status()
                releases = resp.json()

                if releases:
                    # 使用最新的 release
                    download_url = releases[0]["zipball_url"]
                else:
                    # 没有 release，使用默认分支
                    click.echo(f"正在从默认分支下载 {author}/{repo}")
                    download_url = f"https://github.com/{author}/{repo}/archive/refs/heads/master.zip"
        except Exception as e:
            click.echo(f"获取 release 信息失败: {e}，将直接使用提供的 URL")
            download_url = url

        # 应用代理
        if proxy:
            download_url = f"{proxy}/{download_url}"

        # 下载并解压
        with httpx.Client(
            proxy=proxy if proxy else None, follow_redirects=True
        ) as client:
            resp = client.get(download_url)
            if (
                resp.status_code == 404
                and "archive/refs/heads/master.zip" in download_url
            ):
                alt_url = download_url.replace("master.zip", "main.zip")
                click.echo("master 分支不存在，尝试下载 main 分支")
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
    """从 metadata.yaml 文件加载插件元数据

    Args:
        plugin_dir: 插件目录路径

    Returns:
        dict: 包含元数据的字典，如果读取失败则返回空字典
    """
    yaml_path = plugin_dir / "metadata.yaml"
    if yaml_path.exists():
        try:
            return yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
        except Exception as e:
            click.echo(f"读取 {yaml_path} 失败: {e}", err=True)
    return {}


def build_plug_list(plugins_dir: Path) -> list:
    """构建插件列表，包含本地和在线插件信息

    Args:
        plugins_dir (Path): 插件目录路径

    Returns:
        list: 包含插件信息的字典列表
    """
    # 获取本地插件信息
    result = []
    if plugins_dir.exists():
        for plugin_name in [d.name for d in plugins_dir.glob("*") if d.is_dir()]:
            plugin_dir = plugins_dir / plugin_name

            # 从 metadata.yaml 加载元数据
            metadata = load_yaml_metadata(plugin_dir)

            # 如果成功加载元数据，添加到结果列表
            if metadata and all(
                k in metadata for k in ["name", "desc", "version", "author", "repo"]
            ):
                result.append({
                    "name": str(metadata.get("name", "")),
                    "desc": str(metadata.get("desc", "")),
                    "version": str(metadata.get("version", "")),
                    "author": str(metadata.get("author", "")),
                    "repo": str(metadata.get("repo", "")),
                    "status": PluginStatus.INSTALLED,
                    "local_path": str(plugin_dir),
                })

    # 获取在线插件列表
    online_plugins = []
    try:
        with httpx.Client() as client:
            resp = client.get("https://api.soulter.top/astrbot/plugins")
            resp.raise_for_status()
            data = resp.json()
            for plugin_id, plugin_info in data.items():
                online_plugins.append({
                    "name": str(plugin_id),
                    "desc": str(plugin_info.get("desc", "")),
                    "version": str(plugin_info.get("version", "")),
                    "author": str(plugin_info.get("author", "")),
                    "repo": str(plugin_info.get("repo", "")),
                    "status": PluginStatus.NOT_INSTALLED,
                    "local_path": None,
                })
    except Exception as e:
        click.echo(f"获取在线插件列表失败: {e}", err=True)

    # 与在线插件比对，更新状态
    online_plugin_names = {plugin["name"] for plugin in online_plugins}
    for local_plugin in result:
        if local_plugin["name"] in online_plugin_names:
            # 查找对应的在线插件
            online_plugin = next(
                p for p in online_plugins if p["name"] == local_plugin["name"]
            )
            if (
                VersionComparator.compare_version(
                    local_plugin["version"], online_plugin["version"]
                )
                < 0
            ):
                local_plugin["status"] = PluginStatus.NEED_UPDATE
        else:
            # 本地插件未在线上发布
            local_plugin["status"] = PluginStatus.NOT_PUBLISHED

    # 添加未安装的在线插件
    for online_plugin in online_plugins:
        if not any(plugin["name"] == online_plugin["name"] for plugin in result):
            result.append(online_plugin)

    return result


def manage_plugin(
    plugin: dict, plugins_dir: Path, is_update: bool = False, proxy: str | None = None
) -> None:
    """安装或更新插件

    Args:
        plugin (dict): 插件信息字典
        plugins_dir (Path): 插件目录
        is_update (bool, optional): 是否为更新操作. 默认为 False
        proxy (str, optional): 代理服务器地址
    """
    plugin_name = plugin["name"]
    repo_url = plugin["repo"]

    # 如果是更新且有本地路径，直接使用本地路径
    if is_update and plugin.get("local_path"):
        target_path = Path(plugin["local_path"])
    else:
        target_path = plugins_dir / plugin_name

    backup_path = Path(f"{target_path}_backup") if is_update else None

    # 检查插件是否存在
    if is_update and not target_path.exists():
        raise click.ClickException(f"插件 {plugin_name} 未安装，无法更新")

    # 备份现有插件
    if is_update and backup_path.exists():
        shutil.rmtree(backup_path)
    if is_update:
        shutil.copytree(target_path, backup_path)

    try:
        click.echo(
            f"正在从 {repo_url} {'更新' if is_update else '下载'}插件 {plugin_name}..."
        )
        get_git_repo(repo_url, target_path, proxy)

        # 更新成功，删除备份
        if is_update and backup_path.exists():
            shutil.rmtree(backup_path)
        click.echo(f"插件 {plugin_name} {'更新' if is_update else '安装'}成功")
    except Exception as e:
        if target_path.exists():
            shutil.rmtree(target_path, ignore_errors=True)
        if is_update and backup_path.exists():
            shutil.move(backup_path, target_path)
        raise click.ClickException(
            f"{'更新' if is_update else '安装'}插件 {plugin_name} 时出错: {e}"
        )
