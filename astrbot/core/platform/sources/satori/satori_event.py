from typing import TYPE_CHECKING

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import (
    At,
    File,
    Forward,
    Image,
    Node,
    Nodes,
    Plain,
    Record,
    Reply,
    Video,
)
from astrbot.api.platform import AstrBotMessage, PlatformMetadata

if TYPE_CHECKING:
    from .satori_adapter import SatoriPlatformAdapter


class SatoriPlatformEvent(AstrMessageEvent):
    def __init__(
        self,
        message_str: str,
        message_obj: AstrBotMessage,
        platform_meta: PlatformMetadata,
        session_id: str,
        adapter: "SatoriPlatformAdapter",
    ):
        # 更新平台元数据
        if adapter and hasattr(adapter, "logins") and adapter.logins:
            current_login = adapter.logins[0]
            platform_name = current_login.get("platform", "satori")
            user = current_login.get("user", {})
            user_id = user.get("id", "") if user else ""
            if not platform_meta.id and user_id:
                platform_meta.id = f"{platform_name}({user_id})"

        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.adapter = adapter
        self.platform = None
        self.user_id = None
        if (
            hasattr(message_obj, "raw_message")
            and message_obj.raw_message
            and isinstance(message_obj.raw_message, dict)
        ):
            login = message_obj.raw_message.get("login", {})
            self.platform = login.get("platform")
            user = login.get("user", {})
            self.user_id = user.get("id") if user else None

    @classmethod
    async def send_with_adapter(
        cls,
        adapter: "SatoriPlatformAdapter",
        message: MessageChain,
        session_id: str,
    ):
        try:
            content_parts = []

            for component in message.chain:
                component_content = await cls._convert_component_to_satori_static(
                    component,
                )
                if component_content:
                    content_parts.append(component_content)

                # 特殊处理 Node 和 Nodes 组件
                if isinstance(component, Node):
                    # 单个转发节点
                    node_content = await cls._convert_node_to_satori_static(component)
                    if node_content:
                        content_parts.append(node_content)

                elif isinstance(component, Nodes):
                    # 合并转发消息
                    node_content = await cls._convert_nodes_to_satori_static(component)
                    if node_content:
                        content_parts.append(node_content)

            content = "".join(content_parts)
            channel_id = session_id
            data = {"channel_id": channel_id, "content": content}

            platform = None
            user_id = None

            if hasattr(adapter, "logins") and adapter.logins:
                current_login = adapter.logins[0]
                platform = current_login.get("platform", "")
                user = current_login.get("user", {})
                user_id = user.get("id", "") if user else ""

            result = await adapter.send_http_request(
                "POST",
                "/message.create",
                data,
                platform,
                user_id,
            )
            if result:
                return result
            return None

        except Exception as e:
            logger.error(f"Satori 消息发送异常: {e}")
            return None

    async def send(self, message: MessageChain):
        platform = getattr(self, "platform", None)
        user_id = getattr(self, "user_id", None)

        if not platform or not user_id:
            if hasattr(self.adapter, "logins") and self.adapter.logins:
                current_login = self.adapter.logins[0]
                platform = current_login.get("platform", "")
                user = current_login.get("user", {})
                user_id = user.get("id", "") if user else ""

        try:
            content_parts = []

            for component in message.chain:
                component_content = await self._convert_component_to_satori(component)
                if component_content:
                    content_parts.append(component_content)

                # 特殊处理 Node 和 Nodes 组件
                if isinstance(component, Node):
                    # 单个转发节点
                    node_content = await self._convert_node_to_satori(component)
                    if node_content:
                        content_parts.append(node_content)

                elif isinstance(component, Nodes):
                    # 合并转发消息
                    node_content = await self._convert_nodes_to_satori(component)
                    if node_content:
                        content_parts.append(node_content)

            content = "".join(content_parts)
            channel_id = self.session_id
            data = {"channel_id": channel_id, "content": content}

            result = await self.adapter.send_http_request(
                "POST",
                "/message.create",
                data,
                platform,
                user_id,
            )
            if not result:
                logger.error("Satori 消息发送失败")
        except Exception as e:
            logger.error(f"Satori 消息发送异常: {e}")

        await super().send(message)

    async def send_streaming(self, generator, use_fallback: bool = False):
        try:
            content_parts = []

            async for chain in generator:
                if isinstance(chain, MessageChain):
                    if chain.type == "break":
                        if content_parts:
                            content = "".join(content_parts)
                            temp_chain = MessageChain([Plain(text=content)])
                            await self.send(temp_chain)
                            content_parts = []
                        continue

                    for component in chain.chain:
                        if isinstance(component, Plain):
                            content_parts.append(component.text)
                        elif isinstance(component, Image):
                            if content_parts:
                                content = "".join(content_parts)
                                temp_chain = MessageChain([Plain(text=content)])
                                await self.send(temp_chain)
                                content_parts = []
                            try:
                                image_base64 = await component.convert_to_base64()
                                if image_base64:
                                    img_chain = MessageChain(
                                        [
                                            Plain(
                                                text=f'<img src="data:image/jpeg;base64,{image_base64}"/>',
                                            ),
                                        ],
                                    )
                                    await self.send(img_chain)
                            except Exception as e:
                                logger.error(f"图片转换为base64失败: {e}")
                        else:
                            content_parts.append(str(component))

            if content_parts:
                content = "".join(content_parts)
                temp_chain = MessageChain([Plain(text=content)])
                await self.send(temp_chain)

        except Exception as e:
            logger.error(f"Satori 流式消息发送异常: {e}")

        return await super().send_streaming(generator, use_fallback)

    async def _convert_component_to_satori(self, component) -> str:
        """将单个消息组件转换为 Satori 格式"""
        try:
            if isinstance(component, Plain):
                text = (
                    component.text.replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                )
                return text

            if isinstance(component, At):
                if component.qq:
                    return f'<at id="{component.qq}"/>'
                if component.name:
                    return f'<at name="{component.name}"/>'

            elif isinstance(component, Image):
                try:
                    image_base64 = await component.convert_to_base64()
                    if image_base64:
                        return f'<img src="data:image/jpeg;base64,{image_base64}"/>'
                except Exception as e:
                    logger.error(f"图片转换为base64失败: {e}")

            elif isinstance(component, File):
                return (
                    f'<file src="{component.file}" name="{component.name or "文件"}"/>'
                )

            elif isinstance(component, Record):
                try:
                    record_base64 = await component.convert_to_base64()
                    if record_base64:
                        return f'<audio src="data:audio/wav;base64,{record_base64}"/>'
                except Exception as e:
                    logger.error(f"语音转换为base64失败: {e}")

            elif isinstance(component, Reply):
                return f'<reply id="{component.id}"/>'

            elif isinstance(component, Video):
                try:
                    video_path_url = await component.convert_to_file_path()
                    if video_path_url:
                        return f'<video src="{video_path_url}"/>'
                except Exception as e:
                    logger.error(f"视频文件转换失败: {e}")

            elif isinstance(component, Forward):
                return f'<message id="{component.id}" forward/>'

            # 对于其他未处理的组件类型，返回空字符串
            return ""

        except Exception as e:
            logger.error(f"转换消息组件失败: {e}")
            return ""

    async def _convert_node_to_satori(self, node: Node) -> str:
        """将单个转发节点转换为 Satori 格式"""
        try:
            content_parts = []
            if node.content:
                for content_component in node.content:
                    component_content = await self._convert_component_to_satori(
                        content_component,
                    )
                    if component_content:
                        content_parts.append(component_content)

            content = "".join(content_parts)

            # 如果内容为空，添加默认内容
            if not content.strip():
                content = "[转发消息]"

            # 构建 Satori 格式的转发节点
            author_attrs = []
            if node.uin:
                author_attrs.append(f'id="{node.uin}"')
            if node.name:
                author_attrs.append(f'name="{node.name}"')

            author_attr_str = " ".join(author_attrs)

            return f"<message><author {author_attr_str}/>{content}</message>"

        except Exception as e:
            logger.error(f"转换转发节点失败: {e}")
            return ""

    @classmethod
    async def _convert_component_to_satori_static(cls, component) -> str:
        """将单个消息组件转换为 Satori 格式"""
        try:
            if isinstance(component, Plain):
                text = (
                    component.text.replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                )
                return text

            if isinstance(component, At):
                if component.qq:
                    return f'<at id="{component.qq}"/>'
                if component.name:
                    return f'<at name="{component.name}"/>'

            elif isinstance(component, Image):
                try:
                    image_base64 = await component.convert_to_base64()
                    if image_base64:
                        return f'<img src="data:image/jpeg;base64,{image_base64}"/>'
                except Exception as e:
                    logger.error(f"图片转换为base64失败: {e}")

            elif isinstance(component, File):
                return (
                    f'<file src="{component.file}" name="{component.name or "文件"}"/>'
                )

            elif isinstance(component, Record):
                try:
                    record_base64 = await component.convert_to_base64()
                    if record_base64:
                        return f'<audio src="data:audio/wav;base64,{record_base64}"/>'
                except Exception as e:
                    logger.error(f"语音转换为base64失败: {e}")

            elif isinstance(component, Reply):
                return f'<reply id="{component.id}"/>'

            elif isinstance(component, Video):
                try:
                    video_path_url = await component.convert_to_file_path()
                    if video_path_url:
                        return f'<video src="{video_path_url}"/>'
                except Exception as e:
                    logger.error(f"视频文件转换失败: {e}")

            elif isinstance(component, Forward):
                return f'<message id="{component.id}" forward/>'

            # 对于其他未处理的组件类型，返回空字符串
            return ""

        except Exception as e:
            logger.error(f"转换消息组件失败: {e}")
            return ""

    @classmethod
    async def _convert_node_to_satori_static(cls, node: Node) -> str:
        """将单个转发节点转换为 Satori 格式"""
        try:
            content_parts = []
            if node.content:
                for content_component in node.content:
                    component_content = await cls._convert_component_to_satori_static(
                        content_component,
                    )
                    if component_content:
                        content_parts.append(component_content)

            content = "".join(content_parts)

            # 如果内容为空，添加默认内容
            if not content.strip():
                content = "[转发消息]"

            author_attrs = []
            if node.uin:
                author_attrs.append(f'id="{node.uin}"')
            if node.name:
                author_attrs.append(f'name="{node.name}"')

            author_attr_str = " ".join(author_attrs)

            return f"<message><author {author_attr_str}/>{content}</message>"

        except Exception as e:
            logger.error(f"转换转发节点失败: {e}")
            return ""

    async def _convert_nodes_to_satori(self, nodes: Nodes) -> str:
        """将多个转发节点转换为 Satori 格式的合并转发"""
        try:
            node_parts = []

            for node in nodes.nodes:
                node_content = await self._convert_node_to_satori(node)
                if node_content:
                    node_parts.append(node_content)

            if node_parts:
                return f"<message forward>{''.join(node_parts)}</message>"
            return ""

        except Exception as e:
            logger.error(f"转换合并转发消息失败: {e}")
            return ""

    @classmethod
    async def _convert_nodes_to_satori_static(cls, nodes: Nodes) -> str:
        """将多个转发节点转换为 Satori 格式的合并转发"""
        try:
            node_parts = []

            for node in nodes.nodes:
                node_content = await cls._convert_node_to_satori_static(node)
                if node_content:
                    node_parts.append(node_content)

            if node_parts:
                return f"<message forward>{''.join(node_parts)}</message>"
            return ""

        except Exception as e:
            logger.error(f"转换合并转发消息失败: {e}")
            return ""
