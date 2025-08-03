import traceback
from typing import List, Dict, Any

from .route import Route, Response, RouteContext
from astrbot.core import logger
from quart import request
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.star.star_handler import star_handlers_registry, StarHandlerMetadata
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.filter.command_group import CommandGroupFilter
from astrbot.core.star.filter.permission import PermissionTypeFilter
from astrbot.core.star.star import star_map
from astrbot.core import DEMO_MODE
from astrbot.core.utils.shared_preferences import SharedPreferences


class CommandPermissionRoute(Route):
    def __init__(
        self,
        context: RouteContext,
        core_lifecycle: AstrBotCoreLifecycle,
    ) -> None:
        super().__init__(context)
        self.routes = {
            "/command_permission/get": ("GET", self.get_command_permissions),
            "/command_permission/set": ("POST", self.set_command_permission),
            "/command_permission/get_commands": ("GET", self.get_all_commands),
        }
        self.core_lifecycle = core_lifecycle
        self.register_routes()

    async def get_command_permissions(self) -> Response:
        """获取所有指令的权限配置"""
        try:
            sp = SharedPreferences()
            alter_cmd_cfg = sp.get("alter_cmd", {})
            
            # 构建权限配置列表
            permissions = []
            
            # 遍历所有插件的权限配置
            for plugin_name, plugin_config in alter_cmd_cfg.items():
                for command_name, config in plugin_config.items():
                    permission_type = config.get("permission", "member")
                    permissions.append({
                        "plugin_name": plugin_name,
                        "command_name": command_name,
                        "permission": permission_type,
                        "id": f"{plugin_name}.{command_name}"
                    })
            
            return Response().ok({"permissions": permissions}).__dict__
        except Exception:
            logger.error(f"/api/command_permission/get: {traceback.format_exc()}")
            return Response().error("获取指令权限配置失败").__dict__

    async def get_all_commands(self) -> Response:
        """获取所有可用的指令列表"""
        try:
            commands = []
            
            # 遍历所有注册的处理器
            for handler in star_handlers_registry:
                assert isinstance(handler, StarHandlerMetadata)
                plugin = star_map.get(handler.handler_module_path)
                
                if not plugin:
                    continue
                
                # 查找指令过滤器
                for filter_ in handler.event_filters:
                    if isinstance(filter_, CommandFilter):
                        # 检查当前权限配置
                        sp = SharedPreferences()
                        alter_cmd_cfg = sp.get("alter_cmd", {})
                        current_permission = "member"  # 默认权限
                        
                        if (plugin.name in alter_cmd_cfg and 
                            handler.handler_name in alter_cmd_cfg[plugin.name]):
                            current_permission = alter_cmd_cfg[plugin.name][handler.handler_name].get("permission", "member")
                        
                        # 检查是否有默认的权限过滤器
                        has_default_admin = False
                        for f in handler.event_filters:
                            if isinstance(f, PermissionTypeFilter):
                                if f.permission_type.name == "ADMIN":
                                    has_default_admin = True
                                    if current_permission == "member":
                                        current_permission = "admin"
                                break
                        
                        commands.append({
                            "command_name": filter_.command_name,
                            "plugin_name": plugin.name,
                            "handler_name": handler.handler_name,
                            "description": getattr(handler, 'description', ''),
                            "current_permission": current_permission,
                            "has_default_admin": has_default_admin,
                            "id": f"{plugin.name}.{handler.handler_name}"
                        })
                    elif isinstance(filter_, CommandGroupFilter):
                        # 处理指令组
                        sp = SharedPreferences()
                        alter_cmd_cfg = sp.get("alter_cmd", {})
                        current_permission = "member"
                        
                        if (plugin.name in alter_cmd_cfg and 
                            handler.handler_name in alter_cmd_cfg[plugin.name]):
                            current_permission = alter_cmd_cfg[plugin.name][handler.handler_name].get("permission", "member")
                        
                        has_default_admin = False
                        for f in handler.event_filters:
                            if isinstance(f, PermissionTypeFilter):
                                if f.permission_type.name == "ADMIN":
                                    has_default_admin = True
                                    if current_permission == "member":
                                        current_permission = "admin"
                                break
                        
                        commands.append({
                            "command_name": filter_.group_name,
                            "plugin_name": plugin.name,
                            "handler_name": handler.handler_name,
                            "description": getattr(handler, 'description', ''),
                            "current_permission": current_permission,
                            "has_default_admin": has_default_admin,
                            "is_group": True,
                            "id": f"{plugin.name}.{handler.handler_name}"
                        })
            
            return Response().ok({"commands": commands}).__dict__
        except Exception:
            logger.error(f"/api/command_permission/get_commands: {traceback.format_exc()}")
            return Response().error("获取指令列表失败").__dict__

    async def set_command_permission(self) -> Response:
        """设置指令权限"""
        if DEMO_MODE:
            return Response().error("演示模式下不允许修改配置").__dict__
        
        try:
            data = await request.get_json()
            plugin_name = data.get("plugin_name")
            handler_name = data.get("handler_name")
            permission = data.get("permission")
            
            if not all([plugin_name, handler_name, permission]):
                return Response().error("参数不完整").__dict__
            
            if permission not in ["admin", "member"]:
                return Response().error("权限类型错误，只能是 admin 或 member").__dict__
            
            # 查找对应的处理器
            found_handler = None
            for handler in star_handlers_registry:
                if (handler.handler_module_path in star_map and
                    star_map[handler.handler_module_path].name == plugin_name and
                    handler.handler_name == handler_name):
                    found_handler = handler
                    break
            
            if not found_handler:
                return Response().error("未找到指定的指令处理器").__dict__
            
            # 更新配置
            sp = SharedPreferences()
            alter_cmd_cfg = sp.get("alter_cmd", {})
            
            if plugin_name not in alter_cmd_cfg:
                alter_cmd_cfg[plugin_name] = {}
            
            if handler_name not in alter_cmd_cfg[plugin_name]:
                alter_cmd_cfg[plugin_name][handler_name] = {}
            
            alter_cmd_cfg[plugin_name][handler_name]["permission"] = permission
            sp.put("alter_cmd", alter_cmd_cfg)
            
            # 动态更新权限过滤器
            found_permission_filter = False
            for filter_ in found_handler.event_filters:
                if isinstance(filter_, PermissionTypeFilter):
                    from astrbot.core.star.filter.permission import PermissionType
                    if permission == "admin":
                        filter_.permission_type = PermissionType.ADMIN
                    else:
                        filter_.permission_type = PermissionType.MEMBER
                    found_permission_filter = True
                    break
            
            if not found_permission_filter:
                # 如果没有权限过滤器，则添加一个
                from astrbot.core.star.filter.permission import PermissionType
                new_filter = PermissionTypeFilter(
                    PermissionType.ADMIN if permission == "admin" else PermissionType.MEMBER
                )
                found_handler.event_filters.insert(0, new_filter)
            
            return Response().ok({"message": f"已将 {handler_name} 权限设置为 {permission}"}).__dict__
            
        except Exception:
            logger.error(f"/api/command_permission/set: {traceback.format_exc()}")
            return Response().error("设置指令权限失败").__dict__