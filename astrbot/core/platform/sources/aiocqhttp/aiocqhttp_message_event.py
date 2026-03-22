import asyncio
import base64
import copy
import hashlib
import re
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from urllib.parse import urlparse

from aiocqhttp import CQHttp, Event

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import (
    At,
    BaseMessageComponent,
    File,
    Image,
    Node,
    Nodes,
    Plain,
    Record,
    Video,
)
from astrbot.api.platform import Group, MessageMember

CHUNK_SIZE = 64 * 1024  # 流式上传分块大小:64KB
FILE_RETENTION_MS = 30 * 1000  # 文件在服务端的保留时间(毫秒),NapCat 使用毫秒


class AiocqhttpMessageEvent(AstrMessageEvent):
    def __init__(
        self,
        message_str,
        message_obj,
        platform_meta,
        session_id,
        bot: CQHttp,
    ) -> None:
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.bot = bot

    @staticmethod
    def _is_local_file_path(file_str: str) -> bool:
        """判断是否为本地文件路径(非 base64/URL)"""
        if not file_str:
            return False
        # base64 编码
        if file_str.startswith("base64://"):
            return False
        # 远程 URL
        if file_str.startswith(("http://", "https://")):
            return False
        # 包含协议头但不是以上几种,如 file://,仍视为本地
        if "://" in file_str:
            # file:// 开头认为是本地
            return file_str.startswith("file://")
        # 无协议头,视为本地路径
        return True

    @classmethod
    async def _send_with_stream_retry(
        cls,
        bot: CQHttp,
        message_chain: MessageChain,
        event: Event | None,
        is_group: bool,
        session_id: str | None,
    ) -> bool:
        """
        尝试普通发送,若失败且消息中包含本地文件,则尝试通过流式上传重发｡
        返回 True 表示发送成功(含重试成功),False 表示失败且无需继续｡
        抛出异常表示需要上层处理(如取消任务等)｡
        """
        # 构造新消息链,避免修改原始对象
        new_chain = MessageChain([])
        modified = False
        for seg in message_chain.chain:
            new_seg = copy.copy(seg)  # 浅拷贝,确保独立
            if isinstance(new_seg, (Image, Record, File, Video)):
                file_val = getattr(new_seg, "file", None)
                if file_val and cls._is_local_file_path(file_val):
                    try:
                        logger.debug(f"文件上传失败,尝试 NapCat 流式传输: {file_val}")
                        new_path = await cls._upload_file_via_stream(bot, file_val)
                        new_seg.file = new_path
                        modified = True
                    except Exception as upload_err:
                        raise f"NapCat 文件流式上传失败: {upload_err}"
                        # 上传失败,保留原文件路径,但继续后续 segments 处理
            new_chain.chain.append(new_seg)
        if not modified:
            return False
        ret = await cls._parse_onebot_json(new_chain)
        if ret:
            await cls._dispatch_send(bot, event, is_group, session_id, ret)
            return True
        return False

    @classmethod
    async def _upload_file_via_stream(cls, bot: CQHttp, file_path: str) -> str:
        """使用 OneBot 流式上传接口上传文件,返回服务端文件路径"""
        # 处理 file:// URI 协议头
        if file_path.startswith("file://"):
            parsed = urlparse(file_path)
            path = parsed.path
            if parsed.netloc and not path:
                path = parsed.netloc
            if path.startswith("/") and ":" in path:
                path = path.lstrip("/")
            file_path = path

        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        # 第一次遍历:计算文件总大小和 SHA256 哈希
        hasher = hashlib.sha256()
        total_size = 0
        with open(path, "rb") as f:
            while True:
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    break
                hasher.update(chunk)
                total_size += len(chunk)
        sha256_hash = hasher.hexdigest()
        total_chunks = (total_size + CHUNK_SIZE - 1) // CHUNK_SIZE

        # 第二次遍历:逐块上传
        stream_id = str(uuid.uuid4())
        with open(path, "rb") as f:
            for i in range(total_chunks):
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    break
                chunk_b64 = base64.b64encode(chunk).decode("utf-8")
                params = {
                    "stream_id": stream_id,
                    "chunk_data": chunk_b64,
                    "chunk_index": i,
                    "total_chunks": total_chunks,
                    "file_size": total_size,
                    "expected_sha256": sha256_hash,
                    "filename": path.name,
                    "file_retention": FILE_RETENTION_MS,  # 单位为毫秒
                }
                resp = await bot.call_action("upload_file_stream", **params)
                if not cls._is_upload_success_response(
                    resp, expected_statuses=("chunk_received", "file_complete")
                ):
                    raise OSError(f"上传分片 {i} 失败: {resp}")

        # 发送完成信号
        complete_params = {"stream_id": stream_id, "is_complete": True}
        resp = await bot.call_action("upload_file_stream", **complete_params)
        if not cls._is_upload_success_response(
            resp, expected_statuses=("file_complete",)
        ):
            raise OSError(f"文件合并失败: {resp}")

        # 提取最终文件路径
        file_path_result = None
        data = resp.get("data")
        if data and isinstance(data, dict):
            file_path_result = data.get("file_path")
        if not file_path_result:
            file_path_result = resp.get("file_path")
        if not file_path_result:
            raise ValueError(f"无法从响应中获取文件路径: {resp}")
        return file_path_result

    @classmethod
    def _is_upload_success_response(cls, resp: dict, expected_statuses: tuple) -> bool:
        """判断流式上传的响应是否为成功"""
        # 标准 OneBot 响应
        if resp.get("status") == "ok":
            return True
        # NapCat 流式响应
        resp_type = resp.get("type", "").lower()
        resp_status = resp.get("status", "")
        if resp_type in ("stream", "response") and resp_status in expected_statuses:
            return True
        return False

    @staticmethod
    async def _from_segment_to_dict(segment: BaseMessageComponent) -> dict:
        """修复部分字段"""
        if isinstance(segment, Image | Record):
            # For Image and Record segments, we convert them to base64
            bs64 = await segment.convert_to_base64()
            return {
                "type": segment.type.lower(),
                "data": {
                    "file": f"base64://{bs64}",
                },
            }
        if isinstance(segment, File):
            # For File segments, we need to handle the file differently
            d = await segment.to_dict()
            file_val = d.get("data", {}).get("file", "")
            if file_val:
                import pathlib

                try:
                    # 使用 pathlib 处理路径,能更好地处理 Windows/Linux 差异
                    path_obj = pathlib.Path(file_val)
                    # 如果是绝对路径且不包含协议头 (://),则转换为标准的 file: URI
                    if path_obj.is_absolute() and "://" not in file_val:
                        d["data"]["file"] = path_obj.as_uri()
                except Exception:
                    # 如果不是合法路径(例如已经是特定的特殊字符串),则跳过转换
                    pass
            return d
        if isinstance(segment, Video):
            d = await segment.to_dict()
            return d
        # For other segments, we simply convert them to a dict by calling toDict
        return segment.toDict()

    @staticmethod
    async def _parse_onebot_json(message_chain: MessageChain):
        """解析成 OneBot json 格式"""
        ret = []
        for segment in message_chain.chain:
            if isinstance(segment, At):
                # At 组件后插入一个空格,避免与后续文本粘连
                d = await AiocqhttpMessageEvent._from_segment_to_dict(segment)
                ret.append(d)
                ret.append({"type": "text", "data": {"text": " "}})
            elif isinstance(segment, Plain):
                if not segment.text.strip():
                    continue
                d = await AiocqhttpMessageEvent._from_segment_to_dict(segment)
                ret.append(d)
            else:
                d = await AiocqhttpMessageEvent._from_segment_to_dict(segment)
                ret.append(d)
        return ret

    @classmethod
    async def _dispatch_send(
        cls,
        bot: CQHttp,
        event: Event | None,
        is_group: bool,
        session_id: str | None,
        messages: list[dict],
    ) -> None:
        # session_id 必须是纯数字字符串
        session_id_int = (
            int(session_id) if session_id and session_id.isdigit() else None
        )

        if is_group and isinstance(session_id_int, int):
            await bot.send_group_msg(group_id=session_id_int, message=messages)
        elif not is_group and isinstance(session_id_int, int):
            await bot.send_private_msg(user_id=session_id_int, message=messages)
        elif isinstance(event, Event):  # 最后兜底
            await bot.send(event=event, message=messages)
        else:
            raise ValueError(
                f"无法发送消息:缺少有效的数字 session_id({session_id}) 或 event({event})",
            )

    @classmethod
    async def send_message(
        cls,
        bot: CQHttp,
        message_chain: MessageChain,
        event: Event | None = None,
        is_group: bool = False,
        session_id: str | None = None,
    ) -> None:
        """发送消息至 QQ 协议端(aiocqhttp)｡
        如果普通发送失败且消息中包含本地文件,会尝试使用流式上传后重发｡

        Args:
            bot (CQHttp): aiocqhttp 机器人实例
            message_chain (MessageChain): 要发送的消息链
            event (Event | None, optional): aiocqhttp 事件对象.
            is_group (bool, optional): 是否为群消息.
            session_id (str | None, optional): 会话 ID(群号或 QQ 号

        """
        # 转发消息､文件消息不能和普通消息混在一起发送
        send_one_by_one = any(
            isinstance(seg, Node | Nodes | File) for seg in message_chain.chain
        )
        if not send_one_by_one:
            # 尝试普通发送
            try:
                ret = await cls._parse_onebot_json(message_chain)
                if not ret:
                    return
                await cls._dispatch_send(bot, event, is_group, session_id, ret)
                return
            except asyncio.CancelledError:
                raise
            except Exception as e:
                # 其他异常:尝试流式重试
                try:
                    success = await cls._send_with_stream_retry(
                        bot, message_chain, event, is_group, session_id
                    )
                    if success:
                        return
                except Exception as retry_err:
                    # 重试过程也失败,抛出原始异常
                    logger.error(retry_err)
                # 重试未成功或无组件可重试,抛出原始异常
                raise e

        # 原有逐条发送逻辑(处理 Node/Nodes/File 等)
        for seg in message_chain.chain:
            if isinstance(seg, Node | Nodes):
                # 合并转发消息
                if isinstance(seg, Node):
                    nodes = Nodes([seg])
                    seg = nodes

                payload = await seg.to_dict()

                if is_group:
                    payload["group_id"] = session_id
                    await bot.call_action("send_group_forward_msg", **payload)
                else:
                    payload["user_id"] = session_id
                    await bot.call_action("send_private_forward_msg", **payload)
            elif isinstance(seg, File):
                # 使用 OneBot V11 文件 API 发送文件
                file_path = seg.file_ or seg.url
                if not file_path:
                    logger.warning("无法发送文件:文件路径或 URL 为空｡")
                    continue

                file_name = seg.name or "file"
                session_id_int = (
                    int(session_id) if session_id and session_id.isdigit() else None
                )

                if session_id_int is None:
                    logger.warning(f"无法发送文件:无效的 session_id: {session_id}")
                    continue

                if is_group:
                    await bot.send_group_file(
                        group_id=session_id_int, file=file_path, name=file_name
                    )
                else:
                    await bot.send_private_file(
                        user_id=session_id_int, file=file_path, name=file_name
                    )
            else:
                messages = await cls._parse_onebot_json(MessageChain([seg]))
                if not messages:
                    continue
                await cls._dispatch_send(bot, event, is_group, session_id, messages)
                await asyncio.sleep(0.5)

    async def send(self, message: MessageChain) -> None:
        """发送消息"""
        event = getattr(self.message_obj, "raw_message", None)

        is_group = bool(self.get_group_id())
        session_id = self.get_group_id() if is_group else self.get_sender_id()

        await self.send_message(
            bot=self.bot,
            message_chain=message,
            event=event,  # 不强制要求一定是 Event
            is_group=is_group,
            session_id=session_id,
        )
        await super().send(message)

    async def send_streaming(
        self,
        generator: AsyncGenerator,
        use_fallback: bool = False,
    ):
        if not use_fallback:
            buffer = None
            async for chain in generator:
                if not buffer:
                    buffer = chain
                else:
                    buffer.chain.extend(chain.chain)
            if not buffer:
                return None
            buffer.squash_plain()
            await self.send(buffer)
            return await super().send_streaming(generator, use_fallback)

        buffer = ""
        pattern = re.compile(r"[^｡?!~…]+[｡?!~…]+")

        async for chain in generator:
            if isinstance(chain, MessageChain):
                for comp in chain.chain:
                    if isinstance(comp, Plain):
                        buffer += comp.text
                        if any(p in buffer for p in "｡?!~…"):
                            buffer = await self.process_buffer(buffer, pattern)
                    else:
                        await self.send(MessageChain(chain=[comp]))
                        await asyncio.sleep(1.5)  # 限速

        if buffer.strip():
            await self.send(MessageChain([Plain(buffer)]))
        return await super().send_streaming(generator, use_fallback)

    async def get_group(self, group_id=None, **kwargs):
        if isinstance(group_id, str) and group_id.isdigit():
            group_id = int(group_id)
        elif self.get_group_id():
            group_id = int(self.get_group_id())
        else:
            return None

        info: dict = await self.bot.call_action(
            "get_group_info",
            group_id=group_id,
        )

        members: list[dict] = await self.bot.call_action(
            "get_group_member_list",
            group_id=group_id,
        )

        owner_id = None
        admin_ids = []
        for member in members:
            if member["role"] == "owner":
                owner_id = member["user_id"]
            if member["role"] == "admin":
                admin_ids.append(member["user_id"])

        group = Group(
            group_id=str(group_id),
            group_name=info.get("group_name"),
            group_avatar="",
            group_admins=admin_ids,
            group_owner=str(owner_id),
            members=[
                MessageMember(
                    user_id=member["user_id"],
                    nickname=member.get("nickname") or member.get("card"),
                )
                for member in members
            ],
        )

        return group
