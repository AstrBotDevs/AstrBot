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
import asyncio
from pathlib import Path
from typing import Union, Awaitable, List, Optional, ClassVar, Dict, Any, Callable
from astrbot.core import logger
from astrbot.core.message.components import BaseMessageComponent
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform import MessageMember, AstrBotMessage, MessageType
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
    _shared_data: ClassVar[Dict[str, Any]] = {}
    _data_listeners: ClassVar[Dict[str, List[Callable[[str, Any], Awaitable[None]]]]] = {}


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

    @classmethod
    def set_shared_data(cls, key: str, value: Any, plugin_name: Optional[str] = None) -> None:
        """
        设置插件间共享数据

        Args:
            key (str): 数据键名
            value (Any): 要存储的数据，支持任意数据类型
            plugin_name (Optional[str]): 插件名称，如果为None则自动检测

        Example:
            # 设置工作状态
            StarTools.set_shared_data("worker_status", True)

            # 设置复杂数据
            StarTools.set_shared_data("task_progress", {
                "current": 5,
                "total": 10,
                "status": "processing"
            })
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

        full_key = f"{plugin_name}:{key}"
        cls._shared_data[full_key] = value
        asyncio.create_task(cls._notify_listeners(full_key, value))

    @classmethod
    def get_shared_data(cls, key: str, plugin_name: Optional[str] = None, default: Any = None) -> Any:
        """
        获取插件间共享数据

        Args:
            key (str): 数据键名
            plugin_name (Optional[str]): 插件名称，如果为None则自动检测
            default (Any): 当数据不存在时返回的默认值

        Returns:
            Any: 存储的数据，如果不存在则返回default

        Example:
            # 获取其他插件的工作状态
            status = StarTools.get_shared_data("worker_status", "other_plugin")

            # 获取当前插件的数据
            my_data = StarTools.get_shared_data("my_key")
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

        full_key = f"{plugin_name}:{key}"
        return cls._shared_data.get(full_key, default)

    @classmethod
    def remove_shared_data(cls, key: str, plugin_name: Optional[str] = None) -> bool:
        """
        删除插件间共享数据

        Args:
            key (str): 数据键名
            plugin_name (Optional[str]): 插件名称，如果为None则自动检测

        Returns:
            bool: 是否成功删除（True表示数据存在并被删除，False表示数据不存在）
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

        full_key = f"{plugin_name}:{key}"
        if full_key in cls._shared_data:
            del cls._shared_data[full_key]
            return True
        return False

    @classmethod
    def list_shared_data(cls, plugin_name: Optional[str] = None) -> Dict[str, Any]:
        """
        列出指定插件的所有共享数据

        Args:
            plugin_name (Optional[str]): 插件名称，如果为None则返回所有数据

        Returns:
            Dict[str, Any]: 数据字典，键为原始键名（不包含插件前缀）

        Example:
            # 获取当前插件的所有数据
            my_data = StarTools.list_shared_data()

            # 获取所有插件的数据
            all_data = StarTools.list_shared_data("")
        """
        if plugin_name is None:
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

        if plugin_name == "":
            return dict(cls._shared_data)

        prefix = f"{plugin_name}:"
        result = {}
        for full_key, value in cls._shared_data.items():
            if full_key.startswith(prefix):
                original_key = full_key[len(prefix):]
                result[original_key] = value
        return result

    @classmethod
    def add_data_listener(
        cls,
        key: str,
        callback: Callable[[str, Any], Awaitable[None]],
        plugin_name: Optional[str] = None
    ) -> None:
        """
        添加数据变化监听器

        Args:
            key (str): 要监听的数据键名
            callback (Callable): 回调函数，接受参数(key, new_value)
            plugin_name (Optional[str]): 插件名称，如果为None则自动检测

        Example:
            async def on_worker_status_change(key: str, value: Any):
                if value:
                    logger.INFO("哈哈我的工作完成啦!")

            StarTools.add_data_listener("worker_status", on_worker_status_change, "other_plugin")
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

        full_key = f"{plugin_name}:{key}"
        if full_key not in cls._data_listeners:
            cls._data_listeners[full_key] = []
        cls._data_listeners[full_key].append(callback)

    @classmethod
    def remove_data_listener(
        cls,
        key: str,
        callback: Callable[[str, Any], Awaitable[None]],
        plugin_name: Optional[str] = None
    ) -> bool:
        """
        移除数据变化监听器

        Args:
            key (str): 数据键名
            callback (Callable): 要移除的回调函数
            plugin_name (Optional[str]): 插件名称，如果为None则自动检测

        Returns:
            bool: 是否成功移除
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

        full_key = f"{plugin_name}:{key}"
        if full_key in cls._data_listeners and callback in cls._data_listeners[full_key]:
            cls._data_listeners[full_key].remove(callback)
            if not cls._data_listeners[full_key]:
                del cls._data_listeners[full_key]
            return True
        return False

    @classmethod
    async def _notify_listeners(cls, full_key: str, value: Any) -> None:
        """
        通知所有监听指定数据的回调函数

        Args:
            full_key (str): 完整的数据键名（包含插件前缀）
            value (Any): 新的数据值
        """
        if full_key in cls._data_listeners:
            tasks = []
            for callback in cls._data_listeners[full_key]:
                try:
                    task = callback(full_key, value)
                    if asyncio.iscoroutine(task):
                        tasks.append(task)
                except Exception as e:
                    logger.Error(f"数据监听器错误:{full_key}: {e}")

            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

