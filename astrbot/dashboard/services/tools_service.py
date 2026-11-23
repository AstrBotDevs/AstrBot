from __future__ import annotations

import traceback
from collections.abc import Callable
from typing import Any

from astrbot.core import logger, sp
from astrbot.core.agent.mcp_client import MCPTool, validate_mcp_stdio_config
from astrbot.core.agent.tool import FunctionTool
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.star import star_map
from astrbot.dashboard.validation import is_json_object


class ToolsServiceError(Exception):
    pass


class EmptyMcpServersError(ValueError):
    pass


def extract_mcp_server_config(mcp_servers_value: object) -> dict:
    if not is_json_object(mcp_servers_value):
        raise ValueError("mcpServers must be a JSON object")
    if not mcp_servers_value:
        raise EmptyMcpServersError("mcpServers configuration cannot be empty")
    key_0 = next(iter(mcp_servers_value))
    extracted = mcp_servers_value[key_0]
    if not is_json_object(extracted):
        raise ValueError(
            "Invalid mcpServers format. Ensure each key in mcpServers is a server name, "
            "and each value is an object containing fields like command/url."
        )
    return extracted


def rollback_mcp_server_config(tool_mgr, name: str) -> bool:
    """Remove one saved server after its runtime failed to start."""
    try:
        config = tool_mgr.load_mcp_config()
        if name in config["mcpServers"]:
            config["mcpServers"].pop(name)
            return tool_mgr.save_mcp_config(config)
        return True
    except Exception:
        logger.error(traceback.format_exc())
        return False


def describe_mcp_servers(tool_mgr, *, include_connected: bool) -> list[dict]:
    """Merge persisted server settings with the current runtime view."""
    config = tool_mgr.load_mcp_config()
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
        server_info = {"name": name, "active": server_config.get("active", True)}
        for key, value in server_config.items():
            if key != "active":
                server_info[key] = value
        runtime = tool_mgr.mcp_server_runtime_view.get(name)
        if include_connected:
            server_info["connected"] = runtime is not None
        if runtime is None:
            server_info["tools"] = []
        else:
            server_info["tools"] = [tool.name for tool in runtime.client.tools]
            server_info["errlogs"] = runtime.client.server_errlogs
        servers.append(server_info)
    return servers


def merge_mcp_server_config(
    server_data: dict,
    active: object,
    *,
    excluded_keys: tuple[str, ...],
    extract_config: Callable[[object], dict],
) -> tuple[bool, dict]:
    """Collect submitted settings while preserving each adapter's accepted fields."""
    has_config = False
    server_config = {"active": active}
    for key, value in server_data.items():
        if key in excluded_keys:
            continue
        if key == "mcpServers":
            server_config = extract_config(value)
        else:
            server_config[key] = value
        has_config = True
    return has_config, server_config


class ToolsService:
    def __init__(self, core_lifecycle: AstrBotCoreLifecycle) -> None:
        self.tool_mgr = core_lifecycle.provider_manager.llm_tools

    def rollback_mcp_server(self, name: str) -> bool:
        return rollback_mcp_server_config(self.tool_mgr, name)

    def get_mcp_servers(self) -> list[dict]:
        try:
            return describe_mcp_servers(self.tool_mgr, include_connected=True)
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise ToolsServiceError(f"Failed to get MCP server list: {exc!s}") from exc

    def get_mcp_server_config(self, name: str) -> dict | None:
        config = self.tool_mgr.load_mcp_config()
        mcp_servers = config.get("mcpServers", {})
        if not isinstance(mcp_servers, dict):
            return None

        server_config = mcp_servers.get(name)
        if not isinstance(server_config, dict):
            return None
        return dict(server_config)

    async def add_mcp_server(self, server_data: Any) -> str:
        try:
            name = server_data.get("name", "")
            if not name:
                raise ToolsServiceError("Server name cannot be empty")

            has_valid_config, server_config = self._build_server_config(server_data)
            if not has_valid_config:
                raise ToolsServiceError("A valid server configuration is required")

            self._validate_server_config(server_config)

            config = self.tool_mgr.load_mcp_config()
            if name in config["mcpServers"]:
                raise ToolsServiceError(f"Server {name} already exists")

            try:
                await self.tool_mgr.test_mcp_server_connection(server_config)
            except Exception as exc:
                logger.error(traceback.format_exc())
                raise ToolsServiceError(f"MCP connection test failed: {exc!s}") from exc

            config["mcpServers"][name] = server_config

            if self.tool_mgr.save_mcp_config(config):
                await self._enable_added_server(name, server_config)
                return f"Successfully added MCP server {name}"
            raise ToolsServiceError("Failed to save configuration")
        except ToolsServiceError:
            raise
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise ToolsServiceError(f"Failed to add MCP server: {exc!s}") from exc

    async def update_mcp_server(self, server_data: Any) -> str:
        try:
            name = server_data.get("name", "")
            old_name = server_data.get("oldName") or name

            if not name:
                raise ToolsServiceError("Server name cannot be empty")

            config = self.tool_mgr.load_mcp_config()

            if old_name not in config["mcpServers"]:
                raise ToolsServiceError(f"Server {old_name} does not exist")

            is_rename = name != old_name
            if name in config["mcpServers"] and is_rename:
                raise ToolsServiceError(f"Server {name} already exists")

            old_config = config["mcpServers"][old_name]
            old_active = (
                old_config.get("active", True) if isinstance(old_config, dict) else True
            )
            active = server_data.get("active", old_active)

            only_update_active, server_config = self._build_updated_server_config(
                server_data,
                old_config,
                active,
            )
            self._validate_server_config(server_config)

            if is_rename:
                config["mcpServers"].pop(old_name)
                config["mcpServers"][name] = server_config
            else:
                config["mcpServers"][name] = server_config

            if self.tool_mgr.save_mcp_config(config):
                await self._sync_updated_server_runtime(
                    name=name,
                    old_name=old_name,
                    active=active,
                    is_rename=is_rename,
                    only_update_active=only_update_active,
                    server_config=config["mcpServers"][name],
                )
                return f"Successfully updated MCP server {name}"
            raise ToolsServiceError("Failed to save configuration")
        except ToolsServiceError:
            raise
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise ToolsServiceError(f"Failed to update MCP server: {exc!s}") from exc

    async def delete_mcp_server(self, server_data: Any) -> str:
        try:
            name = server_data.get("name", "")

            if not name:
                raise ToolsServiceError("Server name cannot be empty")

            config = self.tool_mgr.load_mcp_config()

            if name not in config["mcpServers"]:
                raise ToolsServiceError(f"Server {name} does not exist")

            del config["mcpServers"][name]

            if self.tool_mgr.save_mcp_config(config):
                if name in self.tool_mgr.mcp_server_runtime_view:
                    await self._disable_server(name)
                return f"Successfully deleted MCP server {name}"
            raise ToolsServiceError("Failed to save configuration")
        except ToolsServiceError:
            raise
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise ToolsServiceError(f"Failed to delete MCP server: {exc!s}") from exc

    async def test_mcp_connection(self, server_data: Any) -> list:
        try:
            config = server_data.get("mcp_server_config", None)

            if not isinstance(config, dict) or not config:
                raise ToolsServiceError("Invalid MCP server configuration")

            if "mcpServers" in config:
                mcp_servers = config["mcpServers"]
                if isinstance(mcp_servers, dict) and len(mcp_servers) > 1:
                    raise ToolsServiceError(
                        "Only one MCP server configuration can be tested at a time"
                    )
                try:
                    config = extract_mcp_server_config(mcp_servers)
                except EmptyMcpServersError as exc:
                    raise ToolsServiceError(
                        "MCP server configuration cannot be empty"
                    ) from exc
                except ValueError as exc:
                    raise ToolsServiceError(f"{exc!s}") from exc
            elif not config:
                raise ToolsServiceError("MCP server configuration cannot be empty")

            self._validate_server_config(config)
            return await self.tool_mgr.test_mcp_server_connection(config)
        except ToolsServiceError:
            raise
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise ToolsServiceError(f"Failed to test MCP connection: {exc!s}") from exc

    async def get_tool_list(self) -> list[dict]:
        try:
            tools = list(self.tool_mgr.func_list)
            if not tools:
                return []
            perms_store = await sp.global_get("tool_permissions", {})
            return [self._serialize_tool(tool, perms_store) for tool in tools]
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise ToolsServiceError(f"Failed to get tool list: {exc!s}") from exc

    def _resolve_managed_tool(self, data: object) -> FunctionTool:
        """Validate a management identity and resolve exactly one tool.

        Args:
            data: Dashboard selector with a name or opaque tool key.

        Returns:
            The registered tool selected by all supplied identity fields.

        Raises:
            ToolsServiceError: If any selector is unsupported or ambiguous.
        """
        if not isinstance(data, dict):
            raise ToolsServiceError("Tool payload must be a JSON object")
        for field in ("name", "tool_key", "runtime_kind", "plugin_id", "source"):
            value = data.get(field)
            if value is not None and (not isinstance(value, str) or not value):
                raise ToolsServiceError(f"{field} must be a nonempty string")
        if data.get("runtime_kind") not in (None, "legacy"):
            raise ToolsServiceError("Unsupported tool runtime identity")
        name = data.get("name")
        tool_key = data.get("tool_key")
        if name is None and tool_key is None:
            raise ToolsServiceError("name or tool_key is required")
        try:
            tool = self.tool_mgr.resolve_tool(name, tool_key=tool_key)
        except ValueError as exc:
            raise ToolsServiceError(str(exc)) from exc
        if tool is None:
            raise ToolsServiceError("Tool identity was not found")
        source = "mcp" if isinstance(tool, MCPTool) else tool.source
        if data.get("source") is not None and data["source"] != source:
            raise ToolsServiceError(
                "Tool source does not match the registered identity"
            )
        module_path = tool.handler_module_path
        plugin = star_map.get(module_path) if module_path is not None else None
        plugin_id = plugin.name if plugin is not None else None
        if data.get("plugin_id") is not None and data["plugin_id"] != plugin_id:
            raise ToolsServiceError(
                "Tool plugin does not match the registered identity"
            )
        if source in ("native", "internal"):
            raise ToolsServiceError(
                "Native and internal tools are managed by the runtime"
            )
        return tool

    async def update_tool_permission(self, data: Any) -> str:
        """Persist a permission for one exact registered tool."""
        try:
            tool = self._resolve_managed_tool(data)
            permission = data.get("permission")
            if permission not in ("admin", "member"):
                raise ToolsServiceError("permission must be admin or member")
            stored = await sp.global_get("tool_permissions", {})
            perms_store = dict(stored) if isinstance(stored, dict) else {}
            defaults = perms_store.get("_default", {})
            defaults = dict(defaults) if isinstance(defaults, dict) else {}
            defaults[self.tool_mgr.get_tool_key(tool)] = permission
            if data.get("tool_key") is None and data.get("name") == tool.name:
                defaults[tool.name] = permission
            perms_store["_default"] = defaults
            await sp.global_put("tool_permissions", perms_store)
            return f"Tool '{tool.name}' permission set to {permission}"
        except ToolsServiceError:
            raise
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise ToolsServiceError(
                f"Failed to update tool permission: {exc!s}"
            ) from exc

    async def toggle_tool(self, data: Any) -> str:
        """Toggle one registered tool and await its exact persisted state."""
        try:
            tool = self._resolve_managed_tool(data)
            action = data.get("activate")
            if not isinstance(action, bool):
                raise ToolsServiceError("activate must be a boolean")
            ok = await self.tool_mgr.set_tool_active(
                self.tool_mgr.get_tool_key(tool), action, star_map
            )
            if ok:
                return "Operation successful."
            raise ToolsServiceError("Tool identity no longer exists")
        except ToolsServiceError:
            raise
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise ToolsServiceError(f"Failed to operate tool: {exc!s}") from exc

    async def sync_provider(self, data: Any) -> str:
        try:
            provider_name = data.get("name")
            match provider_name:
                case "modelscope":
                    access_token = data.get("access_token", "")
                    await self.tool_mgr.sync_modelscope_mcp_servers(access_token)
                case _:
                    raise ToolsServiceError(f"Unknown provider: {provider_name}")

            return "Sync completed"
        except ToolsServiceError:
            raise
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise ToolsServiceError(f"Sync failed: {exc!s}") from exc

    @staticmethod
    def _build_server_config(server_data: dict) -> tuple[bool, dict]:
        try:
            return merge_mcp_server_config(
                server_data,
                server_data.get("active", True),
                excluded_keys=("name", "active", "tools", "errlogs"),
                extract_config=extract_mcp_server_config,
            )
        except ValueError as exc:
            raise ToolsServiceError(f"{exc!s}") from exc

    @staticmethod
    def _build_updated_server_config(
        server_data: dict,
        old_config: object,
        active: bool,
    ) -> tuple[bool, dict]:
        try:
            has_config, server_config = merge_mcp_server_config(
                server_data,
                active,
                excluded_keys=(
                    "name",
                    "active",
                    "connected",
                    "tools",
                    "errlogs",
                    "oldName",
                ),
                extract_config=extract_mcp_server_config,
            )
        except ValueError as exc:
            raise ToolsServiceError(f"{exc!s}") from exc
        only_update_active = not has_config
        if only_update_active and is_json_object(old_config):
            for key, value in old_config.items():
                if key != "active":
                    server_config[key] = value
        return only_update_active, server_config

    @staticmethod
    def _validate_server_config(server_config: dict) -> None:
        try:
            validate_mcp_stdio_config(server_config)
        except ValueError as exc:
            raise ToolsServiceError(f"{exc!s}") from exc

    async def _enable_added_server(self, name: str, server_config: dict) -> None:
        try:
            await self.tool_mgr.enable_mcp_server(name, server_config, timeout=30)
        except TimeoutError as exc:
            rollback_ok = self.rollback_mcp_server(name)
            err_msg = f"Timed out while enabling MCP server {name}."
            if not rollback_ok:
                err_msg += (
                    " Configuration rollback failed. Please check the config manually."
                )
            raise ToolsServiceError(err_msg) from exc
        except Exception as exc:
            logger.error(traceback.format_exc())
            rollback_ok = self.rollback_mcp_server(name)
            err_msg = f"Failed to enable MCP server {name}: {exc!s}"
            if not rollback_ok:
                err_msg += (
                    " Configuration rollback failed. Please check the config manually."
                )
            raise ToolsServiceError(err_msg) from exc

    async def _sync_updated_server_runtime(
        self,
        *,
        name: str,
        old_name: str,
        active: bool,
        is_rename: bool,
        only_update_active: bool,
        server_config: dict,
    ) -> None:
        if active:
            if (
                old_name in self.tool_mgr.mcp_server_runtime_view
                or not only_update_active
                or is_rename
            ):
                await self._disable_server_before_enable(old_name)
            await self._enable_updated_server(name, server_config)
        elif old_name in self.tool_mgr.mcp_server_runtime_view:
            await self._disable_server(old_name)

    async def _disable_server_before_enable(self, old_name: str) -> None:
        try:
            await self.tool_mgr.disable_mcp_server(old_name, timeout=10)
        except TimeoutError as exc:
            raise ToolsServiceError(
                f"Timed out while disabling MCP server {old_name} before enabling: {exc!s}"
            ) from exc
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise ToolsServiceError(
                f"Failed to disable MCP server {old_name} before enabling: {exc!s}"
            ) from exc

    async def _enable_updated_server(self, name: str, server_config: dict) -> None:
        try:
            await self.tool_mgr.enable_mcp_server(name, server_config, timeout=30)
        except TimeoutError as exc:
            raise ToolsServiceError(
                f"Timed out while enabling MCP server {name}."
            ) from exc
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise ToolsServiceError(
                f"Failed to enable MCP server {name}: {exc!s}"
            ) from exc

    async def _disable_server(self, name: str) -> None:
        try:
            await self.tool_mgr.disable_mcp_server(name, timeout=10)
        except TimeoutError as exc:
            raise ToolsServiceError(
                f"Timed out while disabling MCP server {name}."
            ) from exc
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise ToolsServiceError(
                f"Failed to disable MCP server {name}: {exc!s}"
            ) from exc

    def _serialize_tool(
        self,
        tool,
        perms_store: object,
    ) -> dict:
        if isinstance(tool, MCPTool):
            origin = "mcp"
            origin_name = tool.mcp_server_name
            origin_display_name = origin_name
        elif tool.handler_module_path and star_map.get(tool.handler_module_path):
            star = star_map[tool.handler_module_path]
            origin = "plugin"
            origin_name = star.name
            origin_display_name = star.display_name or star.name
        else:
            origin = "unknown"
            origin_name = "unknown"
            origin_display_name = origin_name

        defaults = (
            perms_store.get("_default", {}) if isinstance(perms_store, dict) else {}
        )
        if not isinstance(defaults, dict):
            defaults = {}
        tool_key = self.tool_mgr.get_tool_key(tool)
        return {
            "name": tool.name,
            "tool_key": tool_key,
            "runtime_kind": "legacy",
            "plugin_id": origin_name if origin == "plugin" else None,
            "source": "mcp" if isinstance(tool, MCPTool) else tool.source,
            "description": tool.description,
            "parameters": tool.parameters,
            "active": tool.active,
            "origin": origin,
            "origin_name": origin_name,
            "origin_display_name": origin_display_name,
            "permission": defaults.get(tool_key, defaults.get(tool.name, "member")),
            "permission_configured": tool_key in defaults or tool.name in defaults,
        }
