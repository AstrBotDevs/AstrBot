"""EULA (最终用户许可协议) 相关路由

提供 EULA 内容获取、签署状态查询和签署确认功能。
签署状态存储在 cmd_config.json 中。
"""

import os
from datetime import datetime, timezone

from quart import g

from astrbot.core.utils.astrbot_path import get_astrbot_path, get_astrbot_root

from .route import Response, Route, RouteContext


class EulaRoute(Route):
    """EULA 路由类"""

    def __init__(
        self,
        context: RouteContext,
    ) -> None:
        super().__init__(context)
        self.routes = {
            "/eula/status": ("GET", self.get_eula_status),
            "/eula/content": ("GET", self.get_eula_content),
            "/eula/accept": ("POST", self.accept_eula),
        }
        self.register_routes()

    async def get_eula_status(self):
        """获取 EULA 签署状态

        从 cmd_config.json 中读取 eula 配置项

        Returns:
            包含 accepted 状态和签署时间的响应
        """
        try:
            eula_config = self.config.get("eula", {})

            if eula_config.get("accepted"):
                return (
                    Response()
                    .ok(
                        {
                            "accepted": True,
                            "accepted_at": eula_config.get("accepted_at"),
                            "accepted_by": eula_config.get("accepted_by"),
                        }
                    )
                    .__dict__
                )

            return Response().ok({"accepted": False}).__dict__
        except Exception as e:
            return Response().error(f"获取 EULA 状态失败: {e!s}").__dict__

    async def get_eula_content(self):
        """获取 EULA 内容

        Returns:
            EULA markdown 内容
        """
        try:
            # 尝试从不同位置读取 EULA.md
            # 优先级: 项目源码目录 > 根目录
            eula_paths = [
                os.path.join(get_astrbot_path(), "EULA.md"),
                os.path.join(get_astrbot_root(), "EULA.md"),
            ]

            eula_content = None
            for path in eula_paths:
                if os.path.exists(path):
                    with open(path, encoding="utf-8") as f:
                        eula_content = f.read()
                    break

            if eula_content is None:
                return Response().error("EULA 文件未找到").__dict__

            return Response().ok({"content": eula_content}).__dict__
        except Exception as e:
            return Response().error(f"获取 EULA 内容失败: {e!s}").__dict__

    async def accept_eula(self):
        """确认签署 EULA

        将签署状态保存到 cmd_config.json 中

        Returns:
            签署结果
        """
        try:
            username = getattr(g, "username", "unknown")
            now = datetime.now(timezone.utc).isoformat()

            # 更新配置
            self.config["eula"] = {
                "accepted": True,
                "accepted_at": now,
                "accepted_by": username,
            }
            self.config.save_config()

            return (
                Response()
                .ok(
                    {
                        "accepted": True,
                        "accepted_at": now,
                        "accepted_by": username,
                    },
                    "EULA 已签署",
                )
                .__dict__
            )
        except Exception as e:
            return Response().error(f"签署 EULA 失败: {e!s}").__dict__
