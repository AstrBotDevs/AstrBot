import traceback
from typing import Any

from astrbot import logger
from astrbot.core.agent.mcp_client import MCPTool, validate_mcp_stdio_config
from astrbot.core.agent.tool import get_parallel_blocked_reason, get_tool_id
from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
from astrbot.core.star.plugin_catalog import PluginCatalog
from astrbot.core.star.star import PluginRegistry
from astrbot.core.tools.function_tool_manager import FunctionToolManager
from astrbot.core.utils.shared_preferences import SharedPreferences


class ToolsServiceError(Exception):
    pass


class ToolsService:
    PARALLEL_PREFERENCE_KEY = "tool_parallel_execution"
    DEFAULT_PARALLEL_MAX_CALLS = 8

    def __init__(
        self,
        tool_manager: FunctionToolManager,
        preferences: SharedPreferences,
        config_manager: AstrBotConfigManager,
        plugin_catalog: PluginRegistry,
    ) -> None:
        self.tool_mgr = tool_manager
        self.preferences = preferences
        self.config_manager = config_manager
        self.plugin_catalog = plugin_catalog

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

    async def update_mcp_server(self, old_name: str, server_data: Any) -> str:
        try:
            name = server_data.get("name", "")

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
            config = server_data.get("config", None)

            if not isinstance(config, dict) or not config:
                raise ToolsServiceError("Invalid MCP server configuration")

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
            existing_names = {tool.name for tool in tools}
            for tool in self.tool_mgr.iter_builtin_tools():
                if tool.name not in existing_names:
                    tools.append(tool)

            config_entries = self._get_config_entries()
            perms_store = await self.preferences.global_get("tool_permissions", {})
            defaults = (
                perms_store.get("_default", {}) if isinstance(perms_store, dict) else {}
            )
            parallel_settings = await self.get_parallel_settings()
            tools_dict = []
            for tool in tools:
                tools_dict.append(
                    self._serialize_tool(
                        tool,
                        config_entries,
                        defaults=defaults,
                        parallel_settings=parallel_settings,
                    )
                )
            return tools_dict
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise ToolsServiceError(f"Failed to get tool list: {exc!s}") from exc

    async def get_parallel_settings(self) -> dict[str, Any]:
        """Return the persisted global parallel-tool policy."""
        raw = await self.preferences.global_get(self.PARALLEL_PREFERENCE_KEY, {})
        if not isinstance(raw, dict):
            raw = {}
        allowed_raw = raw.get("allowed_tool_ids", [])
        allowed = sorted(
            {
                value.strip()
                for value in allowed_raw
                if isinstance(value, str) and value.strip()
            }
            if isinstance(allowed_raw, list)
            else set()
        )
        try:
            max_calls = max(
                1,
                min(
                    self.DEFAULT_PARALLEL_MAX_CALLS,
                    int(raw.get("max_calls", self.DEFAULT_PARALLEL_MAX_CALLS)),
                ),
            )
        except TypeError, ValueError:
            max_calls = self.DEFAULT_PARALLEL_MAX_CALLS
        try:
            mcp_max_concurrency = max(
                1,
                min(
                    self.DEFAULT_PARALLEL_MAX_CALLS,
                    int(raw.get("mcp_max_concurrency", 1)),
                ),
            )
        except TypeError, ValueError:
            mcp_max_concurrency = 1
        return {
            "enabled": bool(raw.get("enabled", False)),
            "allowed_tool_ids": allowed,
            "max_calls": max_calls,
            "mcp_max_concurrency": mcp_max_concurrency,
        }

    async def set_parallel_enabled(self, enabled: bool) -> str:
        """Enable or disable native parallel tool execution globally."""
        settings = await self.get_parallel_settings()
        settings["enabled"] = bool(enabled)
        await self.preferences.global_put(self.PARALLEL_PREFERENCE_KEY, settings)
        return (
            "Parallel tool execution enabled."
            if enabled
            else "Parallel tool execution disabled."
        )

    async def toggle_tool_parallel(self, data: Any) -> str:
        """Persist administrator opt-in for one current tool identity."""
        tool_id = data.get("tool_id") if isinstance(data, dict) else None
        enabled = data.get("enabled") if isinstance(data, dict) else None
        if not isinstance(tool_id, str) or not tool_id or not isinstance(enabled, bool):
            raise ToolsServiceError("tool_id and enabled are required")

        tools = list(self.tool_mgr.func_list) + list(self.tool_mgr.iter_builtin_tools())
        tool = next(
            (candidate for candidate in tools if get_tool_id(candidate) == tool_id),
            None,
        )
        if tool is None:
            raise ToolsServiceError(f"Tool '{tool_id}' not found")
        blocked_reason = get_parallel_blocked_reason(tool)
        if enabled and blocked_reason is not None:
            raise ToolsServiceError(blocked_reason)

        settings = await self.get_parallel_settings()
        allowed = set(settings["allowed_tool_ids"])
        if enabled:
            allowed.add(tool_id)
        else:
            allowed.discard(tool_id)
        settings["allowed_tool_ids"] = sorted(allowed)
        await self.preferences.global_put(self.PARALLEL_PREFERENCE_KEY, settings)
        return f"Tool '{tool.name}' parallel execution {'enabled' if enabled else 'disabled'}."

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

            if self.tool_mgr.is_builtin_tool(tool_name):
                raise ToolsServiceError(
                    "Builtin tools do not support per-tool permission configuration."
                )

            if not any(t.name == tool_name for t in self.tool_mgr.func_list):
                raise ToolsServiceError(f"Tool '{tool_name}' not found")

            perms_store = await self.preferences.global_get("tool_permissions", {})
            if not isinstance(perms_store, dict):
                perms_store = {}
            defaults = perms_store.get("_default", {})
            if not isinstance(defaults, dict):
                defaults = {}
            defaults[tool_name] = permission
            perms_store["_default"] = defaults
            await self.preferences.global_put("tool_permissions", perms_store)

            return f"Tool '{tool_name}' permission set to {permission}"
        except ToolsServiceError:
            raise
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise ToolsServiceError(
                f"Failed to update tool permission: {exc!s}"
            ) from exc

    async def toggle_tool(self, data: Any) -> str:
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
                    ok = await self.tool_mgr.activate_llm_tool(tool_name)
                except ValueError as exc:
                    raise ToolsServiceError(
                        f"Failed to activate tool: {exc!s}"
                    ) from exc
            else:
                ok = await self.tool_mgr.deactivate_llm_tool(tool_name)

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
            if key in ["name", "active", "tools", "errlogs"]:
                continue
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
            if key in ["name", "active", "tools", "errlogs"]:
                continue
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
            await self.tool_mgr.enable_mcp_server(
                name, server_config, timeout_seconds=30
            )
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
            await self.tool_mgr.disable_mcp_server(old_name, timeout_seconds=10)
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
            await self.tool_mgr.enable_mcp_server(
                name, server_config, timeout_seconds=30
            )
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
            await self.tool_mgr.disable_mcp_server(name, timeout_seconds=10)
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
        conf_list = self.config_manager.get_conf_list()
        conf_name_map = {conf["id"]: conf["name"] for conf in conf_list}
        config_entries = []
        for conf_id, conf in self.config_manager.confs.items():
            config_entries.append(
                {
                    "conf_id": conf_id,
                    "conf_name": conf_name_map.get(conf_id, conf_id),
                    "config": conf,
                }
            )
        return config_entries

    def _serialize_tool(
        self,
        tool,
        config_entries: list[dict],
        *,
        defaults: dict[str, str],
        parallel_settings: dict[str, Any] | None = None,
    ) -> dict:
        readonly = False
        builtin_config_statuses = []
        builtin_config_tags = []
        if self.tool_mgr.is_builtin_tool(tool.name):
            origin = "builtin"
            origin_name = "AstrBot Core"
            readonly = True
            builtin_config_statuses = self.tool_mgr.get_builtin_tool_config_statuses(
                tool.name,
                config_entries,
            )
            builtin_config_tags = [
                status for status in builtin_config_statuses if status["enabled"]
            ]
        elif isinstance(tool, MCPTool):
            origin = "mcp"
            origin_name = tool.mcp_server_name
        elif star := self._resolve_plugin_owner(tool):
            origin = "plugin"
            origin_name = star.name
        else:
            origin = "unknown"
            origin_name = "unknown"

        tool_info = {
            "name": tool.name,
            "tool_id": get_tool_id(tool),
            "description": tool.description,
            "parameters": tool.parameters,
            "active": tool.active,
            "origin": origin,
            "origin_name": origin_name,
            "readonly": readonly,
            "builtin_config_statuses": builtin_config_statuses,
            "builtin_config_tags": builtin_config_tags,
        }
        settings = parallel_settings or {
            "enabled": False,
            "allowed_tool_ids": [],
            "max_calls": self.DEFAULT_PARALLEL_MAX_CALLS,
            "mcp_max_concurrency": 1,
        }
        tool_id = tool_info["tool_id"]
        blocked_reason = get_parallel_blocked_reason(tool)
        tool_info.update(
            {
                "parallel_policy": getattr(tool, "parallel_policy", "unknown"),
                "parallel_eligible": blocked_reason is None,
                "parallel_blocked_reason": blocked_reason,
                "parallel_enabled": tool_id in settings["allowed_tool_ids"],
                "parallel_execution_enabled": settings["enabled"],
                "parallel_max_calls": settings["max_calls"],
                "parallel_mcp_max_concurrency": settings["mcp_max_concurrency"],
            }
        )
        if not readonly:
            configured = tool.name in defaults
            permission = (
                defaults[tool.name]
                if configured
                else self.tool_mgr._default_permission(tool.name)
            )
            tool_info["permission"] = permission
            tool_info["permission_configured"] = configured
        return tool_info

    def _resolve_plugin_owner(self, tool: Any) -> Any | None:
        """Resolve a plugin by exact path or strict package-prefix ownership."""
        module_path = getattr(tool, "handler_module_path", None)
        if not isinstance(module_path, str) or not module_path:
            return None
        exact = self.plugin_catalog.get_by_module(module_path)
        if exact is not None:
            return exact

        matches = []
        for metadata in self.plugin_catalog.all():
            try:
                prefix = PluginCatalog.module_prefix(metadata)
            except TypeError, ValueError:
                continue
            if PluginCatalog.is_plugin_module_path(module_path, prefix):
                matches.append(metadata)
        return matches[0] if len(matches) == 1 else None
