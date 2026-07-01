from __future__ import annotations

import traceback
from typing import Any

from astrbot.core import logger, sp
from astrbot.core.agent.mcp_client import MCPTool, validate_mcp_stdio_config
from astrbot.core.agent.mcp_oauth import MCPOAuthAuthorizationRequiredError
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.star import star_map
from astrbot.core.tools.registry import get_builtin_tool_config_statuses


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
        self.core_lifecycle = core_lifecycle
        self.tool_mgr = core_lifecycle.provider_manager.llm_tools

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

    async def get_mcp_servers(self) -> list[dict]:
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

                get_oauth_state = getattr(self.tool_mgr, "get_mcp_oauth_state", None)
                if get_oauth_state is not None:
                    server_info.update(await get_oauth_state(server_config))

                for name_key, runtime in self.tool_mgr.mcp_server_runtime_view.items():
                    if name_key == name:
                        mcp_client = runtime.client
                        server_info["tools"] = [tool.name for tool in mcp_client.tools]
                        server_info["errlogs"] = mcp_client.server_errlogs
                        break
                else:
                    server_info["tools"] = []

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

            try:
                await self.tool_mgr.test_mcp_server_connection(server_config)
            except MCPOAuthAuthorizationRequiredError as exc:
                raise ToolsServiceError(f"{exc!s}") from exc
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

            config.pop("oauth2_enabled", None)
            config.pop("oauth2_authorized", None)
            config.pop("oauth2_grant_type", None)
            self._validate_server_config(config)
            return await self.tool_mgr.test_mcp_server_connection(config)
        except ToolsServiceError:
            raise
        except MCPOAuthAuthorizationRequiredError as exc:
            raise ToolsServiceError(f"{exc!s}") from exc
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise ToolsServiceError(f"Failed to test MCP connection: {exc!s}") from exc

    def get_tool_list(self) -> list[dict]:
        try:
            tools = list(self.tool_mgr.func_list)
            existing_names = {tool.name for tool in tools}
            for tool in self.tool_mgr.iter_builtin_tools():
                if tool.name not in existing_names:
                    tools.append(tool)

            config_entries = self._get_config_entries()
            tools_dict = []
            for tool in tools:
                tools_dict.append(self._serialize_tool(tool, config_entries))
            return tools_dict
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise ToolsServiceError(f"Failed to get tool list: {exc!s}") from exc

    def update_tool_permission(self, data: Any) -> str:
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

            if self.tool_mgr.is_builtin_tool(tool_name):
                raise ToolsServiceError(
                    "Builtin tools do not support per-tool permission configuration."
                )

            if not any(t.name == tool_name for t in self.tool_mgr.func_list):
                raise ToolsServiceError(f"Tool '{tool_name}' not found")

            perms_store = sp.get(
                "tool_permissions",
                {},
                scope="global",
                scope_id="global",
            )
            if not isinstance(perms_store, dict):
                perms_store = {}
            defaults = perms_store.get("_default", {})
            if not isinstance(defaults, dict):
                defaults = {}
            defaults[tool_name] = permission
            perms_store["_default"] = defaults
            sp.put(
                "tool_permissions",
                perms_store,
                scope="global",
                scope_id="global",
            )

            return f"Tool '{tool_name}' permission set to {permission}"
        except ToolsServiceError:
            raise
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise ToolsServiceError(
                f"Failed to update tool permission: {exc!s}"
            ) from exc

    def toggle_tool(self, data: Any) -> str:
        try:
            tool_name = data.get("name")
            action = data.get("activate")

            if not tool_name or action is None:
                raise ToolsServiceError("Missing required parameters: name or activate")

            if self.tool_mgr.is_builtin_tool(tool_name):
                raise ToolsServiceError(
                    "Builtin tools are read-only and cannot be toggled."
                )

            if action:
                try:
                    ok = self.tool_mgr.activate_llm_tool(tool_name, star_map=star_map)
                except ValueError as exc:
                    raise ToolsServiceError(
                        f"Failed to activate tool: {exc!s}"
                    ) from exc
            else:
                ok = self.tool_mgr.deactivate_llm_tool(tool_name)

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

    async def start_mcp_oauth_authorization(
        self,
        config: dict,
        *,
        callback_base_url: str,
        server_name: str | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """Start an interactive MCP OAuth authorization flow.

        Args:
            config: Normalized MCP server configuration that includes OAuth settings.
            callback_base_url: Public dashboard base URL used for the OAuth callback.
            server_name: Optional MCP server name associated with the flow.
            force: Whether to clear existing OAuth credentials before starting the flow.

        Returns:
            Current OAuth flow status payload.

        Raises:
            ToolsServiceError: If the flow cannot be started.
        """
        try:
            return await self.tool_mgr.start_mcp_oauth_authorization(
                config,
                callback_base_url=callback_base_url,
                server_name=server_name,
                force=force,
            )
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise ToolsServiceError(
                f"Failed to start MCP OAuth authorization: {exc!s}"
            ) from exc

    def get_mcp_oauth_flow_status(self, flow_id: str) -> dict[str, Any]:
        """Get an MCP OAuth authorization flow status.

        Args:
            flow_id: Identifier returned by the OAuth start endpoint.

        Returns:
            Current OAuth flow status payload.

        Raises:
            ToolsServiceError: If the flow is missing or status lookup fails.
        """
        try:
            return self.tool_mgr.get_mcp_oauth_flow_status(flow_id)
        except KeyError as exc:
            raise ToolsServiceError("OAuth flow not found or expired") from exc
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise ToolsServiceError(f"Failed to get MCP OAuth status: {exc!s}") from exc

    async def submit_mcp_oauth_callback(
        self,
        flow_id: str | None,
        *,
        code: str | None,
        state: str | None,
        error: str | None,
    ) -> None:
        """Submit OAuth callback parameters to a pending MCP flow.

        Args:
            flow_id: Optional flow identifier; the OAuth state is used when omitted.
            code: Authorization code from the provider callback.
            state: OAuth state from the provider callback.
            error: Provider error text, if authorization failed.

        Raises:
            KeyError: If the flow is not found or expired.
            ToolsServiceError: If callback processing fails.
        """
        try:
            await self.tool_mgr.submit_mcp_oauth_callback(
                flow_id,
                code=code,
                state=state,
                error=error,
            )
        except KeyError:
            raise
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise ToolsServiceError(f"OAuth callback failed: {exc!s}") from exc

    @staticmethod
    def _build_server_config(server_data: dict) -> tuple[bool, dict]:
        has_valid_config = False
        server_config = {"active": server_data.get("active", True)}

        for key, value in server_data.items():
            if key in [
                "name",
                "active",
                "tools",
                "errlogs",
                "oauth2_enabled",
                "oauth2_authorized",
                "oauth2_grant_type",
            ]:
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
                "tools",
                "errlogs",
                "oldName",
                "oauth2_enabled",
                "oauth2_authorized",
                "oauth2_grant_type",
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
        except MCPOAuthAuthorizationRequiredError as exc:
            rollback_ok = self.rollback_mcp_server(name)
            err_msg = f"{exc!s}"
            if not rollback_ok:
                err_msg += (
                    " Configuration rollback failed. Please check the config manually."
                )
            raise ToolsServiceError(err_msg) from exc
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
        except MCPOAuthAuthorizationRequiredError as exc:
            raise ToolsServiceError(f"{exc!s}") from exc
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

    def _get_config_entries(self) -> list[dict]:
        conf_list = self.core_lifecycle.astrbot_config_mgr.get_conf_list()
        conf_name_map = {conf["id"]: conf["name"] for conf in conf_list}
        config_entries = []
        for conf_id, conf in self.core_lifecycle.astrbot_config_mgr.confs.items():
            config_entries.append(
                {
                    "conf_id": conf_id,
                    "conf_name": conf_name_map.get(conf_id, conf_id),
                    "config": conf,
                }
            )
        return config_entries

    def _serialize_tool(self, tool, config_entries: list[dict]) -> dict:
        readonly = False
        builtin_config_statuses = []
        builtin_config_tags = []
        if self.tool_mgr.is_builtin_tool(tool.name):
            origin = "builtin"
            origin_name = "AstrBot Core"
            readonly = True
            builtin_config_statuses = get_builtin_tool_config_statuses(
                tool.name,
                config_entries,
            )
            builtin_config_tags = [
                status for status in builtin_config_statuses if status["enabled"]
            ]
        elif isinstance(tool, MCPTool):
            origin = "mcp"
            origin_name = tool.mcp_server_name
        elif tool.handler_module_path and star_map.get(tool.handler_module_path):
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
            "readonly": readonly,
            "builtin_config_statuses": builtin_config_statuses,
            "builtin_config_tags": builtin_config_tags,
        }
        if not readonly:
            perms_store = sp.get(
                "tool_permissions",
                {},
                scope="global",
                scope_id="global",
            )
            defaults = (
                perms_store.get("_default", {}) if isinstance(perms_store, dict) else {}
            )
            configured = tool.name in defaults
            permission = defaults[tool.name] if configured else "member"
            tool_info["permission"] = permission
            tool_info["permission_configured"] = configured
        return tool_info
