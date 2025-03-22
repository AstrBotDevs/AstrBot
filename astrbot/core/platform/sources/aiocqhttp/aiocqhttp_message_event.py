import asyncio
import typing
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.platform import Group, MessageMember
from astrbot.api.message_components import Plain, Image, Record, At, Node, Nodes
from aiocqhttp import CQHttp


class AiocqhttpMessageEvent(AstrMessageEvent):
    def __init__(
        self, message_str, message_obj, platform_meta, session_id, bot: CQHttp
    ):
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.bot = bot

    @staticmethod
    async def _parse_onebot_json(message_chain: MessageChain):
        """解析成 OneBot json 格式"""
        ret = []
        for segment in message_chain.chain:
            d = segment.toDict()
            if isinstance(segment, Plain):
                d["type"] = "text"
                d["data"]["text"] = segment.text.strip()
            elif isinstance(segment, (Image, Record)):
                # convert to base64
                bs64 = await segment.convert_to_base64()
                d["data"] = {
                    "file": bs64,
                }
            elif isinstance(segment, At):
                d["data"] = {
                    "qq": str(segment.qq)  # 转换为字符串
                }
            ret.append(d)
        return ret

    async def send(self, message: MessageChain):
        ret = await AiocqhttpMessageEvent._parse_onebot_json(message)

        send_one_by_one = False
        for seg in message.chain:
            if isinstance(seg, (Node, Nodes)):
                # 转发消息不能和普通消息混在一起发送
                send_one_by_one = True
                break

        if send_one_by_one:
            for seg in message.chain:
                if isinstance(seg, (Node, Nodes)):
                    # 合并转发消息

                    if isinstance(seg, Node):
                        nodes = Nodes([seg])
                        seg = nodes

                    payload = seg.toDict()
                    if self.get_group_id():
                        payload["group_id"] = self.get_group_id()
                        await self.bot.call_action("send_group_forward_msg", **payload)
                    else:
                        payload["user_id"] = self.get_sender_id()
                        await self.bot.call_action(
                            "send_private_forward_msg", **payload
                        )
                else:
                    await self.bot.send(
                        self.message_obj.raw_message,
                        await AiocqhttpMessageEvent._parse_onebot_json(
                            MessageChain([seg])
                        ),
                    )
                    await asyncio.sleep(0.5)
        else:
            await self.bot.send(self.message_obj.raw_message, ret)

        await super().send(message)

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

        members: typing.List[typing.Dict] = await self.bot.call_action(
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
