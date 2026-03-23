import traceback

from quart import request

from astrbot.core import logger
from astrbot.core.agent.mcp_client import MCPTool
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.star import star_map

from .route import Response, Route, RouteContext

DEFAULT_MCP_CONFIG = {"mcpServers": {}}


class EmptyMcpServersError(ValueError):
    """Raised when mcpServers is empty."""

    pass


def _extract_mcp_server_config(mcp_servers_value: object) -> dict:
    """Extract server configuration from user-submitted mcpServers field.

    Raises:
        ValueError: Invalid configuration
    """
    if not isinstance(mcp_servers_value, dict):
        raise ValueError("mcpServers must be a JSON object")
    if not mcp_servers_value:
        raise EmptyMcpServersError("mcpServers configuration cannot be empty")
    key_0 = next(iter(mcp_servers_value))
    extracted = mcp_servers_value[key_0]
    if not isinstance(extracted, dict):
        raise ValueError(
            "Invalid mcpServers format. Ensure each key in mcpServers is a server name, "
            "and each value is an object containing fields like command/url."
        )
    return extracted


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

    def _rollback_mcp_server(self, name: str) -> bool:
        try:
            rollback_config = self.tool_mgr.load_mcp_config()
            if name in rollback_config["mcpServers"]:
                rollback_config["mcpServers"].pop(name)
                return self.tool_mgr.save_mcp_config(rollback_config)
            return True
        except Exception:
            logger.error(traceback.format_exc())
            return False

    async def get_mcp_servers(self):
        try:
            config = self.tool_mgr.load_mcp_config()
            servers = []
            mcp_servers = config.get("mcpServers", {})

            if not isinstance(mcp_servers, dict):
                logger.warning(
                    f"Invalid MCP server config type: {type(mcp_servers).__name__}. Expected object/dict; skipped all MCP servers."
                )
                mcp_servers = {}

            # 获取所有服务器并添加它们的工具列表
            for name, server_config in mcp_servers.items():
                if not isinstance(server_config, dict):
                    logger.warning(
                        f"Invalid config for MCP server '{name}' (type: {type(server_config).__name__}); skipped."
                    )
                    continue

                server_info = {
                    "name": name,
                    "active": server_config.get("active", True),
                }

                # 复制所有配置字段
                for key, value in server_config.items():
                    if key != "active":  # active 已经处理
                        server_info[key] = value

                # 如果MCP客户端已初始化,从客户端获取工具名称
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
            return Response().error(f"Failed to get MCP server list: {e!s}").__dict__

    async def add_mcp_server(self):
        try:
            server_data = await request.json

            name = server_data.get("name", "")

            # 检查必填字段
            if not name:
                return Response().error("Server name cannot be empty").__dict__

            # 移除特殊字段并检查配置是否有效
            has_valid_config = False
            server_config = {"active": server_data.get("active", True)}

            # 复制所有配置字段
            for key, value in server_data.items():
                if key not in ["name", "active", "tools", "errlogs"]:  # 排除特殊字段
                    if key == "mcpServers":
                        try:
                            server_config = _extract_mcp_server_config(
                                server_data["mcpServers"]
                            )
                        except ValueError as e:
                            return Response().error(f"{e!s}").__dict__
                    else:
                        server_config[key] = value
                    has_valid_config = True

            if not has_valid_config:
                return (
                    Response()
                    .error("A valid server configuration is required")
                    .__dict__
                )

            config = self.tool_mgr.load_mcp_config()

            if name in config["mcpServers"]:
                return Response().error(f"Server {name} already exists").__dict__

            try:
                await self.tool_mgr.test_mcp_server_connection(server_config)
            except Exception as e:
                logger.error(traceback.format_exc())
                return Response().error(f"MCP connection test failed: {e!s}").__dict__

            config["mcpServers"][name] = server_config

            if self.tool_mgr.save_mcp_config(config):
                try:
                    await self.tool_mgr.enable_mcp_server(
                        name,
                        server_config,
                        init_timeout=30,
                    )
                except TimeoutError:
                    rollback_ok = self._rollback_mcp_server(name)
                    err_msg = f"Timed out while enabling MCP server {name}."
                    if not rollback_ok:
                        err_msg += " Configuration rollback failed. Please check the config manually."
                    return Response().error(err_msg).__dict__
                except Exception as e:
                    logger.error(traceback.format_exc())
                    rollback_ok = self._rollback_mcp_server(name)
                    err_msg = f"Failed to enable MCP server {name}: {e!s}"
                    if not rollback_ok:
                        err_msg += " Configuration rollback failed. Please check the config manually."
                    return Response().error(err_msg).__dict__
                return (
                    Response()
                    .ok(None, f"Successfully added MCP server {name}")
                    .__dict__
                )
            return Response().error("Failed to save configuration").__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(f"Failed to add MCP server: {e!s}").__dict__

    async def update_mcp_server(self):
        try:
            server_data = await request.json

            name = server_data.get("name", "")
            old_name = server_data.get("oldName") or name

            if not name:
                return Response().error("Server name cannot be empty").__dict__

            config = self.tool_mgr.load_mcp_config()

            if old_name not in config["mcpServers"]:
                return Response().error(f"Server {old_name} does not exist").__dict__

            is_rename = name != old_name

            if name in config["mcpServers"] and is_rename:
                return Response().error(f"Server {name} already exists").__dict__

            # 获取活动状态
            old_config = config["mcpServers"][old_name]
            if isinstance(old_config, dict):
                old_active = old_config.get("active", True)
            else:
                old_active = True
            active = server_data.get("active", old_active)

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
                        try:
                            server_config = _extract_mcp_server_config(
                                server_data["mcpServers"]
                            )
                        except ValueError as e:
                            return Response().error(f"{e!s}").__dict__
                    else:
                        server_config[key] = value
                    only_update_active = False

            # 如果只更新活动状态,保留原始配置
            if only_update_active and isinstance(old_config, dict):
                for key, value in old_config.items():
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
                            await self.tool_mgr.disable_mcp_server(old_name, shutdown_timeout=10)
                        except TimeoutError as e:
                            return (
                                Response()
                                .error(
                                    f"Timed out while disabling MCP server {old_name} before enabling: {e!s}"
                                )
                                .__dict__
                            )
                        except Exception as e:
                            logger.error(traceback.format_exc())
                            return (
                                Response()
                                .error(
                                    f"Failed to disable MCP server {old_name} before enabling: {e!s}"
                                )
                                .__dict__
                            )
                    try:
                        await self.tool_mgr.enable_mcp_server(
                            name,
                            config["mcpServers"][name],
                            init_timeout=30,
                        )
                    except TimeoutError:
                        return (
                            Response()
                            .error(f"Timed out while enabling MCP server {name}.")
                            .__dict__
                        )
                    except Exception as e:
                        logger.error(traceback.format_exc())
                        return (
                            Response()
                            .error(f"Failed to enable MCP server {name}: {e!s}")
                            .__dict__
                        )
                # 如果要停用服务器
                elif old_name in self.tool_mgr.mcp_server_runtime_view:
                    try:
                        await self.tool_mgr.disable_mcp_server(old_name, timeout=10)
                    except TimeoutError:
                        return (
                            Response()
                            .error(f"Timed out while disabling MCP server {old_name}.")
                            .__dict__
                        )
                    except Exception as e:
                        logger.error(traceback.format_exc())
                        return (
                            Response()
                            .error(f"Failed to disable MCP server {old_name}: {e!s}")
                            .__dict__
                        )

                return (
                    Response()
                    .ok(None, f"Successfully updated MCP server {name}")
                    .__dict__
                )
            return Response().error("Failed to save configuration").__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(f"Failed to update MCP server: {e!s}").__dict__

    async def delete_mcp_server(self):
        try:
            server_data = await request.json
            name = server_data.get("name", "")

            if not name:
                return Response().error("Server name cannot be empty").__dict__

            config = self.tool_mgr.load_mcp_config()

            if name not in config["mcpServers"]:
                return Response().error(f"Server {name} does not exist").__dict__

            del config["mcpServers"][name]

            if self.tool_mgr.save_mcp_config(config):
                if name in self.tool_mgr.mcp_server_runtime_view:
                    try:
                        await self.tool_mgr.disable_mcp_server(name, timeout=10)
                    except TimeoutError:
                        return (
                            Response()
                            .error(f"Timed out while disabling MCP server {name}.")
                            .__dict__
                        )
                    except Exception as e:
                        logger.error(traceback.format_exc())
                        return (
                            Response()
                            .error(f"Failed to disable MCP server {name}: {e!s}")
                            .__dict__
                        )
                return (
                    Response()
                    .ok(None, f"Successfully deleted MCP server {name}")
                    .__dict__
                )
            return Response().error("Failed to save configuration").__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(f"Failed to delete MCP server: {e!s}").__dict__

    async def test_mcp_connection(self):
        """Test MCP server connection."""
        try:
            server_data = await request.json
            config = server_data.get("mcp_server_config", None)

            if not isinstance(config, dict) or not config:
                return Response().error("Invalid MCP server configuration").__dict__

            if "mcpServers" in config:
                mcp_servers = config["mcpServers"]
                if isinstance(mcp_servers, dict) and len(mcp_servers) > 1:
                    return (
                        Response()
                        .error(
                            "Only one MCP server configuration can be tested at a time"
                        )
                        .__dict__
                    )
                try:
                    config = _extract_mcp_server_config(mcp_servers)
                except EmptyMcpServersError:
                    return (
                        Response()
                        .error("MCP server configuration cannot be empty")
                        .__dict__
                    )
                except ValueError as e:
                    return Response().error(f"{e!s}").__dict__
            elif not config:
                return (
                    Response()
                    .error("MCP server configuration cannot be empty")
                    .__dict__
                )

            tools_name = await self.tool_mgr.test_mcp_server_connection(config)
            return (
                Response()
                .ok(data=tools_name, message="🎉 MCP server is available!")
                .__dict__
            )

        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(f"Failed to test MCP connection: {e!s}").__dict__

    async def get_tool_list(self):
        """Get all registered tools."""
        try:
            tools = self.tool_mgr.func_list
            tools_dict = []
            for tool in tools:
                # Use the source field added to FunctionTool
                source = getattr(tool, "source", "plugin")

                if source == "mcp" and isinstance(tool, MCPTool):
                    origin = "mcp"
                    origin_name = tool.mcp_server_name
                elif source == "internal":
                    origin = "internal"
                    origin_name = "AstrBot"
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
                    "source": source,
                }
                tools_dict.append(tool_info)
            return Response().ok(data=tools_dict).__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(f"Failed to get tool list: {e!s}").__dict__

    async def toggle_tool(self):
        """Activate or deactivate a specified tool."""
        try:
            data = await request.json
            tool_name = data.get("name")
            action = data.get("activate")  # True or False

            if not tool_name or action is None:
                return (
                    Response()
                    .error("Missing required parameters: name or activate")
                    .__dict__
                )

            # Internal tools cannot be toggled by users
            for t in self.tool_mgr.func_list:
                if t.name == tool_name and getattr(t, "source", "") == "internal":
                    return Response().error("内置工具不支持手动启用/停用").__dict__

            if action:
                try:
                    ok = self.tool_mgr.activate_llm_tool(tool_name, star_map=star_map)
                except ValueError as e:
                    return Response().error(f"Failed to activate tool: {e!s}").__dict__
            else:
                ok = self.tool_mgr.deactivate_llm_tool(tool_name)

            if ok:
                return Response().ok(None, "Operation successful.").__dict__
            return (
                Response()
                .error(f"Tool {tool_name} does not exist or the operation failed.")
                .__dict__
            )

        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(f"Failed to operate tool: {e!s}").__dict__

    async def sync_provider(self):
        """Sync MCP provider configuration."""
        try:
            data = await request.json
            provider_name = data.get("name")  # modelscope, or others
            match provider_name:
                case "modelscope":
                    access_token = data.get("access_token", "")
                    await self.tool_mgr.sync_modelscope_mcp_servers(access_token)
                case _:
                    return (
                        Response().error(f"Unknown provider: {provider_name}").__dict__
                    )

            return Response().ok(message="Sync completed").__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(f"Sync failed: {e!s}").__dict__
