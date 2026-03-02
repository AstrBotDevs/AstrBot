import traceback

from quart import request

from astrbot.core import logger
from astrbot.core.agent.mcp_client import MCPTool
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.star import star_map

from .route import Response, Route, RouteContext

DEFAULT_MCP_CONFIG = {"mcpServers": {}}


class ToolsRoute(Route):
    def __init__(
        self,
        context: RouteContext,
        core_lifecycle: AstrBotCoreLifecycle,
    ) -> None:
        super().__init__(context)
        self.core_lifecycle = core_lifecycle
        self.routes = {
            "/tools/mcp/servers": ("GET", self.get_mcp_servers),
            "/tools/mcp/add": ("POST", self.add_mcp_server),
            "/tools/mcp/update": ("POST", self.update_mcp_server),
            "/tools/mcp/delete": ("POST", self.delete_mcp_server),
            "/tools/mcp/test": ("POST", self.test_mcp_connection),
            "/tools/list": ("GET", self.get_tool_list),
            "/tools/toggle-tool": ("POST", self.toggle_tool),
            "/tools/mcp/sync-provider": ("POST", self.sync_provider),
        }
        self.register_routes()
        self.tool_mgr = self.core_lifecycle.provider_manager.llm_tools

    async def get_mcp_servers(self):
        try:
            config = self.tool_mgr.load_mcp_config()
            servers = []

            # 获取所有服务器并添加它们的工具列表
            for name, server_config in config["mcpServers"].items():
                server_info = {
                    "name": name,
                    "active": server_config.get("active", True),
                }

                # 复制所有配置字段
                for key, value in server_config.items():
                    if key != "active":  # active 已经处理
                        server_info[key] = value

                # 如果MCP客户端已初始化，从客户端获取工具名称
                for name_key, runtime in self.tool_mgr.mcp_server_runtime_view.items():
                    if name_key == name:
                        mcp_client = runtime.client
                        server_info["tools"] = [tool.name for tool in mcp_client.tools]
                        server_info["errlogs"] = mcp_client.server_errlogs
                        break
                else:
                    server_info["tools"] = []

                servers.append(server_info)

            return Response().ok(servers).__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(f"获取 MCP 服务器列表失败: {e!s}").__dict__

    async def add_mcp_server(self):
        try:
            server_data = await request.json

            name = server_data.get("name", "")

            # 检查必填字段
            if not name:
                return Response().error("服务器名称不能为空").__dict__

            # 移除特殊字段并检查配置是否有效
            has_valid_config = False
            server_config = {"active": server_data.get("active", True)}

            # 复制所有配置字段
            for key, value in server_data.items():
                if key not in ["name", "active", "tools", "errlogs"]:  # 排除特殊字段
                    if key == "mcpServers":
                        key_0 = list(server_data["mcpServers"].keys())[
                            0
                        ]  # 不考虑为空的情况
                        server_config = server_data["mcpServers"][key_0]
                    else:
                        server_config[key] = value
                    has_valid_config = True

            if not has_valid_config:
                return Response().error("必须提供有效的服务器配置").__dict__

            config = self.tool_mgr.load_mcp_config()

            if name in config["mcpServers"]:
                return Response().error(f"服务器 {name} 已存在").__dict__

            config["mcpServers"][name] = server_config

            if self.tool_mgr.save_mcp_config(config):
                try:
                    await self.tool_mgr.enable_mcp_server(
                        name,
                        server_config,
                        timeout=30,
                    )
                except TimeoutError:
                    return Response().error(f"启用 MCP 服务器 {name} 超时。").__dict__
                except Exception as e:
                    logger.error(traceback.format_exc())
                    return (
                        Response().error(f"启用 MCP 服务器 {name} 失败: {e!s}").__dict__
                    )
                return Response().ok(None, f"成功添加 MCP 服务器 {name}").__dict__
            return Response().error("保存配置失败").__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(f"添加 MCP 服务器失败: {e!s}").__dict__

    async def update_mcp_server(self):
        try:
            server_data = await request.json

            name = server_data.get("name", "")
            old_name = server_data.get("oldName") or name

            if not name:
                return Response().error("服务器名称不能为空").__dict__

            config = self.tool_mgr.load_mcp_config()

            if old_name not in config["mcpServers"]:
                return Response().error(f"服务器 {old_name} 不存在").__dict__

            is_rename = name != old_name

            if name in config["mcpServers"] and is_rename:
                return Response().error(f"服务器 {name} 已存在").__dict__

            # 获取活动状态
            active = server_data.get(
                "active",
                config["mcpServers"][old_name].get("active", True),
            )

            # 创建新的配置对象
            server_config = {"active": active}

            # 仅更新活动状态的特殊处理
            only_update_active = True

            # 复制所有配置字段
            for key, value in server_data.items():
                if key not in [
                    "name",
                    "active",
                    "tools",
                    "errlogs",
                    "oldName",
                ]:  # 排除特殊字段
                    if key == "mcpServers":
                        key_0 = list(server_data["mcpServers"].keys())[
                            0
                        ]  # 不考虑为空的情况
                        server_config = server_data["mcpServers"][key_0]
                    else:
                        server_config[key] = value
                    only_update_active = False

            # 如果只更新活动状态，保留原始配置
            if only_update_active:
                for key, value in config["mcpServers"][old_name].items():
                    if key != "active":  # 除了active之外的所有字段都保留
                        server_config[key] = value

            # config["mcpServers"][name] = server_config
            if is_rename:
                config["mcpServers"].pop(old_name)
                config["mcpServers"][name] = server_config
            else:
                config["mcpServers"][name] = server_config

            if self.tool_mgr.save_mcp_config(config):
                # 处理MCP客户端状态变化
                if active:
                    if (
                        old_name in self.tool_mgr.mcp_server_runtime_view
                        or not only_update_active
                        or is_rename
                    ):
                        try:
                            await self.tool_mgr.disable_mcp_server(old_name, timeout=10)
                        except TimeoutError as e:
                            return (
                                Response()
                                .error(
                                    f"启用前停用 MCP 服务器时 {old_name} 超时: {e!s}"
                                )
                                .__dict__
                            )
                        except Exception as e:
                            logger.error(traceback.format_exc())
                            return (
                                Response()
                                .error(
                                    f"启用前停用 MCP 服务器时 {old_name} 失败: {e!s}"
                                )
                                .__dict__
                            )
                    try:
                        await self.tool_mgr.enable_mcp_server(
                            name,
                            config["mcpServers"][name],
                            timeout=30,
                        )
                    except TimeoutError:
                        return (
                            Response().error(f"启用 MCP 服务器 {name} 超时。").__dict__
                        )
                    except Exception as e:
                        logger.error(traceback.format_exc())
                        return (
                            Response()
                            .error(f"启用 MCP 服务器 {name} 失败: {e!s}")
                            .__dict__
                        )
                # 如果要停用服务器
                elif old_name in self.tool_mgr.mcp_server_runtime_view:
                    try:
                        await self.tool_mgr.disable_mcp_server(old_name, timeout=10)
                    except TimeoutError:
                        return (
                            Response()
                            .error(f"停用 MCP 服务器 {old_name} 超时。")
                            .__dict__
                        )
                    except Exception as e:
                        logger.error(traceback.format_exc())
                        return (
                            Response()
                            .error(f"停用 MCP 服务器 {old_name} 失败: {e!s}")
                            .__dict__
                        )

                return Response().ok(None, f"成功更新 MCP 服务器 {name}").__dict__
            return Response().error("保存配置失败").__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(f"更新 MCP 服务器失败: {e!s}").__dict__

    async def delete_mcp_server(self):
        try:
            server_data = await request.json
            name = server_data.get("name", "")

            if not name:
                return Response().error("服务器名称不能为空").__dict__

            config = self.tool_mgr.load_mcp_config()

            if name not in config["mcpServers"]:
                return Response().error(f"服务器 {name} 不存在").__dict__

            del config["mcpServers"][name]

            if self.tool_mgr.save_mcp_config(config):
                if name in self.tool_mgr.mcp_server_runtime_view:
                    try:
                        await self.tool_mgr.disable_mcp_server(name, timeout=10)
                    except TimeoutError:
                        return (
                            Response().error(f"停用 MCP 服务器 {name} 超时。").__dict__
                        )
                    except Exception as e:
                        logger.error(traceback.format_exc())
                        return (
                            Response()
                            .error(f"停用 MCP 服务器 {name} 失败: {e!s}")
                            .__dict__
                        )
                return Response().ok(None, f"成功删除 MCP 服务器 {name}").__dict__
            return Response().error("保存配置失败").__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(f"删除 MCP 服务器失败: {e!s}").__dict__

    async def test_mcp_connection(self):
        """测试 MCP 服务器连接"""
        try:
            server_data = await request.json
            config = server_data.get("mcp_server_config", None)

            if not isinstance(config, dict) or not config:
                return Response().error("无效的 MCP 服务器配置").__dict__

            if "mcpServers" in config:
                keys = list(config["mcpServers"].keys())
                if not keys:
                    return Response().error("MCP 服务器配置不能为空").__dict__
                if len(keys) > 1:
                    return Response().error("一次只能配置一个 MCP 服务器配置").__dict__
                config = config["mcpServers"][keys[0]]
            elif not config:
                return Response().error("MCP 服务器配置不能为空").__dict__

            tools_name = await self.tool_mgr.test_mcp_server_connection(config)
            return (
                Response().ok(data=tools_name, message="🎉 MCP 服务器可用！").__dict__
            )

        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(f"测试 MCP 连接失败: {e!s}").__dict__

    async def get_tool_list(self):
        """获取所有注册的工具列表"""
        try:
            tools = self.tool_mgr.func_list
            tools_dict = []
            for tool in tools:
                if isinstance(tool, MCPTool):
                    origin = "mcp"
                    origin_name = tool.mcp_server_name
                elif tool.handler_module_path and star_map.get(
                    tool.handler_module_path
                ):
                    star = star_map[tool.handler_module_path]
                    origin = "plugin"
                    origin_name = star.name
                else:
                    origin = "unknown"
                    origin_name = "unknown"

                tool_info = {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                    "active": tool.active,
                    "origin": origin,
                    "origin_name": origin_name,
                }
                tools_dict.append(tool_info)
            return Response().ok(data=tools_dict).__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(f"获取工具列表失败: {e!s}").__dict__

    async def toggle_tool(self):
        """启用或停用指定的工具"""
        try:
            data = await request.json
            tool_name = data.get("name")
            action = data.get("activate")  # True or False

            if not tool_name or action is None:
                return Response().error("缺少必要参数: name 或 action").__dict__

            if action:
                try:
                    ok = self.tool_mgr.activate_llm_tool(tool_name, star_map=star_map)
                except ValueError as e:
                    return Response().error(f"启用工具失败: {e!s}").__dict__
            else:
                ok = self.tool_mgr.deactivate_llm_tool(tool_name)

            if ok:
                return Response().ok(None, "操作成功。").__dict__
            return Response().error(f"工具 {tool_name} 不存在或操作失败。").__dict__

        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(f"操作工具失败: {e!s}").__dict__

    async def sync_provider(self):
        """同步 MCP 提供者配置"""
        try:
            data = await request.json
            provider_name = data.get("name")  # modelscope, or others
            match provider_name:
                case "modelscope":
                    access_token = data.get("access_token", "")
                    await self.tool_mgr.sync_modelscope_mcp_servers(access_token)
                case _:
                    return Response().error(f"未知: {provider_name}").__dict__

            return Response().ok(message="同步成功").__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(f"同步失败: {e!s}").__dict__
