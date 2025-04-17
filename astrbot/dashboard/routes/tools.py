import os
import json
import aiohttp
import traceback
from .route import Route, Response, RouteContext
from quart import request
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core import logger

DEFAULT_MCP_CONFIG = {"mcpServers": {}}


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
            "/tools/mcp/market": ("GET", self.get_mcp_markets),
        }
        self.register_routes()
        self.tool_mgr = self.core_lifecycle.provider_manager.llm_tools

    @property
    def mcp_config_path(self):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        data_dir = os.path.abspath(os.path.join(current_dir, "../../../data"))
        return os.path.join(data_dir, "mcp_server.json")

    def load_mcp_config(self):
        if not os.path.exists(self.mcp_config_path):
            # 配置文件不存在，创建默认配置
            os.makedirs(os.path.dirname(self.mcp_config_path), exist_ok=True)
            with open(self.mcp_config_path, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_MCP_CONFIG, f, ensure_ascii=False, indent=4)
            return DEFAULT_MCP_CONFIG

        try:
            with open(self.mcp_config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载 MCP 配置失败: {e}")
            return DEFAULT_MCP_CONFIG

    def save_mcp_config(self, config):
        try:
            with open(self.mcp_config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=4)
            return True
        except Exception as e:
            logger.error(f"保存 MCP 配置失败: {e}")
            return False

    async def get_mcp_servers(self):
        try:
            config = self.load_mcp_config()
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

            return Response().ok(servers).__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(f"获取 MCP 服务器列表失败: {str(e)}").__dict__

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

            config = self.load_mcp_config()

            if name in config["mcpServers"]:
                return Response().error(f"服务器 {name} 已存在").__dict__

            config["mcpServers"][name] = server_config

            if self.save_mcp_config(config):
                # 动态初始化新MCP客户端
                await self.tool_mgr.mcp_service_queue.put(
                    {
                        "type": "init",
                        "name": name,
                        "cfg": config["mcpServers"][name],
                    }
                )
                return Response().ok(None, f"成功添加 MCP 服务器 {name}").__dict__
            else:
                return Response().error("保存配置失败").__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(f"添加 MCP 服务器失败: {str(e)}").__dict__

    async def update_mcp_server(self):
        try:
            server_data = await request.json

            name = server_data.get("name", "")

            if not name:
                return Response().error("服务器名称不能为空").__dict__

            config = self.load_mcp_config()

            if name not in config["mcpServers"]:
                return Response().error(f"服务器 {name} 不存在").__dict__

            # 获取活动状态
            active = server_data.get(
                "active", config["mcpServers"][name].get("active", True)
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

            if self.save_mcp_config(config):
                # 处理MCP客户端状态变化
                if active:
                    # 如果要激活服务器或者配置已更改
                    if name in self.tool_mgr.mcp_client_dict or not only_update_active:
                        await self.tool_mgr.mcp_service_queue.put(
                            {
                                "type": "terminate",
                                "name": name,
                            }
                        )
                        await self.tool_mgr.mcp_service_queue.put(
                            {
                                "type": "init",
                                "name": name,
                                "cfg": config["mcpServers"][name],
                            }
                        )
                    else:
                        # 客户端不存在，初始化
                        await self.tool_mgr.mcp_service_queue.put(
                            {
                                "type": "init",
                                "name": name,
                                "cfg": config["mcpServers"][name],
                            }
                        )
                else:
                    # 如果要停用服务器
                    if name in self.tool_mgr.mcp_client_dict:
                        self.tool_mgr.mcp_service_queue.put_nowait(
                            {
                                "type": "terminate",
                                "name": name,
                            }
                        )

                return Response().ok(None, f"成功更新 MCP 服务器 {name}").__dict__
            else:
                return Response().error("保存配置失败").__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(f"更新 MCP 服务器失败: {str(e)}").__dict__

    async def delete_mcp_server(self):
        try:
            server_data = await request.json
            name = server_data.get("name", "")

            if not name:
                return Response().error("服务器名称不能为空").__dict__

            config = self.load_mcp_config()

            if name not in config["mcpServers"]:
                return Response().error(f"服务器 {name} 不存在").__dict__

            # 删除服务器配置
            del config["mcpServers"][name]

            if self.save_mcp_config(config):
                # 关闭并删除MCP客户端
                if name in self.tool_mgr.mcp_client_dict:
                    self.tool_mgr.mcp_service_queue.put_nowait(
                        {
                            "type": "terminate",
                            "name": name,
                        }
                    )

                return Response().ok(None, f"成功删除 MCP 服务器 {name}").__dict__
            else:
                return Response().error("保存配置失败").__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(f"删除 MCP 服务器失败: {str(e)}").__dict__

    async def get_mcp_markets(self):
        page = request.args.get("page", 1, type=int)
        page_size = request.args.get("page_size", 10, type=int)
        BASE_URL = "https://api.soulter.top/astrbot/mcpservers?page={}&page_size={}".format(
            page,
            page_size,
        )
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{BASE_URL}") as response:
                    if response.status == 200:
                        data = await response.json()
                        return Response().ok(data["data"]).__dict__
                    else:
                        return (
                            Response()
                            .error(f"获取市场数据失败: HTTP {response.status}")
                            .__dict__
                        )
        except Exception as _:
            logger.error(traceback.format_exc())
        return Response().error("获取市场数据失败").__dict__