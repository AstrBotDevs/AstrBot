import asyncio
import copy
import traceback
from typing import Any

from mcp.types import PromptReference, ResourceTemplateReference

from astrbot import logger
from astrbot.core.agent.mcp_client import (
    MCPClient,
    MCPTool,
    validate_mcp_server_config,
)
from astrbot.core.agent.tool import get_parallel_blocked_reason, get_tool_id
from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
from astrbot.core.star.plugin_catalog import PluginCatalog
from astrbot.core.star.star import PluginRegistry
from astrbot.core.tools.function_tool_manager import FunctionToolManager
from astrbot.core.utils.error_redaction import safe_error
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
        self._oauth_probe_tasks: dict[str, asyncio.Task[None]] = {}

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
                    if key not in {"active", "headers"}:
                        server_info[key] = value
                # Headers are write-only. A Dashboard list response must never
                # disclose an Authorization value or another deployment secret.
                server_info["headers_configured"] = bool(server_config.get("headers"))

                for name_key, runtime in self.tool_mgr.mcp_server_runtime_view.items():
                    if name_key == name:
                        mcp_client = runtime.client
                        server_info["tools"] = [tool.name for tool in mcp_client.tools]
                        server_info["errlogs"] = mcp_client.server_errlogs
                        server_info.update(mcp_client.runtime_status())
                        if server_config.get("auth_ref"):
                            server_info["auth_status"] = "configured"
                        break
                else:
                    server_info["tools"] = []
                    server_info["connection_status"] = "disconnected"
                    server_info["auth_status"] = "not_configured"

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

    def _mcp_runtime(self, name: str):
        runtime = self.tool_mgr.mcp_server_runtime_view.get(name)
        if runtime is None or runtime.client.connection_status != "connected":
            raise ToolsServiceError("MCP server is not connected.")
        return runtime

    @staticmethod
    def _mcp_model(value: Any) -> Any:
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        if isinstance(value, list):
            return [ToolsService._mcp_model(item) for item in value]
        if isinstance(value, dict):
            return {
                str(key): ToolsService._mcp_model(item) for key, item in value.items()
            }
        return value

    async def get_mcp_runtime_catalog(self, name: str) -> dict[str, Any]:
        runtime = self._mcp_runtime(name)
        client = runtime.client
        return {
            "status": client.runtime_status(),
            "resources": self._mcp_model(client.resources),
            "resource_templates": self._mcp_model(client.resource_templates),
            "prompts": self._mcp_model(client.prompts),
        }

    async def list_mcp_resources(self, name: str) -> dict[str, Any]:
        """List only the current, explicitly browsable resource catalog."""
        client = self._mcp_runtime(name).client
        await client.list_resources()
        return {"source": name, "resources": self._mcp_model(client.resources)}

    async def list_mcp_resource_templates(self, name: str) -> dict[str, Any]:
        """List the current resource-template catalog without reading content."""
        client = self._mcp_runtime(name).client
        await client.list_resource_templates()
        return {
            "source": name,
            "resource_templates": self._mcp_model(client.resource_templates),
        }

    async def list_mcp_prompts(self, name: str) -> dict[str, Any]:
        """List the current prompt catalog without invoking a prompt."""
        client = self._mcp_runtime(name).client
        await client.list_prompts()
        return {"source": name, "prompts": self._mcp_model(client.prompts)}

    async def read_mcp_resource(self, name: str, uri: str) -> dict[str, Any]:
        if not uri:
            raise ToolsServiceError("Resource URI cannot be empty.")
        result = await self._mcp_runtime(name).client.read_resource(uri)
        # Resource data is untrusted external content. Dashboard clients render
        # it as plain data, never as trusted HTML or an automatic LLM context.
        return {"source": name, "resource": self._mcp_model(result)}

    async def get_mcp_prompt(
        self, name: str, prompt_name: str, arguments: dict[str, str] | None
    ) -> dict[str, Any]:
        if not prompt_name:
            raise ToolsServiceError("Prompt name cannot be empty.")
        result = await self._mcp_runtime(name).client.get_prompt(prompt_name, arguments)
        return {"source": name, "prompt": self._mcp_model(result)}

    async def complete_mcp(
        self,
        name: str,
        reference: dict[str, Any],
        argument: dict[str, str],
        context_arguments: dict[str, str] | None,
    ) -> dict[str, Any]:
        try:
            reference_type = reference.get("type")
            if reference_type == "ref/resource":
                resolved_reference = ResourceTemplateReference.model_validate(reference)
            elif reference_type == "ref/prompt":
                resolved_reference = PromptReference.model_validate(reference)
            else:
                raise ValueError("Unsupported completion reference.")
        except (AttributeError, ValueError) as exc:
            raise ToolsServiceError("Invalid completion reference.") from exc
        result = await self._mcp_runtime(name).client.complete(
            resolved_reference, argument, context_arguments
        )
        return {"source": name, "completion": self._mcp_model(result)}

    async def get_mcp_auth_status(self, name: str) -> dict[str, Any]:
        config = self.get_mcp_server_config(name)
        if config is None:
            raise ToolsServiceError("MCP server does not exist.")
        auth_ref = config.get("auth_ref")
        if not auth_ref:
            return {"configured": False}
        status = await self.tool_mgr.mcp_auth_store.status(f"{name}:{auth_ref}")
        return {"configured": True, **status}

    async def start_mcp_authorization(self, name: str) -> dict[str, Any]:
        config = self.get_mcp_server_config(name)
        if config is None or not config.get("auth_ref"):
            raise ToolsServiceError("This MCP server has no OAuth configuration.")
        identity = f"{name}:{config['auth_ref']}"
        runtime = self.tool_mgr.mcp_server_runtime_view.get(name)
        if runtime is not None and runtime.client.connection_status == "connected":
            client = runtime.client
            asyncio.create_task(client.list_tools_and_save(), name=f"mcp-oauth:{name}")
        else:
            # A protected endpoint may fail its first catalog request with 401,
            # so it has no runtime entry yet. Keep an owner task alive while the
            # SDK OAuth provider performs discovery, PKCE, and callback waiting.
            existing = self._oauth_probe_tasks.get(identity)
            if existing is None or existing.done():
                client = MCPClient(
                    interaction_coordinator=self.tool_mgr.mcp_interaction_coordinator,
                    auth_store=self.tool_mgr.mcp_auth_store,
                    auth_coordinator=self.tool_mgr.mcp_authorization_coordinator,
                )

                async def probe() -> None:
                    authorized = False
                    try:
                        await client.connect_to_server(
                            config, name, watch_catalog=False
                        )
                        authorized = True
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        logger.debug("MCP OAuth probe ended: %s", safe_error("", exc))
                    finally:
                        await client.cleanup()
                        if authorized and config.get("active", True):
                            try:
                                await self.tool_mgr.enable_mcp_server(name, config)
                            except Exception as exc:
                                logger.warning(
                                    "MCP server %s could not start after OAuth: %s",
                                    name,
                                    safe_error("", exc),
                                )

                self._oauth_probe_tasks[identity] = asyncio.create_task(
                    probe(), name=f"mcp-oauth:{name}"
                )
        authorization_url = (
            await self.tool_mgr.mcp_authorization_coordinator.wait_for_url(identity)
        )
        if authorization_url is None:
            return {"status": "pending"}
        return {
            "status": "authorization_required",
            "authorization_url": authorization_url,
        }

    async def complete_mcp_authorization(
        self, name: str, code: str, state: str | None, issuer: str | None
    ) -> bool:
        config = self.get_mcp_server_config(name)
        if config is None or not config.get("auth_ref"):
            return False
        return await self.tool_mgr.mcp_authorization_coordinator.complete_callback(
            f"{name}:{config['auth_ref']}", code, state, issuer
        )

    async def revoke_mcp_authorization(self, name: str) -> None:
        config = self.get_mcp_server_config(name)
        if config is None or not config.get("auth_ref"):
            raise ToolsServiceError("This MCP server has no OAuth configuration.")
        identity = f"{name}:{config['auth_ref']}"
        task = self._oauth_probe_tasks.pop(identity, None)
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if name in self.tool_mgr.mcp_server_runtime_view:
            await self.tool_mgr.disable_mcp_server(name)
        await self.tool_mgr.mcp_auth_store.revoke(identity)

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

            if not server_config.get("auth_ref"):
                try:
                    await self.tool_mgr.test_mcp_server_connection(server_config)
                except Exception as exc:
                    logger.error(traceback.format_exc())
                    logger.warning(
                        "MCP connection test failed: %s", safe_error("", exc)
                    )
                    raise ToolsServiceError("MCP connection test failed.") from exc

            config["mcpServers"][name] = server_config

            if self.tool_mgr.save_mcp_config(config):
                if server_config.get("auth_ref"):
                    return (
                        f"Added MCP server {name}. Authorize it before it is connected."
                    )
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
            parallel_settings = await self.get_parallel_settings()
            tools_dict = []
            for tool in tools:
                tools_dict.append(
                    await self._serialize_tool(
                        tool,
                        config_entries,
                        defaults={},
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
        raw_config = server_data.get("config")
        if isinstance(raw_config, dict):
            server_config = dict(raw_config)
        else:
            server_config = {
                key: value
                for key, value in server_data.items()
                if key not in {"name", "active", "tools", "errlogs", "config"}
            }
        server_config["active"] = server_data.get("active", True)
        return any(key != "active" for key in server_config), server_config

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

        # Header values are deliberately absent from the Dashboard GET result.
        # Omission preserves the existing secret; an explicit empty object is
        # the user's intentional request to remove headers.
        if (
            isinstance(old_config, dict)
            and "headers" in old_config
            and "headers" not in server_config
        ):
            server_config["headers"] = copy.deepcopy(old_config["headers"])

        if only_update_active and isinstance(old_config, dict):
            for key, value in old_config.items():
                if key != "active":
                    server_config[key] = value

        return only_update_active, server_config

    @staticmethod
    def _validate_server_config(server_config: dict) -> None:
        try:
            validate_mcp_server_config(server_config)
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

    async def _serialize_tool(
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
        del defaults
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
