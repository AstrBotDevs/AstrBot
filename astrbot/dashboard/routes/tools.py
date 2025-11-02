import traceback

from pydantic import BaseModel

from astrbot.core import logger
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.star import star_map

from .route import Response, Route, RouteContext

DEFAULT_MCP_CONFIG = {"mcpServers": {}}


class MCPServerRequest(BaseModel):
    name: str
    command: str | None = None
    args: list | None = None
    env: dict[str, str] | None = None
    active: bool = True


class MCPServerUpdateRequest(BaseModel):
    name: str
    old_name: str
    command: str | None = None
    args: list | None = None
    env: dict[str, str] | None = None
    active: bool = True


class MCPServerDeleteRequest(BaseModel):
    name: str


class MCPTestRequest(BaseModel):
    command: str
    args: list | None = None
    env: dict[str, str] | None = None


class ToggleToolRequest(BaseModel):
    tool_name: str
    enabled: bool


class SyncProviderRequest(BaseModel):
    provider_id: str


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
                for (
                    name_key,
                    mcp_client,
                ) in self.tool_mgr.mcp_client_dict.items():
                    if name_key == name:
                        server_info["tools"] = [tool.name for tool in mcp_client.tools]
                        server_info["errlogs"] = mcp_client.server_errlogs
                        break
                else:
                    server_info["tools"] = []

                servers.append(server_info)

            return Response.ok(servers)
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response.error(f"获取 MCP 服务器列表失败: {e!s}")

    async def add_mcp_server(self, server_data: MCPServerRequest):
        try:
            name = server_data.name

            # 检查必填字段
            if not name:
                return Response.error("服务器名称不能为空")

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
                return Response.error("必须提供有效的服务器配置")

            config = self.tool_mgr.load_mcp_config()

            if name in config["mcpServers"]:
                return Response.error(f"服务器 {name} 已存在")

            config["mcpServers"][name] = server_config

            if self.tool_mgr.save_mcp_config(config):
                try:
                    await self.tool_mgr.enable_mcp_server(
                        name,
                        server_config,
                        timeout=30,
                    )
                except TimeoutError:
                    return Response.error(f"启用 MCP 服务器 {name} 超时。")
                except Exception as e:
                    logger.error(traceback.format_exc())
                    return (
                        Response.error(f"启用 MCP 服务器 {name} 失败: {e!s}")
                    )
                return Response.ok(None, f"成功添加 MCP 服务器 {name}")
            return Response.error("保存配置失败")
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response.error(f"添加 MCP 服务器失败: {e!s}")

    async def update_mcp_server(self, server_data: dict):
        try:
            name = server_data.get("name", "")

            if not name:
                return Response.error("服务器名称不能为空")

            config = self.tool_mgr.load_mcp_config()

            if name not in config["mcpServers"]:
                return Response.error(f"服务器 {name} 不存在")

            # 获取活动状态
            active = server_data.get(
                "active",
                config["mcpServers"][name].get("active", True),
            )

            # 创建新的配置对象
            server_config = {"active": active}

            # 仅更新活动状态的特殊处理
            only_update_active = True

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
                    only_update_active = False

            # 如果只更新活动状态，保留原始配置
            if only_update_active:
                for key, value in config["mcpServers"][name].items():
                    if key != "active":  # 除了active之外的所有字段都保留
                        server_config[key] = value

            config["mcpServers"][name] = server_config

            if self.tool_mgr.save_mcp_config(config):
                # 处理MCP客户端状态变化
                if active:
                    if name in self.tool_mgr.mcp_client_dict or not only_update_active:
                        try:
                            await self.tool_mgr.disable_mcp_server(name, timeout=10)
                        except TimeoutError as e:
                            return Response.error(f"启用前停用 MCP 服务器时 {name} 超时: {e!s}")
                        except Exception as e:
                            logger.error(traceback.format_exc())
                            return Response.error(f"启用前停用 MCP 服务器时 {name} 失败: {e!s}")
                    try:
                        await self.tool_mgr.enable_mcp_server(
                            name,
                            config["mcpServers"][name],
                            timeout=30,
                        )
                    except TimeoutError:
                        return (
                            Response.error(f"启用 MCP 服务器 {name} 超时。")
                        )
                    except Exception as e:
                        logger.error(traceback.format_exc())
                        return Response.error(f"启用 MCP 服务器 {name} 失败: {e!s}")
                # 如果要停用服务器
                elif name in self.tool_mgr.mcp_client_dict:
                    try:
                        await self.tool_mgr.disable_mcp_server(name, timeout=10)
                    except TimeoutError:
                        return (
                            Response.error(f"停用 MCP 服务器 {name} 超时。")
                        )
                    except Exception as e:
                        logger.error(traceback.format_exc())
                        return Response.error(f"停用 MCP 服务器 {name} 失败: {e!s}")

                return Response.ok(None, f"成功更新 MCP 服务器 {name}")
            return Response.error("保存配置失败")
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response.error(f"更新 MCP 服务器失败: {e!s}")

    async def delete_mcp_server(self, server_data: MCPServerDeleteRequest):
        try:
            name = server_data.name

            if not name:
                return Response.error("服务器名称不能为空")

            config = self.tool_mgr.load_mcp_config()

            if name not in config["mcpServers"]:
                return Response.error(f"服务器 {name} 不存在")

            del config["mcpServers"][name]

            if self.tool_mgr.save_mcp_config(config):
                if name in self.tool_mgr.mcp_client_dict:
                    try:
                        await self.tool_mgr.disable_mcp_server(name, timeout=10)
                    except TimeoutError:
                        return (
                            Response.error(f"停用 MCP 服务器 {name} 超时。")
                        )
                    except Exception as e:
                        logger.error(traceback.format_exc())
                        return Response.error(f"停用 MCP 服务器 {name} 失败: {e!s}")
                return Response.ok(None, f"成功删除 MCP 服务器 {name}")
            return Response.error("保存配置失败")
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response.error(f"删除 MCP 服务器失败: {e!s}")

    async def test_mcp_connection(self, server_data: dict):
        """测试 MCP 服务器连接"""
        try:
            config = server_data.get("mcp_server_config", None)

            if not isinstance(config, dict) or not config:
                return Response.error("无效的 MCP 服务器配置")

            if "mcpServers" in config:
                keys = list(config["mcpServers"].keys())
                if not keys:
                    return Response.error("MCP 服务器配置不能为空")
                if len(keys) > 1:
                    return Response.error("一次只能配置一个 MCP 服务器配置")
                config = config["mcpServers"][keys[0]]
            elif not config:
                return Response.error("MCP 服务器配置不能为空")

            tools_name = await self.tool_mgr.test_mcp_server_connection(config)
            return (
                Response.ok(data=tools_name, message="🎉 MCP 服务器可用！")
            )

        except Exception as e:
            logger.error(traceback.format_exc())
            return Response.error(f"测试 MCP 连接失败: {e!s}")

    async def get_tool_list(self):
        """获取所有注册的工具列表"""
        try:
            tools = self.tool_mgr.func_list
            tools_dict = [tool() for tool in tools]
            return Response.ok(data=tools_dict)
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response.error(f"获取工具列表失败: {e!s}")

    async def toggle_tool(self, data: dict):
        """启用或停用指定的工具"""
        try:
            tool_name = data.get("name")
            action = data.get("activate")  # True or False

            if not tool_name or action is None:
                return Response.error("缺少必要参数: name 或 action")

            if action:
                try:
                    ok = self.tool_mgr.activate_llm_tool(tool_name, star_map=star_map)
                except ValueError as e:
                    return Response.error(f"启用工具失败: {e!s}")
            else:
                ok = self.tool_mgr.deactivate_llm_tool(tool_name)

            if ok:
                return Response.ok(None, "操作成功。")
            return Response.error(f"工具 {tool_name} 不存在或操作失败。")

        except Exception as e:
            logger.error(traceback.format_exc())
            return Response.error(f"操作工具失败: {e!s}")

    async def sync_provider(self, data: dict):
        """同步 MCP 提供者配置"""
        try:
            provider_name = data.get("name")  # modelscope, or others
            match provider_name:
                case "modelscope":
                    access_token = data.get("access_token", "")
                    await self.tool_mgr.sync_modelscope_mcp_servers(access_token)
                case _:
                    return Response.error(f"未知: {provider_name}")

            return Response.ok(message="同步成功")
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response.error(f"同步失败: {e!s}")
