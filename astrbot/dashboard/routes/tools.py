import traceback
from typing import Any

from quart import request

from astrbot.core import logger
from astrbot.core.agent.mcp_client import MCPTool
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.star import star_map

from .route import Response, Route, RouteContext

DEFAULT_MCP_CONFIG: dict[str, Any] = {"mcpServers": {}}


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
    extracted = list(mcp_servers_value.values())[0]
    if not isinstance(extracted, dict):
        raise ValueError(
            "Invalid mcpServers format. Ensure each key in mcpServers is a server name, and each value is an object containing fields like command/url."
        )
    return extracted


class ToolsRoute(Route):
    def __init__(
        self, context: RouteContext, core_lifecycle: AstrBotCoreLifecycle
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
        provider_mgr = self.core_lifecycle.provider_manager
        if provider_mgr is None:
            raise RuntimeError("Provider manager not initialized")
        self.tool_mgr = provider_mgr.llm_tools

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
                for key, value in server_config.items():
                    if key != "active":
                        server_info[key] = value
                for name_key, runtime in self.tool_mgr.mcp_server_runtime_view.items():
                    if name_key == name:
                        mcp_client = runtime.client
                        server_info["tools"] = [tool.name for tool in mcp_client.tools]
                        server_info["errlogs"] = mcp_client.server_errlogs
                        break
                else:
                    server_info["tools"] = []
                servers.append(server_info)
            return Response().ok(servers).to_json()
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(f"Failed to get MCP server list: {e!s}").to_json()

    async def add_mcp_server(self):
        try:
            server_data = await request.json
            name = server_data.get("name", "")
            if not name:
                return Response().error("Server name cannot be empty").to_json()
            has_valid_config = False
            server_config = {"active": server_data.get("active", True)}
            for key, value in server_data.items():
                if key not in ["name", "active", "tools", "errlogs"]:
                    if key == "mcpServers":
                        try:
                            server_config = _extract_mcp_server_config(
                                server_data["mcpServers"]
                            )
                        except ValueError as e:
                            return Response().error(f"{e!s}").to_json()
                    else:
                        server_config[key] = value
                    has_valid_config = True
            if not has_valid_config:
                return (
                    Response()
                    .error("A valid server configuration is required")
                    .to_json()
                )
            config = self.tool_mgr.load_mcp_config()
            if name in config["mcpServers"]:
                return Response().error(f"Server {name} already exists").to_json()
            try:
                await self.tool_mgr.test_mcp_server_connection(server_config)
            except Exception as e:
                logger.error(traceback.format_exc())
                return Response().error(f"MCP connection test failed: {e!s}").to_json()
            config["mcpServers"][name] = server_config
            if self.tool_mgr.save_mcp_config(config):
                try:
                    await self.tool_mgr.enable_mcp_server(
                        name, server_config, init_timeout=30
                    )
                except TimeoutError:
                    rollback_ok = self._rollback_mcp_server(name)
                    err_msg = f"Timed out while enabling MCP server {name}."
                    if not rollback_ok:
                        err_msg += " Configuration rollback failed. Please check the config manually."
                    return Response().error(err_msg).to_json()
                except Exception as e:
                    logger.error(traceback.format_exc())
                    rollback_ok = self._rollback_mcp_server(name)
                    err_msg = f"Failed to enable MCP server {name}: {e!s}"
                    if not rollback_ok:
                        err_msg += " Configuration rollback failed. Please check the config manually."
                    return Response().error(err_msg).to_json()
                return (
                    Response()
                    .ok(None, f"Successfully added MCP server {name}")
                    .to_json()
                )
            return Response().error("Failed to save configuration").to_json()
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(f"Failed to add MCP server: {e!s}").to_json()

    async def update_mcp_server(self):
        try:
            server_data = await request.json
            name = server_data.get("name", "")
            old_name = server_data.get("oldName") or name
            if not name:
                return Response().error("Server name cannot be empty").to_json()
            config = self.tool_mgr.load_mcp_config()
            if old_name not in config["mcpServers"]:
                return Response().error(f"Server {old_name} does not exist").to_json()
            is_rename = name != old_name
            if name in config["mcpServers"] and is_rename:
                return Response().error(f"Server {name} already exists").to_json()
            old_config = config["mcpServers"][old_name]
            if isinstance(old_config, dict):
                old_active = old_config.get("active", True)
            else:
                old_active = True
            active = server_data.get("active", old_active)
            server_config = {"active": active}
            only_update_active = True
            for key, value in server_data.items():
                if key not in ["name", "active", "tools", "errlogs", "oldName"]:
                    if key == "mcpServers":
                        try:
                            server_config = _extract_mcp_server_config(
                                server_data["mcpServers"]
                            )
                        except ValueError as e:
                            return Response().error(f"{e!s}").to_json()
                    else:
                        server_config[key] = value
                    only_update_active = False
            if only_update_active and isinstance(old_config, dict):
                for key, value in old_config.items():
                    if key != "active":
                        server_config[key] = value
            if is_rename:
                config["mcpServers"].pop(old_name)
                config["mcpServers"][name] = server_config
            else:
                config["mcpServers"][name] = server_config
            if self.tool_mgr.save_mcp_config(config):
                if active:
                    if (
                        old_name in self.tool_mgr.mcp_server_runtime_view
                        or not only_update_active
                        or is_rename
                    ):
                        try:
                            await self.tool_mgr.disable_mcp_server(
                                old_name, shutdown_timeout=10
                            )
                        except TimeoutError as e:
                            return (
                                Response()
                                .error(
                                    f"Timed out while disabling MCP server {old_name} before enabling: {e!s}"
                                )
                                .to_json()
                            )
                        except Exception as e:
                            logger.error(traceback.format_exc())
                            return (
                                Response()
                                .error(
                                    f"Failed to disable MCP server {old_name} before enabling: {e!s}"
                                )
                                .to_json()
                            )
                    try:
                        await self.tool_mgr.enable_mcp_server(
                            name, config["mcpServers"][name], init_timeout=30
                        )
                    except TimeoutError:
                        return (
                            Response()
                            .error(f"Timed out while enabling MCP server {name}.")
                            .to_json()
                        )
                    except Exception as e:
                        logger.error(traceback.format_exc())
                        return (
                            Response()
                            .error(f"Failed to enable MCP server {name}: {e!s}")
                            .to_json()
                        )
                elif old_name in self.tool_mgr.mcp_server_runtime_view:
                    try:
                        await self.tool_mgr.disable_mcp_server(old_name, timeout=10)
                    except TimeoutError:
                        return (
                            Response()
                            .error(f"Timed out while disabling MCP server {old_name}.")
                            .to_json()
                        )
                    except Exception as e:
                        logger.error(traceback.format_exc())
                        return (
                            Response()
                            .error(f"Failed to disable MCP server {old_name}: {e!s}")
                            .to_json()
                        )
                return (
                    Response()
                    .ok(None, f"Successfully updated MCP server {name}")
                    .to_json()
                )
            return Response().error("Failed to save configuration").to_json()
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(f"Failed to update MCP server: {e!s}").to_json()

    async def delete_mcp_server(self):
        try:
            server_data = await request.json
            name = server_data.get("name", "")
            if not name:
                return Response().error("Server name cannot be empty").to_json()
            config = self.tool_mgr.load_mcp_config()
            if name not in config["mcpServers"]:
                return Response().error(f"Server {name} does not exist").to_json()
            del config["mcpServers"][name]
            if self.tool_mgr.save_mcp_config(config):
                if name in self.tool_mgr.mcp_server_runtime_view:
                    try:
                        await self.tool_mgr.disable_mcp_server(name, timeout=10)
                    except TimeoutError:
                        return (
                            Response()
                            .error(f"Timed out while disabling MCP server {name}.")
                            .to_json()
                        )
                    except Exception as e:
                        logger.error(traceback.format_exc())
                        return (
                            Response()
                            .error(f"Failed to disable MCP server {name}: {e!s}")
                            .to_json()
                        )
                return (
                    Response()
                    .ok(None, f"Successfully deleted MCP server {name}")
                    .to_json()
                )
            return Response().error("Failed to save configuration").to_json()
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(f"Failed to delete MCP server: {e!s}").to_json()

    async def test_mcp_connection(self):
        """Test MCP server connection."""
        try:
            server_data = await request.json
            config = server_data.get("mcp_server_config", None)
            if not isinstance(config, dict) or not config:
                return Response().error("Invalid MCP server configuration").to_json()
            if "mcpServers" in config:
                mcp_servers = config["mcpServers"]
                if isinstance(mcp_servers, dict) and len(mcp_servers) > 1:
                    return (
                        Response()
                        .error(
                            "Only one MCP server configuration can be tested at a time"
                        )
                        .to_json()
                    )
                try:
                    config = _extract_mcp_server_config(mcp_servers)
                except EmptyMcpServersError:
                    return (
                        Response()
                        .error("MCP server configuration cannot be empty")
                        .to_json()
                    )
                except ValueError as e:
                    return Response().error(f"{e!s}").to_json()
            elif not config:
                return (
                    Response()
                    .error("MCP server configuration cannot be empty")
                    .to_json()
                )
            tools_name = await self.tool_mgr.test_mcp_server_connection(config)
            return (
                Response()
                .ok(data=tools_name, message="🎉 MCP server is available!")
                .to_json()
            )
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(f"Failed to test MCP connection: {e!s}").to_json()

    async def get_tool_list(self):
        """Get all registered tools."""
        try:
            tools = self.tool_mgr.func_list
            tools_dict = []
            for tool in tools:
                source = getattr(tool, "source", "plugin")
                if source == "mcp" and isinstance(tool, MCPTool):
                    origin = "mcp"
                    origin_name = tool.mcp_server_name
                elif source == "internal":
                    origin = "internal"
                    origin_name = "AstrBot"
                elif getattr(tool, "handler_module_path", None) and star_map.get(
                    getattr(tool, "handler_module_path", None)
                ):
                    handler_path = getattr(tool, "handler_module_path", None)
                    star = star_map[handler_path]
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
            return Response().ok(data=tools_dict).to_json()
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(f"Failed to get tool list: {e!s}").to_json()

    async def toggle_tool(self):
        """Activate or deactivate a specified tool."""
        try:
            data = await request.json
            tool_name = data.get("name")
            action = data.get("activate")
            if not tool_name or action is None:
                return (
                    Response()
                    .error("Missing required parameters: name or activate")
                    .to_json()
                )
            for t in self.tool_mgr.func_list:
                if t.name == tool_name and getattr(t, "source", "") == "internal":
                    return Response().error("内置工具不支持手动启用/停用").to_json()
            if action:
                try:
                    ok = self.tool_mgr.activate_llm_tool(tool_name)
                except ValueError as e:
                    return Response().error(f"Failed to activate tool: {e!s}").to_json()
            else:
                ok = self.tool_mgr.deactivate_llm_tool(tool_name)
            if ok:
                return Response().ok(None, "Operation successful.").to_json()
            return (
                Response()
                .error(f"Tool {tool_name} does not exist or the operation failed.")
                .to_json()
            )
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(f"Failed to operate tool: {e!s}").to_json()

    async def sync_provider(self):
        """Sync MCP provider configuration."""
        try:
            data = await request.json
            provider_name = data.get("name")
            match provider_name:
                case "modelscope":
                    access_token = data.get("access_token", "")
                    await self.tool_mgr.sync_modelscope_mcp_servers(access_token)
                case _:
                    return (
                        Response().error(f"Unknown provider: {provider_name}").to_json()
                    )
            return Response().ok(message="Sync completed").to_json()
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(f"Sync failed: {e!s}").to_json()
