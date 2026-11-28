from __future__ import annotations

import asyncio
import traceback
from typing import Any

from astrbot.core import logger, sp
from astrbot.core.agent.mcp_client import MCPTool, validate_mcp_stdio_config
from astrbot.core.capabilities import (
    SETTINGS_SCOPE,
    global_settings,
    legacy_setting,
    tool_ref,
    update_setting,
    write_legacy_setting,
)
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.star import star_map


class ToolsServiceError(Exception):
    pass


class EmptyMcpServersError(ValueError):
    pass


def extract_mcp_server_config(mcp_servers_value: object) -> dict:
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


class ToolsService:
    def __init__(self, core_lifecycle: AstrBotCoreLifecycle) -> None:
        self.tool_mgr = core_lifecycle.provider_manager.llm_tools
        self._tool_settings_lock = asyncio.Lock()

    def rollback_mcp_server(self, name: str) -> bool:
        try:
            rollback_config = self.tool_mgr.load_mcp_config()
            if name in rollback_config["mcpServers"]:
                rollback_config["mcpServers"].pop(name)
                return self.tool_mgr.save_mcp_config(rollback_config)
            return True
        except Exception:
            logger.error(traceback.format_exc())
            return False

    def get_mcp_servers(self) -> list[dict]:
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

                runtime = self.tool_mgr.mcp_server_runtime_view.get(name)
                server_info["connected"] = runtime is not None
                if runtime is None:
                    server_info["tools"] = []
                else:
                    mcp_client = runtime.client
                    server_info["tools"] = [tool.name for tool in mcp_client.tools]
                    server_info["errlogs"] = mcp_client.server_errlogs

                servers.append(server_info)

            return servers
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
            namespace = MCPTool.server_namespace(name)
            for other, other_config in config["mcpServers"].items():
                if not isinstance(other_config, dict):
                    continue
                if MCPTool.server_namespace(other) == namespace:
                    raise ToolsServiceError(
                        f"Server {other!r} already uses tool namespace {namespace!r}. "
                        "Choose another server name."
                    )

            try:
                await self.tool_mgr.test_mcp_server_connection(server_config)
            except Exception as exc:
                logger.error(traceback.format_exc())
                raise ToolsServiceError(f"MCP connection test failed: {exc!s}") from exc

            server_config.pop("_astrbot_id", None)
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
            if is_rename:
                if name in config["mcpServers"]:
                    raise ToolsServiceError(f"Server {name} already exists")
                namespace = MCPTool.server_namespace(name)
                for other, other_config in config["mcpServers"].items():
                    if (
                        other != old_name
                        and isinstance(other_config, dict)
                        and MCPTool.server_namespace(other) == namespace
                    ):
                        raise ToolsServiceError(
                            f"Server {other!r} already uses tool namespace {namespace!r}. "
                            "Choose another server name."
                        )

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
            server_config.pop("_astrbot_id", None)
            if isinstance(old_config, dict) and old_config.get("_astrbot_id"):
                server_config["_astrbot_id"] = old_config["_astrbot_id"]

            if is_rename:
                config["mcpServers"].pop(old_name)
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

    async def get_tool_list(self, *, include_saved: bool = False) -> list[dict]:
        try:
            tools = list(self.tool_mgr.func_list)
            if not tools and not include_saved:
                return []
            perms_store = await legacy_setting("tool_permissions", {})
            defaults = (
                perms_store.get("_default", {}) if isinstance(perms_store, dict) else {}
            )
            if not isinstance(defaults, dict):
                defaults = {}
            settings = await global_settings()
            result = [
                self._serialize_tool(
                    tool, defaults, settings.get(tool_ref(tool).key, {})
                )
                for tool in tools
            ]
            if not include_saved:
                return result

            stored_inactive = await legacy_setting("inactivated_llm_tools", [])
            inactive_names = (
                {name for name in stored_inactive if isinstance(name, str) and name}
                if isinstance(stored_inactive, list)
                else set()
            )
            for entry in result:
                scoped = settings.get(entry["capability"]["key"], {})
                entry["inactive_configured"] = not scoped.get(
                    "enabled", entry["name"] not in inactive_names
                )
            registered_names = {entry["name"] for entry in result}
            saved_names = {name for name in defaults if isinstance(name, str) and name}
            for name in sorted((inactive_names | saved_names) - registered_names):
                result.append(
                    {
                        "name": name,
                        "description": "",
                        "active": False,
                        "registered": False,
                        "inactive_configured": name in inactive_names,
                        "permission": defaults.get(name),
                        "permission_configured": name in defaults,
                    }
                )
            registered_keys = {
                entry["capability"]["key"] for entry in result if "capability" in entry
            }
            for key, setting in settings.items():
                if key not in registered_keys and (
                    "/tools/" in key or key.startswith("astrbot/tools/")
                ):
                    result.append(
                        {
                            "name": key,
                            "description": "",
                            "active": False,
                            "registered": False,
                            "resource_key": key,
                            "inactive_configured": setting.get("enabled") is False,
                            "permission": setting.get("permission"),
                            "permission_configured": "permission" in setting,
                        }
                    )
            return result
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise ToolsServiceError(f"Failed to get tool list: {exc!s}") from exc

    async def delete_unregistered_tool_settings(
        self, tool_name: str, resource_key: str | None = None
    ) -> str:
        """Clear the saved global settings for one unregistered tool.

        Args:
            tool_name: Exact name used in the global tool settings.

        Returns:
            A success message for the response body.

        Raises:
            ToolsServiceError: If the tool is registered or its settings cannot be saved.
        """
        try:
            async with self._tool_settings_lock:
                if resource_key is not None:
                    if not (
                        "/tools/" in resource_key
                        or resource_key.startswith("astrbot/tools/")
                    ):
                        raise ToolsServiceError("Invalid tool resource")
                    if any(
                        tool_ref(tool).key == resource_key
                        for tool in self.tool_mgr.func_list
                    ):
                        raise ToolsServiceError(f"Tool '{resource_key}' is registered")
                    await sp.remove_async(SETTINGS_SCOPE, "global", resource_key)
                    return f"Saved settings for tool '{resource_key}' deleted"
                permissions = await legacy_setting("tool_permissions", None)
                inactive = await legacy_setting("inactivated_llm_tools", None)
                if any(tool.name == tool_name for tool in self.tool_mgr.func_list):
                    raise ToolsServiceError(f"Tool '{tool_name}' is registered")

                defaults = (
                    permissions.get("_default")
                    if isinstance(permissions, dict)
                    else None
                )
                # Persist both containers so a retry can finish a partial write.
                if isinstance(defaults, dict):
                    defaults.pop(tool_name, None)
                    await write_legacy_setting("tool_permissions", permissions)
                if isinstance(inactive, list):
                    await write_legacy_setting(
                        "inactivated_llm_tools",
                        [name for name in inactive if name != tool_name],
                    )
            return f"Saved settings for tool '{tool_name}' deleted"
        except ToolsServiceError:
            raise
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise ToolsServiceError(
                f"Failed to delete saved tool settings: {exc!s}"
            ) from exc

    async def update_tool_permission(self, data: Any) -> str:
        """Set a tool permission level.

        Args:
            data: Legacy dashboard payload with ``name`` and ``permission``.

        Returns:
            A success message for the response body.

        Raises:
            ToolsServiceError: If the payload is invalid, the tool is unknown,
                or permission storage cannot be updated.
        """
        try:
            tool_name = data.get("name") if isinstance(data, dict) else None
            permission = data.get("permission") if isinstance(data, dict) else None

            if not tool_name or permission not in ("admin", "member"):
                raise ToolsServiceError(
                    "name and permission (admin or member) are required"
                )

            tool = self._find_tool(tool_name, data.get("resource_key"))
            if tool is None:
                raise ToolsServiceError(f"Tool '{tool_name}' not found")
            await update_setting(tool_ref(tool), permission=permission)

            return f"Tool '{tool_name}' permission set to {permission}"
        except ToolsServiceError:
            raise
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise ToolsServiceError(
                f"Failed to update tool permission: {exc!s}"
            ) from exc

    def _find_tool(self, name: str, resource_key: str | None):
        if resource_key is None:
            return self.tool_mgr.get_func(name)
        return next(
            (
                tool
                for tool in self.tool_mgr.func_list
                if tool.name == name and tool_ref(tool).key == resource_key
            ),
            None,
        )

    async def toggle_tool(self, data: Any) -> str:
        """Toggle a tool and wait for its preference change to persist.

        Args:
            data: Mapping containing the tool name and activation state.

        Returns:
            Operation result message.

        Raises:
            ToolsServiceError: If validation or the tool operation fails.
        """
        try:
            tool_name = data.get("name")
            action = data.get("activate")

            if not tool_name or action is None:
                raise ToolsServiceError("Missing required parameters: name or activate")

            tool = self._find_tool(tool_name, data.get("resource_key"))
            if tool is None:
                raise ToolsServiceError(f"Tool '{tool_name}' not found")
            async with self._tool_settings_lock:
                if action:
                    try:
                        ok = await self.tool_mgr.activate_llm_tool_async(
                            tool_name,
                            star_map=star_map,
                            tool=tool,
                        )
                    except ValueError as exc:
                        raise ToolsServiceError(
                            f"Failed to activate tool: {exc!s}"
                        ) from exc
                else:
                    ok = await self.tool_mgr.deactivate_llm_tool_async(
                        tool_name, tool=tool
                    )

            if ok:
                return "Operation successful."
            raise ToolsServiceError(
                f"Tool {tool_name} does not exist or the operation failed."
            )
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
        has_valid_config = False
        server_config = {"active": server_data.get("active", True)}

        for key, value in server_data.items():
            if key in ["name", "active", "tools", "errlogs", "_astrbot_id"]:
                continue
            if key == "mcpServers":
                try:
                    server_config = extract_mcp_server_config(server_data["mcpServers"])
                except ValueError as exc:
                    raise ToolsServiceError(f"{exc!s}") from exc
            else:
                server_config[key] = value
            has_valid_config = True

        return has_valid_config, server_config

    @staticmethod
    def _build_updated_server_config(
        server_data: dict,
        old_config: object,
        active: bool,
    ) -> tuple[bool, dict]:
        server_config = {"active": active}
        only_update_active = True

        for key, value in server_data.items():
            if key in [
                "name",
                "active",
                "connected",
                "tools",
                "errlogs",
                "oldName",
                "_astrbot_id",
            ]:
                continue
            if key == "mcpServers":
                try:
                    server_config = extract_mcp_server_config(server_data["mcpServers"])
                except ValueError as exc:
                    raise ToolsServiceError(f"{exc!s}") from exc
            else:
                server_config[key] = value
            only_update_active = False

        if only_update_active and isinstance(old_config, dict):
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
        defaults: dict,
        settings: dict,
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

        return {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
            "active": tool.active,
            "origin": origin,
            "origin_name": origin_name,
            "origin_display_name": origin_display_name,
            "capability": tool_ref(tool).metadata(),
            "permission": settings.get("permission", defaults.get(tool.name, "member")),
            "permission_configured": "permission" in settings or tool.name in defaults,
        }
