"""
插件的重载、启停、安装、卸载等操作。
"""

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

from astrbot.core import logger, pip_installer, sp
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.provider.register import llm_tools
from astrbot.core.utils.astrbot_path import (
    get_astrbot_config_path,
    get_astrbot_plugin_path,
)
from astrbot.core.utils.io import remove_dir

from . import StarMetadata
from .context import Context
from .filter.permission import PermissionType, PermissionTypeFilter
from .star import star_map, star_registry
from .star_handler import star_handlers_registry
from .updator import PluginUpdator

try:
    from watchfiles import PythonFilter, awatch
except ImportError:
    if os.getenv("ASTRBOT_RELOAD", "0") == "1":
        logger.warning("未安装 watchfiles，无法实现插件的热重载。")


class PluginManager:
    def __init__(self, context: Context, config: AstrBotConfig):
        self.updator = PluginUpdator()

        self.context = context
        self.context._star_manager = self

        self.config = config
        self.plugin_store_path = get_astrbot_plugin_path()
        """存储插件的路径。即 data/plugins"""
        self.plugin_config_path = get_astrbot_config_path()
        """存储插件配置的路径。data/config"""
        self.reserved_plugin_path = os.path.abspath(
            os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "../../../packages"
            )
        )
        """保留插件的路径。在 packages 目录下"""
        self.conf_schema_fname = "_conf_schema.json"
        """插件配置 Schema 文件名"""
        self._pm_lock = asyncio.Lock()
        """StarManager操作互斥锁"""

        self.failed_plugin_info = ""
        if os.getenv("ASTRBOT_RELOAD", "0") == "1":
            asyncio.create_task(self._watch_plugins_changes())

    async def _watch_plugins_changes(self):
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
            logger.error(f"插件热重载监视任务异常: {str(e)}")
            logger.error(traceback.format_exc())

    async def _handle_file_changes(self, changes):
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
                    self.reserved_plugin_path, star.root_dir_name
                )
            else:
                plugin_dir_path = os.path.join(
                    self.plugin_store_path, star.root_dir_name
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
                    os.path.join(path, d, d + ".py")
                ):
                    modules.append(
                        {
                            "pname": d,
                            "module": module_str,
                            "module_path": os.path.join(path, d, module_str),
                        }
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

    async def _check_plugin_dept_update(self, target_plugin: str = None):
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
                    logger.error(f"更新插件 {p} 的依赖失败。Code: {str(e)}")

    @staticmethod
    def _load_plugin_metadata(plugin_path: str, plugin_obj=None) -> StarMetadata:
        """v3.4.0 以前的方式载入插件元数据

        先寻找 metadata.yaml 文件，如果不存在，则使用插件对象的 info() 函数获取元数据。
        """
        metadata = None

        if not os.path.exists(plugin_path):
            raise Exception("插件不存在。")

        if os.path.exists(os.path.join(plugin_path, "metadata.yaml")):
            with open(
                os.path.join(plugin_path, "metadata.yaml"), "r", encoding="utf-8"
            ) as f:
                metadata = yaml.safe_load(f)
        elif plugin_obj:
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
                    "插件元数据信息不完整。name, desc, version, author 是必须的字段。"
                )
            metadata = StarMetadata(
                name=metadata["name"],
                author=metadata["author"],
                desc=metadata["desc"],
                version=metadata["version"],
                repo=metadata["repo"] if "repo" in metadata else None,
            )

        return metadata

    @staticmethod
    def _get_plugin_related_modules(
        plugin_root_dir: str, is_reserved: bool = False
    ) -> list[str]:
        """获取与指定插件相关的所有已加载模块名

        根据插件根目录名和是否为保留插件，从 sys.modules 中筛选出相关的模块名

        Args:
            plugin_root_dir: 插件根目录名
            is_reserved: 是否是保留插件，影响模块路径前缀

        Returns:
            list[str]: 与该插件相关的模块名列表
        """
        prefix = "packages." if is_reserved else "data.plugins."
        return [
            key
            for key in list(sys.modules.keys())
            if key.startswith(f"{prefix}{plugin_root_dir}")
        ]

    def _purge_modules(
        self,
        module_patterns: list[str] = None,
        root_dir_name: str = None,
        is_reserved: bool = False,
    ):
        """从 sys.modules 中移除指定的模块

        可以基于模块名模式或插件目录名移除模块，用于清理插件相关的模块缓存

        Args:
            module_patterns: 要移除的模块名模式列表（例如 ["data.plugins", "packages"]）
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
                root_dir_name, is_reserved
            ):
                try:
                    del sys.modules[module_name]
                    logger.debug(f"删除模块 {module_name}")
                except KeyError:
                    logger.warning(f"模块 {module_name} 未载入")

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
                            f"插件 {smd.name} 未被正常终止: {str(e)}, 可能会导致该插件运行不正常。"
                        )

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
                            f"插件 {smd.name} 未被正常终止: {str(e)}, 可能会导致该插件运行不正常。"
                        )

                    await self._unbind_plugin(smd.name, specified_module_path)

            result = await self.load(specified_module_path)

            # 更新所有插件的平台兼容性
            await self.update_all_platform_compatibility()

            return result

    async def update_all_platform_compatibility(self):
        """更新所有插件的平台兼容性设置"""
        # 获取最新的平台插件启用配置
        plugin_enable_config = self.config.get("platform_settings", {}).get(
            "plugin_enable", {}
        )
        logger.debug(
            f"更新所有插件的平台兼容性设置，平台数量: {len(plugin_enable_config)}"
        )

        # 遍历所有插件，更新平台兼容性
        for plugin in self.context.get_all_stars():
            plugin.update_platform_compatibility(plugin_enable_config)
            logger.debug(
                f"插件 {plugin.name} 支持的平台: {list(plugin.supported_platforms.keys())}"
            )

        return True

    async def load(self, specified_module_path=None, specified_dir_name=None):
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
        inactivated_plugins: list = sp.get("inactivated_plugins", [])
        inactivated_llm_tools: list = sp.get("inactivated_llm_tools", [])

        alter_cmd = sp.get("alter_cmd", {})

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
                    "reserved", False
                )  # 是否是保留插件。目前在 packages/ 目录下的都是保留插件。保留插件不可以卸载。

                path = "data.plugins." if not reserved else "packages."
                path += root_dir_name + "." + module_str

                # 检查是否需要载入指定的插件
                if specified_module_path and path != specified_module_path:
                    continue
                if specified_dir_name and root_dir_name != specified_dir_name:
                    continue

                logger.info(f"正在载入插件 {root_dir_name} ...")

                # 尝试导入模块
                try:
                    module = __import__(path, fromlist=[module_str])
                except (ModuleNotFoundError, ImportError):
                    # 尝试安装依赖
                    await self._check_plugin_dept_update(target_plugin=root_dir_name)
                    module = __import__(path, fromlist=[module_str])
                except Exception as e:
                    logger.error(traceback.format_exc())
                    logger.error(f"插件 {root_dir_name} 导入失败。原因：{str(e)}")
                    continue

                # 检查 _conf_schema.json
                plugin_config = None
                plugin_dir_path = (
                    os.path.join(self.plugin_store_path, root_dir_name)
                    if not reserved
                    else os.path.join(self.reserved_plugin_path, root_dir_name)
                )
                plugin_schema_path = os.path.join(
                    plugin_dir_path, self.conf_schema_fname
                )
                if os.path.exists(plugin_schema_path):
                    # 加载插件配置
                    with open(plugin_schema_path, "r", encoding="utf-8") as f:
                        plugin_config = AstrBotConfig(
                            config_path=os.path.join(
                                self.plugin_config_path, f"{root_dir_name}_config.json"
                            ),
                            schema=json.loads(f.read()),
                        )

                if path in star_map:
                    # 通过__init__subclass__注册插件
                    metadata = star_map[path]

                    try:
                        # yaml 文件的元数据优先
                        metadata_yaml = self._load_plugin_metadata(
                            plugin_path=plugin_dir_path
                        )
                        if metadata_yaml:
                            metadata.name = metadata_yaml.name
                            metadata.author = metadata_yaml.author
                            metadata.desc = metadata_yaml.desc
                            metadata.version = metadata_yaml.version
                            metadata.repo = metadata_yaml.repo
                    except Exception as e:
                        logger.error(
                            f"插件 {root_dir_name} 元数据载入失败: {str(e)}。使用默认元数据。"
                        )
                    metadata.config = plugin_config
                    if path not in inactivated_plugins:
                        # 只有没有禁用插件时才实例化插件类
                        if plugin_config:
                            # metadata.config = plugin_config
                            try:
                                metadata.star_cls = metadata.star_cls_type(
                                    context=self.context, config=plugin_config
                                )
                            except TypeError as _:
                                metadata.star_cls = metadata.star_cls_type(
                                    context=self.context
                                )
                        else:
                            metadata.star_cls = metadata.star_cls_type(
                                context=self.context
                            )
                    else:
                        logger.info(f"插件 {metadata.name} 已被禁用。")

                    metadata.module = module
                    metadata.root_dir_name = root_dir_name
                    metadata.reserved = reserved

                    # 更新插件的平台兼容性
                    plugin_enable_config = self.config.get("platform_settings", {}).get(
                        "plugin_enable", {}
                    )
                    metadata.update_platform_compatibility(plugin_enable_config)

                    # 绑定 handler
                    related_handlers = (
                        star_handlers_registry.get_handlers_by_module_name(
                            metadata.module_path
                        )
                    )
                    for handler in related_handlers:
                        handler.handler = functools.partial(
                            handler.handler, metadata.star_cls
                        )
                    # 绑定 llm_tool handler
                    for func_tool in llm_tools.func_list:
                        if (
                            func_tool.handler
                            and func_tool.handler.__module__ == metadata.module_path
                        ):
                            func_tool.handler_module_path = metadata.module_path
                            func_tool.handler = functools.partial(
                                func_tool.handler, metadata.star_cls
                            )
                        if func_tool.name in inactivated_llm_tools:
                            func_tool.active = False

                else:
                    # v3.4.0 以前的方式注册插件
                    logger.debug(
                        f"插件 {path} 未通过装饰器注册。尝试通过旧版本方式载入。"
                    )
                    classes = self._get_classes(module)

                    if path not in inactivated_plugins:
                        # 只有没有禁用插件时才实例化插件类
                        if plugin_config:
                            try:
                                obj = getattr(module, classes[0])(
                                    context=self.context, config=plugin_config
                                )  # 实例化插件类
                            except TypeError as _:
                                obj = getattr(module, classes[0])(
                                    context=self.context
                                )  # 实例化插件类
                        else:
                            obj = getattr(module, classes[0])(
                                context=self.context
                            )  # 实例化插件类
                    else:
                        logger.info(f"插件 {metadata.name} 已被禁用。")

                    metadata = None
                    metadata = self._load_plugin_metadata(
                        plugin_path=plugin_dir_path, plugin_obj=obj
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

                full_names = []
                for handler in star_handlers_registry.get_handlers_by_module_name(
                    metadata.module_path
                ):
                    full_names.append(handler.handler_full_name)

                    # 检查并且植入自定义的权限过滤器（alter_cmd）
                    if (
                        metadata.name in alter_cmd
                        and handler.handler_name in alter_cmd[metadata.name]
                    ):
                        cmd_type = alter_cmd[metadata.name][handler.handler_name].get(
                            "permission", "member"
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
                                    else PermissionType.MEMBER
                                )
                            )

                        logger.debug(
                            f"插入权限过滤器 {cmd_type} 到 {metadata.name} 的 {handler.handler_name} 方法。"
                        )

                metadata.star_handler_full_names = full_names

                # 执行 initialize() 方法
                if hasattr(metadata.star_cls, "initialize"):
                    await metadata.star_cls.initialize()

            except BaseException as e:
                logger.error(f"----- 插件 {root_dir_name} 载入失败 -----")
                errors = traceback.format_exc()
                for line in errors.split("\n"):
                    logger.error(f"| {line}")
                logger.error("----------------------------------")
                fail_rec += f"加载 {root_dir_name} 插件时出现问题，原因 {str(e)}。\n"

        # 清除 pip.main 导致的多余的 logging handlers
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)

        if not fail_rec:
            return True, None
        else:
            self.failed_plugin_info = fail_rec
            return False, fail_rec

    async def install_plugin(self, repo_url: str, proxy=""):
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
        async with self._pm_lock:
            plugin_path = await self.updator.install(repo_url, proxy)
            # reload the plugin
            dir_name = os.path.basename(plugin_path)
            await self.load(specified_dir_name=dir_name)

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
                    with open(readme_path, "r", encoding="utf-8") as f:
                        readme_content = f.read()
                except Exception as e:
                    logger.warning(f"读取插件 {dir_name} 的 README.md 文件失败: {str(e)}")

            plugin_info = None
            if plugin:
                plugin_info = {
                    "repo": plugin.repo,
                    "readme": readme_content,
                    "name": plugin.name,
                }

            return plugin_info

    async def uninstall_plugin(self, plugin_name: str):
        """卸载指定的插件。

        Args:
            plugin_name (str): 要卸载的插件名称

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
                    f"插件 {plugin_name} 未被正常终止 {str(e)}, 可能会导致资源泄露等问题。"
                )

            # 从 star_registry 和 star_map 中删除
            await self._unbind_plugin(plugin_name, plugin.module_path)

            try:
                remove_dir(os.path.join(ppath, root_dir_name))
            except Exception as e:
                raise Exception(
                    f"移除插件成功，但是删除插件文件夹失败: {str(e)}。您可以手动删除该文件夹，位于 addons/plugins/ 下。"
                )

    async def _unbind_plugin(self, plugin_name: str, plugin_module_path: str):
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
            plugin_module_path
        ):
            logger.info(
                f"移除了插件 {plugin_name} 的处理函数 {handler.handler_name} ({len(star_handlers_registry)})"
            )
            star_handlers_registry.remove(handler)

        for k in [
            k
            for k in star_handlers_registry.star_handlers_map
            if k.startswith(plugin_module_path)
        ]:
            del star_handlers_registry.star_handlers_map[k]

        self._purge_modules(
            root_dir_name=plugin.root_dir_name, is_reserved=plugin.reserved
        )

    async def update_plugin(self, plugin_name: str, proxy=""):
        """升级一个插件"""
        plugin = self.context.get_registered_star(plugin_name)
        if not plugin:
            raise Exception("插件不存在。")
        if plugin.reserved:
            raise Exception("该插件是 AstrBot 保留插件，无法更新。")

        await self.updator.update(plugin, proxy=proxy)
        await self.reload(plugin_name)

    async def turn_off_plugin(self, plugin_name: str):
        """
        禁用一个插件。
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
            inactivated_plugins: list = sp.get("inactivated_plugins", [])
            if plugin.module_path not in inactivated_plugins:
                inactivated_plugins.append(plugin.module_path)

            inactivated_llm_tools: list = list(
                set(sp.get("inactivated_llm_tools", []))
            )  # 后向兼容

            # 禁用插件启用的 llm_tool
            for func_tool in llm_tools.func_list:
                if func_tool.handler_module_path == plugin.module_path:
                    func_tool.active = False
                    if func_tool.name not in inactivated_llm_tools:
                        inactivated_llm_tools.append(func_tool.name)

            sp.put("inactivated_plugins", inactivated_plugins)
            sp.put("inactivated_llm_tools", inactivated_llm_tools)

            plugin.activated = False

    @staticmethod
    async def _terminate_plugin(star_metadata: StarMetadata):
        """终止插件，调用插件的 terminate() 和 __del__() 方法"""
        logger.info(f"正在终止插件 {star_metadata.name} ...")

        if not star_metadata.activated:
            # 说明之前已经被禁用了
            logger.debug(f"插件 {star_metadata.name} 未被激活，不需要终止，跳过。")
            return

        if hasattr(star_metadata.star_cls, "__del__"):
            asyncio.get_event_loop().run_in_executor(
                None, star_metadata.star_cls.__del__
            )
        elif hasattr(star_metadata.star_cls, "terminate"):
            await star_metadata.star_cls.terminate()

    async def turn_on_plugin(self, plugin_name: str):
        plugin = self.context.get_registered_star(plugin_name)
        inactivated_plugins: list = sp.get("inactivated_plugins", [])
        inactivated_llm_tools: list = sp.get("inactivated_llm_tools", [])
        if plugin.module_path in inactivated_plugins:
            inactivated_plugins.remove(plugin.module_path)
        sp.put("inactivated_plugins", inactivated_plugins)

        # 启用插件启用的 llm_tool
        for func_tool in llm_tools.func_list:
            if (
                func_tool.handler_module_path == plugin.module_path
                and func_tool.name in inactivated_llm_tools
            ):
                inactivated_llm_tools.remove(func_tool.name)
                func_tool.active = True
        sp.put("inactivated_llm_tools", inactivated_llm_tools)

        await self.reload(plugin_name)

        # plugin.activated = True

    async def install_plugin_from_file(self, zip_file_path: str):
        dir_name = os.path.basename(zip_file_path).replace(".zip", "")
        dir_name = dir_name.removesuffix("-master").removesuffix("-main").lower()
        desti_dir = os.path.join(self.plugin_store_path, dir_name)
        self.updator.unzip_file(zip_file_path, desti_dir)

        # remove the zip
        try:
            os.remove(zip_file_path)
        except BaseException as e:
            logger.warning(f"删除插件压缩包失败: {str(e)}")
        # await self.reload()
        await self.load(specified_dir_name=dir_name)

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
                with open(readme_path, "r", encoding="utf-8") as f:
                    readme_content = f.read()
            except Exception as e:
                logger.warning(f"读取插件 {dir_name} 的 README.md 文件失败: {str(e)}")

        plugin_info = None
        if plugin:
            plugin_info = {
                "repo": plugin.repo,
                "readme": readme_content,
                "name": plugin.name,
            }

        return plugin_info
