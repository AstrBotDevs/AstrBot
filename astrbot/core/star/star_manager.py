"""插件的重载、启停、安装、卸载等操作。"""

import asyncio
import functools
import inspect
import json
import logging
import os
import sys
import traceback
from types import ModuleType

import yaml
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from astrbot.core import logger, pip_installer, sp
from astrbot.core.agent.handoff import FunctionTool, HandoffTool
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.config.default import VERSION
from astrbot.core.platform.register import unregister_platform_adapters_by_module
from astrbot.core.provider.register import llm_tools
from astrbot.core.utils.astrbot_path import (
    get_astrbot_config_path,
    get_astrbot_path,
    get_astrbot_plugin_path,
)
from astrbot.core.utils.io import remove_dir
from astrbot.core.utils.metrics import Metric

from . import StarMetadata
from .command_management import sync_command_configs
from .context import Context
from .filter.permission import PermissionType, PermissionTypeFilter
from .star import star_map, star_registry
from .star_handler import EventType, star_handlers_registry
from .updator import PluginUpdator

try:
    from watchfiles import PythonFilter, awatch
except ImportError:
    if os.getenv("ASTRBOT_RELOAD", "0") == "1":
        logger.warning("未安装 watchfiles，无法实现插件的热重载。")


class PluginVersionIncompatibleError(Exception):
    """Raised when plugin astrbot_version is incompatible with current AstrBot."""


class PluginManager:
    def __init__(self, context: Context, config: AstrBotConfig) -> None:
        from .star_tools import StarTools

        self.updator = PluginUpdator()

        self.context = context
        self.context._star_manager = self  # type: ignore
        StarTools.initialize(context)

        self.config = config
        self.plugin_store_path = get_astrbot_plugin_path()
        """存储插件的路径。即 data/plugins"""
        self.plugin_config_path = get_astrbot_config_path()
        """存储插件配置的路径。data/config"""
        self.reserved_plugin_path = os.path.join(
            get_astrbot_path(), "astrbot", "builtin_stars"
        )
        """保留插件的路径。在 astrbot/builtin_stars 目录下"""
        self.conf_schema_fname = "_conf_schema.json"
        self.logo_fname = "logo.png"
        """插件配置 Schema 文件名"""
        self._pm_lock = asyncio.Lock()
        """StarManager操作互斥锁"""

        self.failed_plugin_dict = {}
        """加载失败插件的信息，用于后续可能的热重载"""

        self.failed_plugin_info = ""
        if os.getenv("ASTRBOT_RELOAD", "0") == "1":
            asyncio.create_task(self._watch_plugins_changes())

    async def _watch_plugins_changes(self) -> None:
        """监视插件文件变化"""
        try:
            async for changes in awatch(
                self.plugin_store_path,
                self.reserved_plugin_path,
                watch_filter=PythonFilter(),
                recursive=True,
            ):
                # 处理文件变化
                await self._handle_file_changes(changes)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"插件热重载监视任务异常: {e!s}")
            logger.error(traceback.format_exc())

    async def _handle_file_changes(self, changes) -> None:
        """处理文件变化"""
        logger.info(f"检测到文件变化: {changes}")
        plugins_to_check = []

        for star in star_registry:
            if not star.activated:
                continue
            if star.root_dir_name is None:
                continue
            if star.reserved:
                plugin_dir_path = os.path.join(
                    self.reserved_plugin_path,
                    star.root_dir_name,
                )
            else:
                plugin_dir_path = os.path.join(
                    self.plugin_store_path,
                    star.root_dir_name,
                )
            plugins_to_check.append((plugin_dir_path, star.name))
        reloaded_plugins = set()
        for change in changes:
            _, file_path = change
            for plugin_dir_path, plugin_name in plugins_to_check:
                if (
                    os.path.commonpath([plugin_dir_path])
                    == os.path.commonpath([plugin_dir_path, file_path])
                    and plugin_name not in reloaded_plugins
                ):
                    logger.info(f"检测到插件 {plugin_name} 文件变化，正在重载...")
                    await self.reload(plugin_name)
                    reloaded_plugins.add(plugin_name)
                    break

    @staticmethod
    def _get_classes(arg: ModuleType):
        """获取指定模块（可以理解为一个 python 文件）下所有的类"""
        classes = []
        clsmembers = inspect.getmembers(arg, inspect.isclass)
        for name, _ in clsmembers:
            if name.lower().endswith("plugin") or name.lower() == "main":
                classes.append(name)
                break
        return classes

    @staticmethod
    def _get_modules(path):
        modules = []

        dirs = os.listdir(path)
        # 遍历文件夹，找到 main.py 或者和文件夹同名的文件
        for d in dirs:
            if os.path.isdir(os.path.join(path, d)):
                if os.path.exists(os.path.join(path, d, "main.py")):
                    module_str = "main"
                elif os.path.exists(os.path.join(path, d, d + ".py")):
                    module_str = d
                else:
                    logger.info(f"插件 {d} 未找到 main.py 或者 {d}.py，跳过。")
                    continue
                if os.path.exists(os.path.join(path, d, "main.py")) or os.path.exists(
                    os.path.join(path, d, d + ".py"),
                ):
                    modules.append(
                        {
                            "pname": d,
                            "module": module_str,
                            "module_path": os.path.join(path, d, module_str),
                        },
                    )
        return modules

    def _get_plugin_modules(self) -> list[dict]:
        plugins = []
        if os.path.exists(self.plugin_store_path):
            plugins.extend(self._get_modules(self.plugin_store_path))
        if os.path.exists(self.reserved_plugin_path):
            _p = self._get_modules(self.reserved_plugin_path)
            for p in _p:
                p["reserved"] = True
            plugins.extend(_p)
        return plugins

    async def _check_plugin_dept_update(
        self, target_plugin: str | None = None
    ) -> bool | None:
        """检查插件的依赖
        如果 target_plugin 为 None，则检查所有插件的依赖
        """
        plugin_dir = self.plugin_store_path
        if not os.path.exists(plugin_dir):
            return False
        to_update = []
        if target_plugin:
            to_update.append(target_plugin)
        else:
            for p in self.context.get_all_stars():
                to_update.append(p.root_dir_name)
        for p in to_update:
            plugin_path = os.path.join(plugin_dir, p)
            if os.path.exists(os.path.join(plugin_path, "requirements.txt")):
                pth = os.path.join(plugin_path, "requirements.txt")
                logger.info(f"正在安装插件 {p} 所需的依赖库: {pth}")
                try:
                    await pip_installer.install(requirements_path=pth)
                except Exception as e:
                    logger.error(f"更新插件 {p} 的依赖失败。Code: {e!s}")
        return True

    async def _import_plugin_with_dependency_recovery(
        self,
        path: str,
        module_str: str,
        root_dir_name: str,
        requirements_path: str,
    ) -> ModuleType:
        try:
            return __import__(path, fromlist=[module_str])
        except (ModuleNotFoundError, ImportError) as import_exc:
            if os.path.exists(requirements_path):
                try:
                    logger.info(
                        f"插件 {root_dir_name} 导入失败，尝试从已安装依赖恢复: {import_exc!s}"
                    )
                    pip_installer.prefer_installed_dependencies(
                        requirements_path=requirements_path
                    )
                    module = __import__(path, fromlist=[module_str])
                    logger.info(
                        f"插件 {root_dir_name} 已从 site-packages 恢复依赖，跳过重新安装。"
                    )
                    return module
                except Exception as recover_exc:
                    logger.info(
                        f"插件 {root_dir_name} 已安装依赖恢复失败，将重新安装依赖: {recover_exc!s}"
                    )

            await self._check_plugin_dept_update(target_plugin=root_dir_name)
            return __import__(path, fromlist=[module_str])

    @staticmethod
    def _load_plugin_metadata(plugin_path: str, plugin_obj=None) -> StarMetadata | None:
        """先寻找 metadata.yaml 文件，如果不存在，则使用插件对象的 info() 函数获取元数据。

        Notes: 旧版本 AstrBot 插件可能使用的是 info() 函数来获取元数据。
        """
        metadata = None

        if not os.path.exists(plugin_path):
            raise Exception("插件不存在。")

        if os.path.exists(os.path.join(plugin_path, "metadata.yaml")):
            with open(
                os.path.join(plugin_path, "metadata.yaml"),
                encoding="utf-8",
            ) as f:
                metadata = yaml.safe_load(f)
        elif plugin_obj and hasattr(plugin_obj, "info"):
            # 使用 info() 函数
            metadata = plugin_obj.info()

        if isinstance(metadata, dict):
            if "desc" not in metadata and "description" in metadata:
                metadata["desc"] = metadata["description"]

            if (
                "name" not in metadata
                or "desc" not in metadata
                or "version" not in metadata
                or "author" not in metadata
            ):
                raise Exception(
                    "插件元数据信息不完整。name, desc, version, author 是必须的字段。",
                )
            metadata = StarMetadata(
                name=metadata["name"],
                author=metadata["author"],
                desc=metadata["desc"],
                version=metadata["version"],
                repo=metadata["repo"] if "repo" in metadata else None,
                display_name=metadata.get("display_name", None),
                support_platforms=(
                    [
                        platform_id
                        for platform_id in metadata["support_platforms"]
                        if isinstance(platform_id, str)
                    ]
                    if isinstance(metadata.get("support_platforms"), list)
                    else []
                ),
                astrbot_version=(
                    metadata["astrbot_version"]
                    if isinstance(metadata.get("astrbot_version"), str)
                    else None
                ),
            )

        return metadata

    @staticmethod
    def _validate_astrbot_version_specifier(
        version_spec: str | None,
    ) -> tuple[bool, str | None]:
        if not version_spec:
            return True, None

        normalized_spec = version_spec.strip()
        if not normalized_spec:
            return True, None

        try:
            specifier = SpecifierSet(normalized_spec)
        except InvalidSpecifier:
            return (
                False,
                "astrbot_version 格式无效，请使用 PEP 440 版本范围格式，例如 >=4.16,<5。",
            )

        try:
            current_version = Version(VERSION)
        except InvalidVersion:
            return (
                False,
                f"AstrBot 当前版本 {VERSION} 无法被解析，无法校验插件版本范围。",
            )

        if current_version not in specifier:
            return (
                False,
                f"当前 AstrBot 版本为 {VERSION}，不满足插件要求的 astrbot_version: {normalized_spec}",
            )
        return True, None

    @staticmethod
    def _get_plugin_related_modules(
        plugin_root_dir: str,
        is_reserved: bool = False,
    ) -> list[str]:
        """获取与指定插件相关的所有已加载模块名

        根据插件根目录名和是否为保留插件，从 sys.modules 中筛选出相关的模块名

        Args:
            plugin_root_dir: 插件根目录名
            is_reserved: 是否是保留插件，影响模块路径前缀

        Returns:
            list[str]: 与该插件相关的模块名列表

        """
        prefix = "astrbot.builtin_stars." if is_reserved else "data.plugins."
        return [
            key
            for key in list(sys.modules.keys())
            if key.startswith(f"{prefix}{plugin_root_dir}")
        ]

    def _purge_modules(
        self,
        module_patterns: list[str] | None = None,
        root_dir_name: str | None = None,
        is_reserved: bool = False,
    ) -> None:
        """从 sys.modules 中移除指定的模块

        可以基于模块名模式或插件目录名移除模块，用于清理插件相关的模块缓存

        Args:
            module_patterns: 要移除的模块名模式列表（例如 ["data.plugins", "astrbot.builtin_stars"]）
            root_dir_name: 插件根目录名，用于移除与该插件相关的所有模块
            is_reserved: 插件是否为保留插件（影响模块路径前缀）

        """
        if module_patterns:
            for pattern in module_patterns:
                for key in list(sys.modules.keys()):
                    if key.startswith(pattern):
                        del sys.modules[key]
                        logger.debug(f"删除模块 {key}")

        if root_dir_name:
            for module_name in self._get_plugin_related_modules(
                root_dir_name,
                is_reserved,
            ):
                try:
                    del sys.modules[module_name]
                    logger.debug(f"删除模块 {module_name}")
                except KeyError:
                    logger.warning(f"模块 {module_name} 未载入")

    async def reload_failed_plugin(self, dir_name):
        """
        重新加载未注册（加载失败）的插件
        Args:
            dir_name (str): 要重载的特定插件名称。
        Returns:
            tuple: 返回 load() 方法的结果，包含 (success, error_message)
                - success (bool): 重载是否成功
                - error_message (str|None): 错误信息，成功时为 None
        """
        async with self._pm_lock:
            if dir_name in self.failed_plugin_dict:
                success, error = await self.load(specified_dir_name=dir_name)
                if success:
                    self.failed_plugin_dict.pop(dir_name, None)
                    if not self.failed_plugin_dict:
                        self.failed_plugin_info = ""
                    return success, None
                else:
                    return False, error
            return False, "插件不存在于失败列表中"

    async def reload(self, specified_plugin_name=None):
        """重新加载插件

        Args:
            specified_plugin_name (str, optional): 要重载的特定插件名称。
                                                 如果为 None，则重载所有插件。

        Returns:
            tuple: 返回 load() 方法的结果，包含 (success, error_message)
                - success (bool): 重载是否成功
                - error_message (str|None): 错误信息，成功时为 None

        """
        async with self._pm_lock:
            specified_module_path = None
            if specified_plugin_name:
                for smd in star_registry:
                    if smd.name == specified_plugin_name:
                        specified_module_path = smd.module_path
                        break

            # 终止插件
            if not specified_module_path:
                # 重载所有插件
                for smd in star_registry:
                    try:
                        await self._terminate_plugin(smd)
                    except Exception as e:
                        logger.warning(traceback.format_exc())
                        logger.warning(
                            f"插件 {smd.name} 未被正常终止: {e!s}, 可能会导致该插件运行不正常。",
                        )
                    if smd.name and smd.module_path:
                        await self._unbind_plugin(smd.name, smd.module_path)

                star_handlers_registry.clear()
                star_map.clear()
                star_registry.clear()
            else:
                # 只重载指定插件
                smd = star_map.get(specified_module_path)
                if smd:
                    try:
                        await self._terminate_plugin(smd)
                    except Exception as e:
                        logger.warning(traceback.format_exc())
                        logger.warning(
                            f"插件 {smd.name} 未被正常终止: {e!s}, 可能会导致该插件运行不正常。",
                        )
                    if smd.name:
                        await self._unbind_plugin(smd.name, specified_module_path)

            result = await self.load(specified_module_path)

            return result

    async def load(
        self,
        specified_module_path=None,
        specified_dir_name=None,
        ignore_version_check: bool = False,
    ):
        """载入插件。
        当 specified_module_path 或者 specified_dir_name 不为 None 时，只载入指定的插件。

        Args:
            specified_module_path (str, optional): 指定要加载的插件模块路径。例如: "data.plugins.my_plugin.main"
            specified_dir_name (str, optional): 指定要加载的插件目录名。例如: "my_plugin"

        Returns:
            tuple: (success, error_message)
                - success (bool): 是否全部加载成功
                - error_message (str|None): 错误信息，成功时为 None

        """
        inactivated_plugins = await sp.global_get("inactivated_plugins", [])
        inactivated_llm_tools = await sp.global_get("inactivated_llm_tools", [])
        alter_cmd = await sp.global_get("alter_cmd", {})

        plugin_modules = self._get_plugin_modules()
        if plugin_modules is None:
            return False, "未找到任何插件模块"

        fail_rec = ""

        # 导入插件模块，并尝试实例化插件类
        for plugin_module in plugin_modules:
            try:
                module_str = plugin_module["module"]
                # module_path = plugin_module['module_path']
                root_dir_name = plugin_module["pname"]  # 插件的目录名
                reserved = plugin_module.get(
                    "reserved",
                    False,
                )  # 是否是保留插件。目前在 astrbot/builtin_stars 目录下的都是保留插件。保留插件不可以卸载。
                plugin_dir_path = (
                    os.path.join(self.plugin_store_path, root_dir_name)
                    if not reserved
                    else os.path.join(self.reserved_plugin_path, root_dir_name)
                )
                requirements_path = os.path.join(plugin_dir_path, "requirements.txt")

                path = "data.plugins." if not reserved else "astrbot.builtin_stars."
                path += root_dir_name + "." + module_str

                # 检查是否需要载入指定的插件
                if specified_module_path and path != specified_module_path:
                    continue
                if specified_dir_name and root_dir_name != specified_dir_name:
                    continue

                logger.info(f"正在载入插件 {root_dir_name} ...")

                # 尝试导入模块
                try:
                    module = await self._import_plugin_with_dependency_recovery(
                        path=path,
                        module_str=module_str,
                        root_dir_name=root_dir_name,
                        requirements_path=requirements_path,
                    )
                except Exception as e:
                    error_trace = traceback.format_exc()
                    logger.error(error_trace)
                    logger.error(f"插件 {root_dir_name} 导入失败。原因：{e!s}")
                    fail_rec += f"加载 {root_dir_name} 插件时出现问题，原因 {e!s}。\n"
                    self.failed_plugin_dict[root_dir_name] = {
                        "error": str(e),
                        "traceback": error_trace,
                    }
                    if path in star_map:
                        logger.info("失败插件依旧在插件列表中，正在清理...")
                        metadata = star_map.pop(path)
                        if metadata in star_registry:
                            star_registry.remove(metadata)
                    continue

                # 检查 _conf_schema.json
                plugin_config = None
                plugin_schema_path = os.path.join(
                    plugin_dir_path,
                    self.conf_schema_fname,
                )
                if os.path.exists(plugin_schema_path):
                    # 加载插件配置
                    with open(plugin_schema_path, encoding="utf-8") as f:
                        plugin_config = AstrBotConfig(
                            config_path=os.path.join(
                                self.plugin_config_path,
                                f"{root_dir_name}_config.json",
                            ),
                            schema=json.loads(f.read()),
                        )
                logo_path = os.path.join(plugin_dir_path, self.logo_fname)

                if path in star_map:
                    # 通过 __init__subclass__ 注册插件
                    metadata = star_map[path]

                    try:
                        # yaml 文件的元数据优先
                        metadata_yaml = self._load_plugin_metadata(
                            plugin_path=plugin_dir_path,
                        )
                        if metadata_yaml:
                            metadata.name = metadata_yaml.name
                            metadata.author = metadata_yaml.author
                            metadata.desc = metadata_yaml.desc
                            metadata.version = metadata_yaml.version
                            metadata.repo = metadata_yaml.repo
                            metadata.display_name = metadata_yaml.display_name
                            metadata.support_platforms = metadata_yaml.support_platforms
                            metadata.astrbot_version = metadata_yaml.astrbot_version
                    except Exception as e:
                        logger.warning(
                            f"插件 {root_dir_name} 元数据载入失败: {e!s}。使用默认元数据。",
                        )

                    if not ignore_version_check:
                        is_valid, error_message = (
                            self._validate_astrbot_version_specifier(
                                metadata.astrbot_version,
                            )
                        )
                        if not is_valid:
                            raise PluginVersionIncompatibleError(
                                error_message
                                or "The plugin is not compatible with the current AstrBot version."
                            )

                    logger.info(metadata)
                    metadata.config = plugin_config
                    p_name = (metadata.name or "unknown").lower().replace("/", "_")
                    p_author = (metadata.author or "unknown").lower().replace("/", "_")
                    plugin_id = f"{p_author}/{p_name}"

                    # 在实例化前注入类属性，保证插件 __init__ 可读取这些值
                    if metadata.star_cls_type:
                        setattr(metadata.star_cls_type, "name", p_name)
                        setattr(metadata.star_cls_type, "author", p_author)
                        setattr(metadata.star_cls_type, "plugin_id", plugin_id)

                    if path not in inactivated_plugins:
                        # 只有没有禁用插件时才实例化插件类
                        if plugin_config and metadata.star_cls_type:
                            try:
                                metadata.star_cls = metadata.star_cls_type(
                                    context=self.context,
                                    config=plugin_config,
                                )
                            except TypeError as _:
                                metadata.star_cls = metadata.star_cls_type(
                                    context=self.context,
                                )
                        elif metadata.star_cls_type:
                            metadata.star_cls = metadata.star_cls_type(
                                context=self.context,
                            )

                        if metadata.star_cls:
                            setattr(metadata.star_cls, "name", p_name)
                            setattr(metadata.star_cls, "author", p_author)
                            setattr(metadata.star_cls, "plugin_id", plugin_id)
                    else:
                        logger.info(f"插件 {metadata.name} 已被禁用。")

                    metadata.module = module
                    metadata.root_dir_name = root_dir_name
                    metadata.reserved = reserved

                    assert metadata.module_path is not None, (
                        f"插件 {metadata.name} 的模块路径为空。"
                    )

                    # 绑定 handler
                    related_handlers = (
                        star_handlers_registry.get_handlers_by_module_name(
                            metadata.module_path,
                        )
                    )
                    for handler in related_handlers:
                        handler.handler = functools.partial(
                            handler.handler,
                            metadata.star_cls,  # type: ignore
                        )
                    # 绑定 llm_tool handler
                    for func_tool in llm_tools.func_list:
                        if isinstance(func_tool, HandoffTool):
                            need_apply = []
                            sub_tools = func_tool.agent.tools
                            if sub_tools:
                                for sub_tool in sub_tools:
                                    if isinstance(sub_tool, FunctionTool):
                                        need_apply.append(sub_tool)
                        else:
                            need_apply = [func_tool]

                        for ft in need_apply:
                            if (
                                ft.handler
                                and ft.handler.__module__ == metadata.module_path
                            ):
                                ft.handler_module_path = metadata.module_path
                                ft.handler = functools.partial(
                                    ft.handler,
                                    metadata.star_cls,  # type: ignore
                                )
                            if ft.name in inactivated_llm_tools:
                                ft.active = False

                else:
                    # v3.4.0 以前的方式注册插件
                    logger.debug(
                        f"插件 {path} 未通过装饰器注册。尝试通过旧版本方式载入。",
                    )
                    classes = self._get_classes(module)

                    if path not in inactivated_plugins:
                        # 只有没有禁用插件时才实例化插件类
                        if plugin_config:
                            try:
                                obj = getattr(module, classes[0])(
                                    context=self.context,
                                    config=plugin_config,
                                )  # 实例化插件类
                            except TypeError as _:
                                obj = getattr(module, classes[0])(
                                    context=self.context,
                                )  # 实例化插件类
                        else:
                            obj = getattr(module, classes[0])(
                                context=self.context,
                            )  # 实例化插件类

                    metadata = self._load_plugin_metadata(
                        plugin_path=plugin_dir_path,
                        plugin_obj=obj,
                    )
                    if not metadata:
                        raise Exception(f"无法找到插件 {plugin_dir_path} 的元数据。")

                    if not ignore_version_check:
                        is_valid, error_message = (
                            self._validate_astrbot_version_specifier(
                                metadata.astrbot_version,
                            )
                        )
                        if not is_valid:
                            raise PluginVersionIncompatibleError(
                                error_message
                                or "The plugin is not compatible with the current AstrBot version."
                            )

                    metadata.star_cls = obj
                    metadata.config = plugin_config
                    metadata.module = module
                    metadata.root_dir_name = root_dir_name
                    metadata.reserved = reserved
                    metadata.star_cls_type = obj.__class__
                    metadata.module_path = path
                    star_map[path] = metadata
                    star_registry.append(metadata)

                # 禁用/启用插件
                if metadata.module_path in inactivated_plugins:
                    metadata.activated = False

                # Plugin logo path
                if os.path.exists(logo_path):
                    metadata.logo_path = logo_path

                assert metadata.module_path, f"插件 {metadata.name} 模块路径为空"

                full_names = []
                for handler in star_handlers_registry.get_handlers_by_module_name(
                    metadata.module_path,
                ):
                    full_names.append(handler.handler_full_name)

                    # 检查并且植入自定义的权限过滤器（alter_cmd）
                    if (
                        metadata.name in alter_cmd
                        and handler.handler_name in alter_cmd[metadata.name]
                    ):
                        cmd_type = alter_cmd[metadata.name][handler.handler_name].get(
                            "permission",
                            "member",
                        )
                        found_permission_filter = False
                        for filter_ in handler.event_filters:
                            if isinstance(filter_, PermissionTypeFilter):
                                if cmd_type == "admin":
                                    filter_.permission_type = PermissionType.ADMIN
                                else:
                                    filter_.permission_type = PermissionType.MEMBER
                                found_permission_filter = True
                                break
                        if not found_permission_filter:
                            handler.event_filters.append(
                                PermissionTypeFilter(
                                    PermissionType.ADMIN
                                    if cmd_type == "admin"
                                    else PermissionType.MEMBER,
                                ),
                            )

                        logger.debug(
                            f"插入权限过滤器 {cmd_type} 到 {metadata.name} 的 {handler.handler_name} 方法。",
                        )

                metadata.star_handler_full_names = full_names

                # 执行 initialize() 方法
                if hasattr(metadata.star_cls, "initialize") and metadata.star_cls:
                    await metadata.star_cls.initialize()

                # 触发插件加载事件
                handlers = star_handlers_registry.get_handlers_by_event_type(
                    EventType.OnPluginLoadedEvent,
                )
                for handler in handlers:
                    try:
                        logger.info(
                            f"hook(on_plugin_loaded) -> {star_map[handler.handler_module_path].name} - {handler.handler_name}",
                        )
                        await handler.handler(metadata)
                    except Exception:
                        logger.error(traceback.format_exc())

            except BaseException as e:
                logger.error(f"----- 插件 {root_dir_name} 载入失败 -----")
                errors = traceback.format_exc()
                for line in errors.split("\n"):
                    logger.error(f"| {line}")
                logger.error("----------------------------------")
                fail_rec += f"加载 {root_dir_name} 插件时出现问题，原因 {e!s}。\n"
                self.failed_plugin_dict[root_dir_name] = {
                    "error": str(e),
                    "traceback": errors,
                }
                # 记录注册失败的插件名称，以便后续重载插件
                if path in star_map:
                    logger.info("失败插件依旧在插件列表中，正在清理...")
                    metadata = star_map.pop(path)
                    if metadata in star_registry:
                        star_registry.remove(metadata)

        # 清除 pip.main 导致的多余的 logging handlers
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)
        try:
            await sync_command_configs()
        except Exception as e:
            logger.error(f"同步指令配置失败: {e!s}")
            logger.error(traceback.format_exc())

        if not fail_rec:
            return True, None
        self.failed_plugin_info = fail_rec
        return False, fail_rec

    async def _cleanup_failed_plugin_install(
        self,
        dir_name: str,
        plugin_path: str,
    ) -> None:
        plugin = None
        for star in self.context.get_all_stars():
            if star.root_dir_name == dir_name:
                plugin = star
                break

        if plugin and plugin.name and plugin.module_path:
            try:
                await self._terminate_plugin(plugin)
            except Exception:
                logger.warning(traceback.format_exc())
            try:
                await self._unbind_plugin(plugin.name, plugin.module_path)
            except Exception:
                logger.warning(traceback.format_exc())

        if os.path.exists(plugin_path):
            try:
                remove_dir(plugin_path)
                logger.warning(f"已清理安装失败的插件目录: {plugin_path}")
            except Exception as e:
                logger.warning(
                    f"清理安装失败插件目录失败: {plugin_path}，原因: {e!s}",
                )

        plugin_config_path = os.path.join(
            self.plugin_config_path,
            f"{dir_name}_config.json",
        )
        if os.path.exists(plugin_config_path):
            try:
                os.remove(plugin_config_path)
                logger.warning(f"已清理安装失败插件配置: {plugin_config_path}")
            except Exception as e:
                logger.warning(
                    f"清理安装失败插件配置失败: {plugin_config_path}，原因: {e!s}",
                )

    async def install_plugin(
        self, repo_url: str, proxy: str = "", ignore_version_check: bool = False
    ):
        """从仓库 URL 安装插件

        从指定的仓库 URL 下载并安装插件，然后加载该插件到系统中

        Args:
            repo_url (str): 要安装的插件仓库 URL
            proxy (str, optional): 用于下载的代理服务器。默认为空字符串。

        Returns:
            dict | None: 安装成功时返回包含插件信息的字典:
                - repo: 插件的仓库 URL
                - readme: README.md 文件的内容(如果存在)
                如果找不到插件元数据则返回 None。

        """
        # this metric is for displaying plugins installation count in webui
        asyncio.create_task(
            Metric.upload(
                et="install_star",
                repo=repo_url,
            ),
        )

        async with self._pm_lock:
            plugin_path = ""
            dir_name = ""
            cleanup_required = False
            try:
                plugin_path = await self.updator.install(repo_url, proxy)
                cleanup_required = True

                # reload the plugin
                dir_name = os.path.basename(plugin_path)
                success, error_message = await self.load(
                    specified_dir_name=dir_name,
                    ignore_version_check=ignore_version_check,
                )
                if not success:
                    raise Exception(
                        error_message
                        or f"安装插件 {dir_name} 失败，请检查插件依赖或兼容性。"
                    )

                # Get the plugin metadata to return repo info
                plugin = self.context.get_registered_star(dir_name)
                if not plugin:
                    # Try to find by other name if directory name doesn't match plugin name
                    for star in self.context.get_all_stars():
                        if star.root_dir_name == dir_name:
                            plugin = star
                            break

                # Extract README.md content if exists
                readme_content = None
                readme_path = os.path.join(plugin_path, "README.md")
                if not os.path.exists(readme_path):
                    readme_path = os.path.join(plugin_path, "readme.md")

                if os.path.exists(readme_path):
                    try:
                        with open(readme_path, encoding="utf-8") as f:
                            readme_content = f.read()
                    except Exception as e:
                        logger.warning(
                            f"读取插件 {dir_name} 的 README.md 文件失败: {e!s}",
                        )

                plugin_info = None
                if plugin:
                    plugin_info = {
                        "repo": plugin.repo,
                        "readme": readme_content,
                        "name": plugin.name,
                    }

                return plugin_info
            except Exception:
                if cleanup_required and dir_name and plugin_path:
                    await self._cleanup_failed_plugin_install(
                        dir_name=dir_name,
                        plugin_path=plugin_path,
                    )
                raise

    async def uninstall_plugin(
        self,
        plugin_name: str,
        delete_config: bool = False,
        delete_data: bool = False,
    ) -> None:
        """卸载指定的插件。

        Args:
            plugin_name (str): 要卸载的插件名称
            delete_config (bool): 是否删除插件配置文件，默认为 False
            delete_data (bool): 是否删除插件数据，默认为 False

        Raises:
            Exception: 当插件不存在、是保留插件时，或删除插件文件夹失败时抛出异常

        """
        async with self._pm_lock:
            plugin = self.context.get_registered_star(plugin_name)
            if not plugin:
                raise Exception("插件不存在。")
            if plugin.reserved:
                raise Exception("该插件是 AstrBot 保留插件，无法卸载。")
            root_dir_name = plugin.root_dir_name
            ppath = self.plugin_store_path

            # 终止插件
            try:
                await self._terminate_plugin(plugin)
            except Exception as e:
                logger.warning(traceback.format_exc())
                logger.warning(
                    f"插件 {plugin_name} 未被正常终止 {e!s}, 可能会导致资源泄露等问题。",
                )

            # 从 star_registry 和 star_map 中删除
            if plugin.module_path is None or root_dir_name is None:
                raise Exception(f"插件 {plugin_name} 数据不完整，无法卸载。")

            await self._unbind_plugin(plugin_name, plugin.module_path)

            # 删除插件文件夹
            try:
                remove_dir(os.path.join(ppath, root_dir_name))
            except Exception as e:
                raise Exception(
                    f"移除插件成功，但是删除插件文件夹失败: {e!s}。您可以手动删除该文件夹，位于 addons/plugins/ 下。",
                )

            # 删除插件配置文件
            if delete_config and root_dir_name:
                config_file = os.path.join(
                    self.plugin_config_path,
                    f"{root_dir_name}_config.json",
                )
                if os.path.exists(config_file):
                    try:
                        os.remove(config_file)
                        logger.info(f"已删除插件 {plugin_name} 的配置文件")
                    except Exception as e:
                        logger.warning(f"删除插件配置文件失败: {e!s}")

            # 删除插件持久化数据
            # 注意：需要检查两个可能的目录名（plugin_data 和 plugins_data）
            # data/temp 目录可能被多个插件共享，不自动删除以防误删
            if delete_data and root_dir_name:
                data_base_dir = os.path.dirname(ppath)  # data/

                # 删除 data/plugin_data 下的插件持久化数据（单数形式，新版本）
                plugin_data_dir = os.path.join(
                    data_base_dir, "plugin_data", root_dir_name
                )
                if os.path.exists(plugin_data_dir):
                    try:
                        remove_dir(plugin_data_dir)
                        logger.info(
                            f"已删除插件 {plugin_name} 的持久化数据 (plugin_data)"
                        )
                    except Exception as e:
                        logger.warning(f"删除插件持久化数据失败 (plugin_data): {e!s}")

                # 删除 data/plugins_data 下的插件持久化数据（复数形式，旧版本兼容）
                plugins_data_dir = os.path.join(
                    data_base_dir, "plugins_data", root_dir_name
                )
                if os.path.exists(plugins_data_dir):
                    try:
                        remove_dir(plugins_data_dir)
                        logger.info(
                            f"已删除插件 {plugin_name} 的持久化数据 (plugins_data)"
                        )
                    except Exception as e:
                        logger.warning(f"删除插件持久化数据失败 (plugins_data): {e!s}")

    async def _unbind_plugin(self, plugin_name: str, plugin_module_path: str) -> None:
        """解绑并移除一个插件。

        Args:
            plugin_name: 要解绑的插件名称
            plugin_module_path: 插件的完整模块路径

        """
        plugin = None
        del star_map[plugin_module_path]
        for i, p in enumerate(star_registry):
            if p.name == plugin_name:
                plugin = p
                del star_registry[i]
                break
        for handler in star_handlers_registry.get_handlers_by_module_name(
            plugin_module_path,
        ):
            logger.info(
                f"移除了插件 {plugin_name} 的处理函数 {handler.handler_name} ({len(star_handlers_registry)})",
            )
            star_handlers_registry.remove(handler)

        for k in [
            k
            for k in star_handlers_registry.star_handlers_map
            if k.startswith(plugin_module_path)
        ]:
            del star_handlers_registry.star_handlers_map[k]

        # llm_tools 中移除该插件的工具函数绑定
        to_remove = []
        for func_tool in llm_tools.func_list:
            mp = func_tool.handler_module_path
            if (
                mp
                and mp.startswith(plugin_module_path)
                and not mp.endswith(("astrbot.builtin_stars", "data.plugins"))
            ):
                to_remove.append(func_tool)
        for func_tool in to_remove:
            llm_tools.func_list.remove(func_tool)

        # Unregister platform adapters registered by this plugin
        # module_path is like "data.plugins.my_plugin.main", extract prefix like "data.plugins.my_plugin"
        module_prefix = ".".join(plugin_module_path.split(".")[:-1])
        if module_prefix:
            unregistered_adapters = unregister_platform_adapters_by_module(
                module_prefix
            )
            for adapter_name in unregistered_adapters:
                logger.info(
                    f"移除了插件 {plugin_name} 的平台适配器 {adapter_name}",
                )

        if plugin is None:
            return

        self._purge_modules(
            root_dir_name=plugin.root_dir_name,
            is_reserved=plugin.reserved,
        )

    async def update_plugin(self, plugin_name: str, proxy="") -> None:
        """升级一个插件"""
        plugin = self.context.get_registered_star(plugin_name)
        if not plugin:
            raise Exception("插件不存在。")
        if plugin.reserved:
            raise Exception("该插件是 AstrBot 保留插件，无法更新。")

        await self.updator.update(plugin, proxy=proxy)
        await self.reload(plugin_name)

    async def turn_off_plugin(self, plugin_name: str) -> None:
        """禁用一个插件。
        调用插件的 terminate() 方法，
        将插件的 module_path 加入到 data/shared_preferences.json 的 inactivated_plugins 列表中。
        并且同时将插件启用的 llm_tool 禁用。
        """
        async with self._pm_lock:
            plugin = self.context.get_registered_star(plugin_name)
            if not plugin:
                raise Exception("插件不存在。")

            # 调用插件的终止方法
            await self._terminate_plugin(plugin)

            # 加入到 shared_preferences 中
            inactivated_plugins: list = await sp.global_get("inactivated_plugins", [])
            if plugin.module_path not in inactivated_plugins:
                inactivated_plugins.append(plugin.module_path)

            inactivated_llm_tools: list = list(
                set(await sp.global_get("inactivated_llm_tools", [])),
            )  # 后向兼容

            # 禁用插件启用的 llm_tool
            for func_tool in llm_tools.func_list:
                mp = func_tool.handler_module_path
                if (
                    plugin.module_path
                    and mp
                    and plugin.module_path.startswith(mp)
                    and not mp.endswith(("astrbot.builtin_stars", "data.plugins"))
                ):
                    func_tool.active = False
                    if func_tool.name not in inactivated_llm_tools:
                        inactivated_llm_tools.append(func_tool.name)

            await sp.global_put("inactivated_plugins", inactivated_plugins)
            await sp.global_put("inactivated_llm_tools", inactivated_llm_tools)

            plugin.activated = False

    @staticmethod
    async def _terminate_plugin(star_metadata: StarMetadata) -> None:
        """终止插件，调用插件的 terminate() 和 __del__() 方法"""
        logger.info(f"正在终止插件 {star_metadata.name} ...")

        if not star_metadata.activated:
            # 说明之前已经被禁用了
            logger.debug(f"插件 {star_metadata.name} 未被激活，不需要终止，跳过。")
            return

        if star_metadata.star_cls is None:
            return

        if "__del__" in star_metadata.star_cls_type.__dict__:
            asyncio.get_event_loop().run_in_executor(
                None,
                star_metadata.star_cls.__del__,
            )
        elif "terminate" in star_metadata.star_cls_type.__dict__:
            await star_metadata.star_cls.terminate()

        # 触发插件卸载事件
        handlers = star_handlers_registry.get_handlers_by_event_type(
            EventType.OnPluginUnloadedEvent,
        )
        for handler in handlers:
            try:
                logger.info(
                    f"hook(on_plugin_unloaded) -> {star_map[handler.handler_module_path].name} - {handler.handler_name}",
                )
                await handler.handler(star_metadata)
            except Exception:
                logger.error(traceback.format_exc())

    async def turn_on_plugin(self, plugin_name: str) -> None:
        plugin = self.context.get_registered_star(plugin_name)
        if plugin is None:
            raise Exception(f"插件 {plugin_name} 不存在。")
        inactivated_plugins: list = await sp.global_get("inactivated_plugins", [])
        inactivated_llm_tools: list = await sp.global_get("inactivated_llm_tools", [])
        if plugin.module_path in inactivated_plugins:
            inactivated_plugins.remove(plugin.module_path)
        await sp.global_put("inactivated_plugins", inactivated_plugins)

        # 启用插件启用的 llm_tool
        for func_tool in llm_tools.func_list:
            mp = func_tool.handler_module_path
            if (
                plugin.module_path
                and mp
                and plugin.module_path.startswith(mp)
                and not mp.endswith(("astrbot.builtin_stars", "data.plugins"))
                and func_tool.name in inactivated_llm_tools
            ):
                inactivated_llm_tools.remove(func_tool.name)
                func_tool.active = True
        await sp.global_put("inactivated_llm_tools", inactivated_llm_tools)

        await self.reload(plugin_name)

    async def install_plugin_from_file(
        self, zip_file_path: str, ignore_version_check: bool = False
    ):
        dir_name = os.path.basename(zip_file_path).replace(".zip", "")
        dir_name = dir_name.removesuffix("-master").removesuffix("-main").lower()
        desti_dir = os.path.join(self.plugin_store_path, dir_name)
        cleanup_required = False

        # 第一步：检查是否已安装同目录名的插件，先终止旧插件
        existing_plugin = None
        for star in self.context.get_all_stars():
            if star.root_dir_name == dir_name:
                existing_plugin = star
                break

        if existing_plugin:
            logger.info(f"检测到插件 {existing_plugin.name} 已安装，正在终止旧插件...")
            try:
                await self._terminate_plugin(existing_plugin)
            except Exception:
                logger.warning(traceback.format_exc())
            if existing_plugin.name and existing_plugin.module_path:
                await self._unbind_plugin(
                    existing_plugin.name, existing_plugin.module_path
                )

        try:
            self.updator.unzip_file(zip_file_path, desti_dir)
            cleanup_required = True

            # 第二步：解压后，读取新插件的 metadata.yaml，检查是否存在同名但不同目录的插件
            try:
                new_metadata = self._load_plugin_metadata(desti_dir)
                if new_metadata and new_metadata.name:
                    for star in self.context.get_all_stars():
                        if (
                            star.name == new_metadata.name
                            and star.root_dir_name != dir_name
                        ):
                            logger.warning(
                                f"检测到同名插件 {star.name} 存在于不同目录 {star.root_dir_name}，正在终止..."
                            )
                            try:
                                await self._terminate_plugin(star)
                            except Exception:
                                logger.warning(traceback.format_exc())
                            if star.name and star.module_path:
                                await self._unbind_plugin(star.name, star.module_path)
                            break  # 只处理第一个匹配的
            except Exception as e:
                logger.debug(f"读取新插件 metadata.yaml 失败，跳过同名检查: {e!s}")

            # remove the zip
            try:
                os.remove(zip_file_path)
            except BaseException as e:
                logger.warning(f"删除插件压缩包失败: {e!s}")
            # await self.reload()
            success, error_message = await self.load(
                specified_dir_name=dir_name,
                ignore_version_check=ignore_version_check,
            )
            if not success:
                raise Exception(
                    error_message
                    or f"安装插件 {dir_name} 失败，请检查插件依赖或兼容性。"
                )

            # Get the plugin metadata to return repo info
            plugin = self.context.get_registered_star(dir_name)
            if not plugin:
                # Try to find by other name if directory name doesn't match plugin name
                for star in self.context.get_all_stars():
                    if star.root_dir_name == dir_name:
                        plugin = star
                        break

            # Extract README.md content if exists
            readme_content = None
            readme_path = os.path.join(desti_dir, "README.md")
            if not os.path.exists(readme_path):
                readme_path = os.path.join(desti_dir, "readme.md")

            if os.path.exists(readme_path):
                try:
                    with open(readme_path, encoding="utf-8") as f:
                        readme_content = f.read()
                except Exception as e:
                    logger.warning(f"读取插件 {dir_name} 的 README.md 文件失败: {e!s}")

            plugin_info = None
            if plugin:
                plugin_info = {
                    "repo": plugin.repo,
                    "readme": readme_content,
                    "name": plugin.name,
                }

                if plugin.repo:
                    asyncio.create_task(
                        Metric.upload(
                            et="install_star_f",  # install star
                            repo=plugin.repo,
                        ),
                    )

            return plugin_info
        except Exception:
            if cleanup_required:
                await self._cleanup_failed_plugin_install(
                    dir_name=dir_name,
                    plugin_path=desti_dir,
                )
            raise
