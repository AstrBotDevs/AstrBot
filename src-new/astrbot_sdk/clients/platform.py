"""平台客户端模块。

提供与聊天平台交互的能力，支持发送消息和获取群组信息。

与旧版对比：
    旧版 (src/astrbot_sdk/api/star/context.py):
        Context.send_message(session, message_chain)
        # 使用 MessageChain 构建复杂消息

    新版:
        Context.platform.send(session, text)
        Context.platform.send_image(session, image_url)
        Context.platform.get_members(session)

主要差异：
    1. 新版拆分为 send() 和 send_image()，简化使用
    2. 新版移除 MessageChain，直接使用文本字符串
    3. 新增 get_members() 获取群成员列表

TODO (相比旧版缺失的功能):
    - 缺少 MessageChain 复杂消息链支持（多段文本、@提及、表情等）
    - 缺少发送音频、视频、文件等多媒体消息
    - 缺少消息撤回、编辑等操作
    - 缺少获取用户详细信息的方法
"""

from __future__ import annotations

from typing import Any

from ._proxy import CapabilityProxy


class PlatformClient:
    """平台消息客户端。

    提供向聊天平台发送消息和获取信息的能力。

    Attributes:
        _proxy: CapabilityProxy 实例，用于远程能力调用
    """

    def __init__(self, proxy: CapabilityProxy) -> None:
        """初始化平台客户端。

        Args:
            proxy: CapabilityProxy 实例
        """
        self._proxy = proxy

    async def send(self, session: str, text: str) -> dict[str, Any]:
        """发送文本消息。

        向指定的会话（用户或群组）发送文本消息。

        Args:
            session: 统一消息来源标识 (UMO)，格式如 "platform:instance:user_id"
            text: 要发送的文本内容

        Returns:
            发送结果，可能包含消息 ID 等信息

        示例:
            # 发送消息到当前会话
            await ctx.platform.send(event.session, "收到您的消息！")
        """
        return await self._proxy.call(
            "platform.send",
            {"session": session, "text": text},
        )

    async def send_image(self, session: str, image_url: str) -> dict[str, Any]:
        """发送图片消息。

        向指定的会话发送图片，支持 URL 或本地路径。

        Args:
            session: 统一消息来源标识 (UMO)
            image_url: 图片 URL 或本地文件路径

        Returns:
            发送结果

        示例:
            await ctx.platform.send_image(
                event.session,
                "https://example.com/image.png"
            )
        """
        return await self._proxy.call(
            "platform.send_image",
            {"session": session, "image_url": image_url},
        )

    async def get_members(self, session: str) -> list[dict[str, Any]]:
        """获取群组成员列表。

        获取指定群组的成员信息列表。注意仅对群组会话有效。

        Args:
            session: 群组会话的统一消息来源标识 (UMO)

        Returns:
            成员信息列表，每个成员是一个字典，可能包含：
            - user_id: 用户 ID
            - nickname: 昵称
            - role: 角色 (owner, admin, member)

        示例:
            members = await ctx.platform.get_members(event.session)
            for member in members:
                print(f"{member['nickname']} ({member['user_id']})")
        """
        output = await self._proxy.call("platform.get_members", {"session": session})
        return list(output.get("members", []))
