import asyncio
import re
import aiohttp
import quart

from astrbot.api import logger
from astrbot.api.message_components import Plain, At
from astrbot.api.platform import AstrBotMessage, MessageMember, MessageType


class XXXBotClient:
    def __init__(
        self,
        host: str,
        port: int,
        bot_wxid: str,
        api_base_url: str,
    ):
        self.host = host
        self.port = port
        self.server = quart.Quart(__name__)
        self.server.add_url_rule(
            "/wx849/callback", view_func=self._callback, methods=["POST"]
        )
        self.shutdown_event = asyncio.Event()
        self.bot_wxid = bot_wxid
        self.api_base_url = api_base_url
        if self.api_base_url.endswith("/"):
            self.api_base_url = self.api_base_url[:-1]
        # self.server.add_url_rule(
        #     "/astrbot-xxxbot/file/<file_token>",
        #     view_func=self._handle_file,
        #     methods=["GET"],
        # )

    async def _callback(self):
        data = await quart.request.json
        logger.debug(f"收到 xxxbot 回调: {data}")

        abm = None
        try:
            abm = await self._convert(data)
        except BaseException as e:
            import traceback

            logger.error(traceback.format_exc())
            logger.warning(
                f"尝试解析 xxxbot 下发的消息时遇到问题: {e}。下发消息内容: {data}。"
            )

        if abm:
            coro = getattr(self, "on_event_received")
            if coro:
                await coro(abm)

        return quart.jsonify({"success": True})

    async def start_polling(self):
        await self.server.run_task(
            host=self.host,
            port=self.port,
            shutdown_trigger=self.shutdown_trigger,
        )

    async def shutdown_trigger(self):
        await self.shutdown_event.wait()

    async def _convert(self, data: dict) -> AstrBotMessage:
        """将 xxxbot 下发的消息转换为 AstrBotMessage 对象"""
        abm = AstrBotMessage()

        # 解析消息类型
        msg_type = data.get("MsgType", 1)
        # 解析发送者信息
        sender = MessageMember(
            user_id=data.get("SenderWxid"),
            nickname=data.get("SenderNickName", data.get("SenderWxid", "")),
        )
        # 解析消息内容
        content = data.get("Content", "")
        # 解析消息 ID
        msg_id = str(data.get("MsgId", ""))
        # 解析消息来源 ID
        from_user_name = data["FromUserName"]["string"]

        abm.message_id = msg_id
        abm.sender = sender
        abm.session_id = from_user_name
        abm.raw_message = data
        abm.message = []
        abm.message_str = ""
        abm.self_id = self.bot_wxid
        # 用于发信息
        abm.raw_message["to_wxid"] = from_user_name

        # 处理 @ 的情况和检查是否为群聊消息或者私聊消息
        at_me = False
        at_wxids = []
        if "@chatroom" in from_user_name:
            abm.type = MessageType.GROUP_MESSAGE
            _t = content.split(":\n")
            user_id = _t[0]
            content = _t[1]
            # at
            msg_source = data.get("MsgSource", "")
            if msg_source and "\u2005" in content:
                # at
                # content = content.split('\u2005')[1]
                content = re.sub(r"@[^\u2005]*\u2005", "", content)
                at_wxids = re.findall(
                    r"<atuserlist><!\[CDATA\[.*?(?:,|\b)([^,]+?)(?=,|\]\]></atuserlist>)",
                    msg_source,
                )

            abm.group_id = from_user_name

            if (
                f"<atuserlist><![CDATA[,{abm.self_id}]]>" in msg_source
                or f"<atuserlist><![CDATA[{abm.self_id}]]>" in msg_source
            ):
                at_me = True
            if "在群聊中@了你" in data.get("PushContent", ""):
                at_me = True
        else:
            abm.type = MessageType.FRIEND_MESSAGE
            user_id = from_user_name

        # 忽略微信团队消息
        if user_id == "weixin":
            return

        if at_me:
            abm.message.insert(0, At(qq=abm.self_id, name=abm.self_id))
        for wxid in at_wxids:
            # 群聊里 At 其他人的列表
            abm.message.append(At(qq=wxid, name=wxid))

        if msg_type == 1:
            abm.message_str = content
            abm.message.append(Plain(content))
        else:
            logger.warning(f"未知的消息类型: {msg_type}")
            return

        return abm

    async def _post(self, path: str, payload: dict):
        """发送 POST 请求"""
        url = f"{self.api_base_url}{path}"
        logger.debug(f"Ready to send text to {url}: {payload}")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    logger.error(f"请求失败: {resp.status} {await resp.text()}")
                    return
                return await resp.json()

    async def post_text(
        self,
        ToWxid: str,
        Content: str,
        Type: int = 1,
        Wxid: str = None,
        At: list = None,
    ):
        """发送文本消息"""
        payload = {
            "ToWxid": ToWxid,
            "Content": Content,
            "Type": Type,
            "Wxid": Wxid,
            "At": At,
        }
        await self._post("/Msg/SendTxt", payload)
