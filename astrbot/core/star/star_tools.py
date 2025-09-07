"""
插件开发工具集
封装了许多常用的操作，方便插件开发者使用

说明:

主动发送消息: send_message(session, message_chain)
    根据 session (unified_msg_origin) 主动发送消息, 前提是需要提前获得或构造 session

根据id直接主动发送消息: send_message_by_id(type, id, message_chain, platform="aiocqhttp")
    根据 id (例如 qq 号, 群号等) 直接, 主动地发送消息

以上两种方式需要构造消息链, 也就是消息组件的列表

构造事件:

首先需要构造一个 AstrBotMessage 对象, 使用 create_message 方法
然后使用 create_event 方法提交事件到指定平台
"""

import inspect
import os
import uuid
from pathlib import Path
from typing import Union, Awaitable, List, Optional, ClassVar
from astrbot.core.message.components import BaseMessageComponent
from astrbot.core.message.message_event_result import MessageChain
from astrbot.api.platform import MessageMember, AstrBotMessage, MessageType
from astrbot.core.platform.astr_message_event import MessageSesion
from astrbot.core.star.context import Context
from astrbot.core.star.star import star_map
from astrbot.core.utils.astrbot_path import get_astrbot_data_path
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_platform_adapter import AiocqhttpAdapter

class StarTools:
    """
    提供给插件使用的便捷工具函数集合
    这些方法封装了一些常用操作，使插件开发更加简单便捷!
    """

    _context: ClassVar[Optional[Context]] = None

    @classmethod
    def initialize(cls, context: Context) -> None:
        """
        初始化StarTools，设置context引用

        Args:
            context: 暴露给插件的上下文
        """
        cls._context = context

    @classmethod
    async def send_message(
        cls, session: Union[str, MessageSesion], message_chain: MessageChain
    ) -> bool:
        """
        根据session(unified_msg_origin)主动发送消息

        Args:
            session: 消息会话。通过event.session或者event.unified_msg_origin获取
            message_chain: 消息链

        Returns:
            bool: 是否找到匹配的平台

        Raises:
            ValueError: 当session为字符串且解析失败时抛出

        Note:
            qq_official(QQ官方API平台)不支持此方法
        """
        if cls._context is None:
            raise ValueError("StarTools not initialized")
        return await cls._context.send_message(session, message_chain)

    @classmethod
    async def send_message_by_id(
        cls, type: str, id: str, message_chain: MessageChain, platform: str = "aiocqhttp"
    ):
        """
        根据 id(例如qq号, 群号等) 直接, 主动地发送消息

        Args:
            type (str): 消息类型, 可选: PrivateMessage, GroupMessage
            id (str): 目标ID, 例如QQ号, 群号等
            message_chain (MessageChain): 消息链
            platform (str): 可选的平台名称，默认平台(aiocqhttp), 目前只支持 aiocqhttp
        """
        if cls._context is None:
            raise ValueError("StarTools not initialized")
        platforms = cls._context.platform_manager.get_insts()
        if platform == "aiocqhttp":
            adapter = next((p for p in platforms if isinstance(p, AiocqhttpAdapter)), None)
            if adapter is None:
                raise ValueError("未找到适配器: AiocqhttpAdapter")
            await AiocqhttpMessageEvent.send_message(
                bot=adapter.bot,
                message_chain=message_chain,
                is_group=(type == "GroupMessage"),
                session_id=id,
            )
        else:
            raise ValueError(f"不支持的平台: {platform}")

    @classmethod
    async def create_message(
        cls,
        type: str,
        self_id: str,
        session_id: str,
        sender: MessageMember,
        message: List[BaseMessageComponent],
        message_str: str,
        message_id: str = "",
        raw_message: object = None,
        group_id: str = ""
    ) -> AstrBotMessage:
        """
        创建一个AstrBot消息对象

        Args:
            type (str): 消息类型, 例如 "GroupMessage" "FriendMessage" "OtherMessage"
            self_id (str): 机器人自身ID
            session_id (str): 会话ID(通常为用户ID)(QQ号, 群号等)
            sender (MessageMember): 发送者信息, 例如 MessageMember(user_id="123456", nickname="昵称")
            message (List[BaseMessageComponent]): 消息组件列表, 也就是消息链, 这个不会发给 llm, 但是会经过其他处理
            message_str (str): 消息字符串, 也就是纯文本消息, 也就是发送给 llm 的消息, 与消息链一致

            message_id (str): 消息ID, 构造消息时可以随意填写也可不填
            raw_message (object): 原始消息对象, 可以随意填写也可不填
            group_id (str, optional): 群组ID, 如果为私聊则为空. Defaults to "".

        Returns:
            AstrBotMessage: 创建的消息对象
        """
        abm = AstrBotMessage()
        abm.type = MessageType(type)
        abm.self_id = self_id
        abm.session_id = session_id
        if message_id == "":
            message_id = uuid.uuid4().hex
        abm.message_id = message_id
        abm.sender = sender
        abm.message = message
        abm.message_str = message_str
        abm.raw_message = raw_message
        abm.group_id = group_id
        return abm

    @classmethod
    async def create_event(
        cls, abm: AstrBotMessage, platform: str = "aiocqhttp", is_wake: bool = True

    ) -> None:
        """
        创建并提交事件到指定平台
        当有需要创建一个事件, 触发某些处理流程时, 使用该方法

        Args:
            abm (AstrBotMessage): 要提交的消息对象, 请先使用 create_message 创建
            platform (str): 可选的平台名称，默认平台(aiocqhttp), 目前只支持 aiocqhttp
            is_wake (bool): 是否标记为唤醒事件, 默认为 True, 只有唤醒事件才会被 llm 响应
        """
        if cls._context is None:
            raise ValueError("StarTools not initialized")
        platforms = cls._context.platform_manager.get_insts()
        if platform == "aiocqhttp":
            adapter = next((p for p in platforms if isinstance(p, AiocqhttpAdapter)), None)
            if adapter is None:
                raise ValueError("未找到适配器: AiocqhttpAdapter")
            event = AiocqhttpMessageEvent(
                message_str=abm.message_str,
                message_obj=abm,
                platform_meta=adapter.metadata,
                session_id=abm.session_id,
                bot=adapter.bot,
            )
            event.is_wake = is_wake
            adapter.commit_event(event)
        else:
            raise ValueError(f"不支持的平台: {platform}")

    @classmethod
    def activate_llm_tool(cls, name: str) -> bool:
        """
        激活一个已经注册的函数调用工具
        注册的工具默认是激活状态

        Args:
            name (str): 工具名称
        """
        if cls._context is None:
            raise ValueError("StarTools not initialized")
        return cls._context.activate_llm_tool(name)

    @classmethod
    def deactivate_llm_tool(cls, name: str) -> bool:
        """
        停用一个已经注册的函数调用工具

        Args:
            name (str): 工具名称
        """
        if cls._context is None:
            raise ValueError("StarTools not initialized")
        return cls._context.deactivate_llm_tool(name)

    @classmethod
    def register_llm_tool(
        cls, name: str, func_args: list, desc: str, func_obj: Awaitable
    ) -> None:
        """
        为函数调用（function-calling/tools-use）添加工具

        Args:
            name (str): 工具名称
            func_args (list): 函数参数列表
            desc (str): 工具描述
            func_obj (Awaitable): 函数对象，必须是异步函数
        """
        if cls._context is None:
            raise ValueError("StarTools not initialized")
        cls._context.register_llm_tool(name, func_args, desc, func_obj)

    @classmethod
    def unregister_llm_tool(cls, name: str) -> None:
        """
        删除一个函数调用工具
        如果再要启用，需要重新注册

        Args:
            name (str): 工具名称
        """
        if cls._context is None:
            raise ValueError("StarTools not initialized")
        cls._context.unregister_llm_tool(name)

    @classmethod
    def get_data_dir(cls, plugin_name: Optional[str] = None) -> Path:
        """
        返回插件数据目录的绝对路径。

        此方法会在 data/plugin_data 目录下为插件创建一个专属的数据目录。如果未提供插件名称，
        会自动从调用栈中获取插件信息。

        Args:
            plugin_name: 可选的插件名称。如果为None，将自动检测调用者的插件名称。

        Returns:
            Path (Path): 插件数据目录的绝对路径，位于 data/plugin_data/{plugin_name}。

        Raises:
            RuntimeError: 当出现以下情况时抛出:
                - 无法获取调用者模块信息
                - 无法获取模块的元数据信息
                - 创建目录失败（权限不足或其他IO错误）
        """
        if not plugin_name:
            frame = inspect.currentframe()
            module = None
            if frame:
                frame = frame.f_back
                module = inspect.getmodule(frame)

            if not module:
                raise RuntimeError("无法获取调用者模块信息")

            metadata = star_map.get(module.__name__, None)

            if not metadata:
                raise RuntimeError(f"无法获取模块 {module.__name__} 的元数据信息")

            plugin_name = metadata.name

        if not plugin_name:
            raise ValueError("无法获取插件名称")

        data_dir = Path(os.path.join(get_astrbot_data_path(), "plugin_data", plugin_name))

        try:
            data_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            if isinstance(e, PermissionError):
                raise RuntimeError(f"无法创建目录 {data_dir}：权限不足") from e
            raise RuntimeError(f"无法创建目录 {data_dir}：{e!s}") from e

        return data_dir.resolve()
