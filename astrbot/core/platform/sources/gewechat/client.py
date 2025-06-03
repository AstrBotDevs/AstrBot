import asyncio
import base64
import datetime
import os
import re
import uuid
import threading

import aiohttp
import anyio
import quart

from astrbot.api import logger, sp
from astrbot.api.message_components import Plain, Image, At, Record, Video
from astrbot.api.platform import AstrBotMessage, MessageMember, MessageType
from astrbot.core.utils.io import download_image_by_url
from .downloader import GeweDownloader
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

try:
    from .xml_data_parser import GeweDataParser
except (ImportError, ModuleNotFoundError) as e:
    logger.warning(
        f"警告: 可能未安装 defusedxml 依赖库，将导致无法解析微信的 表情包、引用 类型的消息: {str(e)}"
    )


class SimpleGewechatClient:
    """针对 Gewechat 的简单实现。

    @author: Soulter
    @website: https://github.com/Soulter
    """

    def __init__(
        self,
        base_url: str,
        nickname: str,
        host: str,
        port: int,
        event_queue: asyncio.Queue,
    ):
        self.base_url = base_url
        if self.base_url.endswith("/"):
            self.base_url = self.base_url[:-1]

        self.download_base_url = self.base_url.split(":")[:-1]  # 去掉端口
        self.download_base_url = ":".join(self.download_base_url) + ":2532/download/"

        self.base_url += "/v2/api"

        logger.info(f"Gewechat API: {self.base_url}")
        logger.info(f"Gewechat 下载 API: {self.download_base_url}")

        if isinstance(port, str):
            port = int(port)

        self.token = None
        self.headers = {}
        self.nickname = nickname
        self.appid = sp.get(f"gewechat-appid-{nickname}", "")

        self.server = quart.Quart(__name__)
        self.server.add_url_rule(
            "/astrbot-gewechat/callback", view_func=self._callback, methods=["POST"]
        )
        self.server.add_url_rule(
            "/astrbot-gewechat/file/<file_token>",
            view_func=self._handle_file,
            methods=["GET"],
        )

        self.host = host
        self.port = port
        self.callback_url = f"http://{self.host}:{self.port}/astrbot-gewechat/callback"
        self.file_server_url = f"http://{self.host}:{self.port}/astrbot-gewechat/file"

        self.event_queue = event_queue

        self.multimedia_downloader = None

        self.userrealnames = {}

        self.shutdown_event = asyncio.Event()

        self.staged_files = {}
        """存储了允许外部访问的文件列表。auth_token: file_path。通过 register_file 方法注册。"""

        self.lock = asyncio.Lock()

    async def get_token_id(self):
        """获取 Gewechat Token。"""
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.base_url}/tools/getTokenId") as resp:
                json_blob = await resp.json()
                self.token = json_blob["data"]
                logger.info(f"获取到 Gewechat Token: {self.token}")
                self.headers = {"X-GEWE-TOKEN": self.token}

    async def _convert(self, data: dict) -> AstrBotMessage:
        if "TypeName" in data:
            type_name = data["TypeName"]
        elif "type_name" in data:
            type_name = data["type_name"]
        else:
            raise Exception("无法识别的消息类型")

        # 以下没有业务处理，只是避免控制台打印太多的日志
        if type_name == "ModContacts":
            logger.info("gewechat下发：ModContacts消息通知。")
            return
        if type_name == "DelContacts":
            logger.info("gewechat下发：DelContacts消息通知。")
            return

        if type_name == "Offline":
            logger.critical("收到 gewechat 下线通知。")
            return

        d = None
        if "Data" in data:
            d = data["Data"]
        elif "data" in data:
            d = data["data"]

        if not d:
            logger.warning(f"消息不含 data 字段: {data}")
            return

        if "CreateTime" in d:
            # 得到系统 UTF+8 的 ts
            tz_offset = datetime.timedelta(hours=8)
            tz = datetime.timezone(tz_offset)
            ts = datetime.datetime.now(tz).timestamp()
            create_time = d["CreateTime"]
            if create_time < ts - 30:
                logger.warning(f"消息时间戳过旧: {create_time}，当前时间戳: {ts}")
                return

        abm = AstrBotMessage()

        from_user_name = d["FromUserName"]["string"]  # 消息来源
        d["to_wxid"] = from_user_name  # 用于发信息

        abm.message_id = str(d.get("MsgId"))
        abm.session_id = from_user_name
        abm.self_id = data["Wxid"]  # 机器人的 wxid

        user_id = ""  # 发送人 wxid
        content = d["Content"]["string"]  # 消息内容

        at_me = False
        at_wxids = []
        if "@chatroom" in from_user_name:
            abm.type = MessageType.GROUP_MESSAGE
            _t = content.split(":\n")
            user_id = _t[0]
            content = _t[1]
            # at
            msg_source = d["MsgSource"]
            if "\u2005" in content:
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
            if "在群聊中@了你" in d.get("PushContent", ""):
                at_me = True
        else:
            abm.type = MessageType.FRIEND_MESSAGE
            user_id = from_user_name

        # 检查消息是否由自己发送，若是则忽略
        # 已经有可配置项专门配置是否需要响应自己的消息，因此这里注释掉。
        # if user_id == abm.self_id:
        #     logger.info("忽略自己发送的消息")
        #     return None

        abm.message = []

        # 解析用户真实名字
        user_real_name = "unknown"
        if abm.group_id:
            if (
                abm.group_id not in self.userrealnames
                or user_id not in self.userrealnames[abm.group_id]
            ):
                # 获取群成员列表，并且缓存
                if abm.group_id not in self.userrealnames:
                    self.userrealnames[abm.group_id] = {}
                member_list = await self.get_chatroom_member_list(abm.group_id)
                logger.debug(f"获取到 {abm.group_id} 的群成员列表。")
                if member_list and "memberList" in member_list:
                    for member in member_list["memberList"]:
                        self.userrealnames[abm.group_id][member["wxid"]] = member[
                            "nickName"
                        ]
                if user_id in self.userrealnames[abm.group_id]:
                    user_real_name = self.userrealnames[abm.group_id][user_id]
            else:
                user_real_name = self.userrealnames[abm.group_id][user_id]
        else:
            try:
                info = (await self.get_user_or_group_info(user_id))["data"][0]
                user_real_name = info["nickName"]
            except Exception as e:
                logger.debug(f"获取用户 {user_id} 昵称失败: {e}")
                user_real_name = user_id

        if at_me:
            abm.message.insert(0, At(qq=abm.self_id, name=self.nickname))
        for wxid in at_wxids:
            # 群聊里 At 其他人的列表
            _username = self.userrealnames.get(abm.group_id, {}).get(wxid, wxid)
            abm.message.append(At(qq=wxid, name=_username))

        abm.sender = MessageMember(user_id, user_real_name)
        abm.raw_message = d
        abm.message_str = ""

        if user_id == "weixin":
            # 忽略微信团队消息
            return

        # 不同消息类型
        match d["MsgType"]:
            case 1:
                # 文本消息
                abm.message.append(Plain(content))
                abm.message_str = content
            case 3:
                # 图片消息
                file_url = await self.multimedia_downloader.download_image(
                    self.appid, content
                )
                logger.debug(f"下载图片: {file_url}")
                file_path = await download_image_by_url(file_url)
                abm.message.append(Image(file=file_path, url=file_path))

            case 34:
                # 语音消息
                if "ImgBuf" in d and "buffer" in d["ImgBuf"]:
                    voice_data = base64.b64decode(d["ImgBuf"]["buffer"])
                    temp_dir = os.path.join(get_astrbot_data_path(), "temp")
                    file_path = os.path.join(
                        temp_dir, f"gewe_voice_{abm.message_id}.silk"
                    )

                    async with await anyio.open_file(file_path, "wb") as f:
                        await f.write(voice_data)
                    abm.message.append(Record(file=file_path, url=file_path))

            # 以下已知消息类型，没有业务处理，只是避免控制台打印太多的日志
            case 37:  # 好友申请
                logger.info("消息类型(37)：好友申请")
            case 42:  # 名片
                logger.info("消息类型(42)：名片")
            case 43:  # 视频
                video = Video(file="", cover=content)
                abm.message.append(video)
            case 47:  # emoji
                data_parser = GeweDataParser(content, abm.group_id == "")
                emoji = data_parser.parse_emoji()
                abm.message.append(emoji)
            case 48:  # 地理位置
                logger.info("消息类型(48)：地理位置")
            case 49:  # 公众号/文件/小程序/引用/转账/红包/视频号/群聊邀请
                data_parser = GeweDataParser(content, abm.group_id == "")
                segments = data_parser.parse_mutil_49()
                if segments:
                    abm.message.extend(segments)
                    for seg in segments:
                        if isinstance(seg, Plain):
                            abm.message_str += seg.text
            case 51:  # 帐号消息同步?
                logger.info("消息类型(51)：帐号消息同步？")
            case 10000:  # 被踢出群聊/更换群主/修改群名称
                logger.info("消息类型(10000)：被踢出群聊/更换群主/修改群名称")
            case 10002:  # 撤回/拍一拍/成员邀请/被移出群聊/解散群聊/群公告/群待办
                logger.info(
                    "消息类型(10002)：撤回/拍一拍/成员邀请/被移出群聊/解散群聊/群公告/群待办"
                )

            case _:
                logger.info(f"未实现的消息类型: {d['MsgType']}")
                abm.raw_message = d

        logger.debug(f"abm: {abm}")
        return abm

    async def _callback(self):
        data = await quart.request.json
        logger.debug(f"收到 gewechat 回调: {data}")

        if data.get("testMsg", None):
            return quart.jsonify({"r": "AstrBot ACK"})

        abm = None
        try:
            abm = await self._convert(data)
        except BaseException as e:
            logger.warning(
                f"尝试解析 GeweChat 下发的消息时遇到问题: {e}。下发消息内容: {data}。"
            )

        if abm:
            coro = getattr(self, "on_event_received")
            if coro:
                await coro(abm)

        return quart.jsonify({"r": "AstrBot ACK"})

    async def _register_file(self, file_path: str) -> str:
        """向 AstrBot 回调服务器 注册一个允许外部访问的文件。

        Args:
            file_path (str): 文件路径。
        Returns:
            str: 返回一个 auth_token，文件路径为 file_path。通过 /astrbot-gewechat/file/auth_token 得到文件。
        """
        async with self.lock:
            if not os.path.exists(file_path):
                raise Exception(f"文件不存在: {file_path}")

            file_token = str(uuid.uuid4())
            self.staged_files[file_token] = file_path
            return file_token

    async def _handle_file(self, file_token):
        async with self.lock:
            if file_token not in self.staged_files:
                logger.warning(f"请求的文件 {file_token} 不存在。")
                return quart.abort(404)
            if not os.path.exists(self.staged_files[file_token]):
                logger.warning(f"请求的文件 {self.staged_files[file_token]} 不存在。")
                return quart.abort(404)
            file_path = self.staged_files[file_token]
            self.staged_files.pop(file_token, None)
            return await quart.send_file(file_path)

    async def _set_callback_url(self):
        logger.info("设置回调，请等待...")
        await asyncio.sleep(3)
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/tools/setCallback",
                headers=self.headers,
                json={"token": self.token, "callbackUrl": self.callback_url},
            ) as resp:
                json_blob = await resp.json()
                logger.info(f"设置回调结果: {json_blob}")
                if json_blob["ret"] != 200:
                    raise Exception(f"设置回调失败: {json_blob}")
                logger.info(
                    f"将在 {self.callback_url} 上接收 gewechat 下发的消息。如果一直没收到消息请先尝试重启 AstrBot。如果仍没收到请到管理面板聊天页输入 /gewe_logout 重新登录。"
                )

    async def start_polling(self):
        threading.Thread(target=asyncio.run, args=(self._set_callback_url(),)).start()
        await self.server.run_task(
            host="0.0.0.0",
            port=self.port,
            shutdown_trigger=self.shutdown_trigger,
        )

    async def shutdown_trigger(self):
        await self.shutdown_event.wait()

    async def check_online(self, appid: str):
        """检查 APPID 对应的设备是否在线。"""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/login/checkOnline",
                headers=self.headers,
                json={"appId": appid},
            ) as resp:
                json_blob = await resp.json()
                return json_blob["data"]

    async def logout(self):
        """登出 gewechat。"""
        if self.appid:
            online = await self.check_online(self.appid)
            if online:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{self.base_url}/login/logout",
                        headers=self.headers,
                        json={"appId": self.appid},
                    ) as resp:
                        json_blob = await resp.json()
                        logger.info(f"登出结果: {json_blob}")

    async def login(self):
        """登录 gewechat。一般来说插件用不到这个方法。"""
        if self.token is None:
            await self.get_token_id()

        self.multimedia_downloader = GeweDownloader(
            self.base_url, self.download_base_url, self.token
        )

        if self.appid:
            try:
                online = await self.check_online(self.appid)
                if online:
                    logger.info(f"APPID: {self.appid} 已在线")
                    return
            except Exception as e:
                logger.error(f"检查在线状态失败: {e}")
                sp.put(f"gewechat-appid-{self.nickname}", "")
                self.appid = None

        payload = {"appId": self.appid}

        if self.appid:
            logger.info(f"使用 APPID: {self.appid}, {self.nickname}")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/login/getLoginQrCode",
                    headers=self.headers,
                    json=payload,
                ) as resp:
                    json_blob = await resp.json()
                    if json_blob["ret"] != 200:
                        error_msg = json_blob.get("data", {}).get("msg", "")
                        if "设备不存在" in error_msg:
                            logger.error(
                                f"检测到无效的appid: {self.appid}，将清除并重新登录。"
                            )
                            sp.put(f"gewechat-appid-{self.nickname}", "")
                            self.appid = None
                            return await self.login()
                        else:
                            raise Exception(f"获取二维码失败: {json_blob}")
                    qr_data = json_blob["data"]["qrData"]
                    qr_uuid = json_blob["data"]["uuid"]
                    appid = json_blob["data"]["appId"]
                    logger.info(f"APPID: {appid}")
                    logger.warning(
                        f"请打开该网址，然后使用微信扫描二维码登录: https://api.cl2wm.cn/api/qrcode/code?text={qr_data}"
                    )
        except Exception as e:
            raise e

        # 执行登录
        retry_cnt = 64
        payload.update({"uuid": qr_uuid, "appId": appid})
        while retry_cnt > 0:
            retry_cnt -= 1

            # 需要验证码
            temp_dir = os.path.join(get_astrbot_data_path(), "temp")
            code_file_path = os.path.join(temp_dir, "gewe_code")
            if os.path.exists(code_file_path):
                with open(code_file_path, "r") as f:
                    code = f.read().strip()
                    if not code:
                        logger.warning(
                            "未找到验证码，请在管理面板聊天页输入 /gewe_code 验证码 来验证，如 /gewe_code 123456"
                        )
                        await asyncio.sleep(5)
                        continue
                    payload["captchCode"] = code
                    logger.info(f"使用验证码: {code}")
                    try:
                        os.remove(code_file_path)
                    except Exception:
                        logger.warning(f"删除验证码文件 {code_file_path} 失败。")

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/login/checkLogin",
                    headers=self.headers,
                    json=payload,
                ) as resp:
                    json_blob = await resp.json()
                    logger.info(f"检查登录状态: {json_blob}")

                    ret = json_blob["ret"]
                    msg = ""
                    if json_blob["data"] and "msg" in json_blob["data"]:
                        msg = json_blob["data"]["msg"]
                    if ret == 500 and "安全验证码" in msg:
                        logger.warning(
                            "此次登录需要安全验证码，请在管理面板聊天页输入 /gewe_code 验证码 来验证，如 /gewe_code 123456"
                        )
                    else:
                        if "status" in json_blob["data"]:
                            status = json_blob["data"]["status"]
                            nickname = json_blob["data"].get("nickName", "")
                            if status == 1:
                                logger.info(f"等待确认...{nickname}")
                            elif status == 2:
                                logger.info(f"绿泡泡平台登录成功: {nickname}")
                                break
                            elif status == 0:
                                logger.info("等待扫码...")
                            else:
                                logger.warning(f"未知状态: {status}")
            await asyncio.sleep(5)

        if appid:
            sp.put(f"gewechat-appid-{self.nickname}", appid)
            self.appid = appid
            logger.info(f"已保存 APPID: {appid}")

    """API 部分。Gewechat 的 API 文档请参考: https://apifox.com/apidoc/shared/69ba62ca-cb7d-437e-85e4-6f3d3df271b1
    """

    async def get_chatroom_member_list(self, chatroom_wxid: str) -> dict:
        """获取群成员列表。

        Args:
            chatroom_wxid (str): 微信群聊的id。可以通过 event.get_group_id() 获取。

        Returns:
            dict: 返回群成员列表字典。其中键为 memberList 的值为群成员列表。
        """
        payload = {"appId": self.appid, "chatroomId": chatroom_wxid}

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/group/getChatroomMemberList",
                headers=self.headers,
                json=payload,
            ) as resp:
                json_blob = await resp.json()
                return json_blob["data"]

    async def post_text(self, to_wxid, content: str, ats: str = ""):
        """发送纯文本消息"""
        payload = {
            "appId": self.appid,
            "toWxid": to_wxid,
            "content": content,
        }
        if ats:
            payload["ats"] = ats

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/message/postText", headers=self.headers, json=payload
            ) as resp:
                json_blob = await resp.json()
                logger.debug(f"发送消息结果: {json_blob}")

    async def post_image(self, to_wxid, image_url: str):
        """发送图片消息"""
        payload = {
            "appId": self.appid,
            "toWxid": to_wxid,
            "imgUrl": image_url,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/message/postImage", headers=self.headers, json=payload
            ) as resp:
                json_blob = await resp.json()
                logger.debug(f"发送图片结果: {json_blob}")

    async def post_emoji(self, to_wxid, emoji_md5, emoji_size, cdnurl=""):
        """发送emoji消息"""
        payload = {
            "appId": self.appid,
            "toWxid": to_wxid,
            "emojiMd5": emoji_md5,
            "emojiSize": emoji_size,
        }

        # 优先表情包，若拿不到表情包的md5，就用当作图片发
        try:
            if emoji_md5 != "" and emoji_size != "":
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{self.base_url}/message/postEmoji",
                        headers=self.headers,
                        json=payload,
                    ) as resp:
                        json_blob = await resp.json()
                        logger.info(
                            f"发送emoji消息结果: {json_blob.get('msg', '操作失败')}"
                        )
            else:
                await self.post_image(to_wxid, cdnurl)

        except Exception as e:
            logger.error(e)

    async def post_video(
        self, to_wxid, video_url: str, thumb_url: str, video_duration: int
    ):
        payload = {
            "appId": self.appid,
            "toWxid": to_wxid,
            "videoUrl": video_url,
            "thumbUrl": thumb_url,
            "videoDuration": video_duration,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/message/postVideo", headers=self.headers, json=payload
            ) as resp:
                json_blob = await resp.json()
                logger.debug(f"发送视频结果: {json_blob}")

    async def forward_video(self, to_wxid, cnd_xml: str):
        """转发视频

        Args:
            to_wxid (str): 发送给谁
            cnd_xml (str): 视频消息的cdn信息
        """
        payload = {
            "appId": self.appid,
            "toWxid": to_wxid,
            "xml": cnd_xml,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/message/forwardVideo",
                headers=self.headers,
                json=payload,
            ) as resp:
                json_blob = await resp.json()
                logger.debug(f"转发视频结果: {json_blob}")

    async def post_voice(self, to_wxid, voice_url: str, voice_duration: int):
        """发送语音信息

        Args:
            voice_url (str): 语音文件的网络链接
            voice_duration (int): 语音时长，毫秒
        """
        payload = {
            "appId": self.appid,
            "toWxid": to_wxid,
            "voiceUrl": voice_url,
            "voiceDuration": voice_duration,
        }

        logger.debug(f"发送语音: {payload}")

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/message/postVoice", headers=self.headers, json=payload
            ) as resp:
                json_blob = await resp.json()
                logger.info(f"发送语音结果: {json_blob.get('msg', '操作失败')}")

    async def post_file(self, to_wxid, file_url: str, file_name: str):
        """发送文件

        Args:
            to_wxid (string): 微信ID
            file_url (str): 文件的网络链接
            file_name (str): 文件名
        """
        payload = {
            "appId": self.appid,
            "toWxid": to_wxid,
            "fileUrl": file_url,
            "fileName": file_name,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/message/postFile", headers=self.headers, json=payload
            ) as resp:
                json_blob = await resp.json()
                logger.debug(f"发送文件结果: {json_blob}")

    async def add_friend(self, v3: str, v4: str, content: str):
        """申请添加好友"""
        payload = {
            "appId": self.appid,
            "scene": 3,
            "content": content,
            "v4": v4,
            "v3": v3,
            "option": 2,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/contacts/addContacts",
                headers=self.headers,
                json=payload,
            ) as resp:
                json_blob = await resp.json()
                logger.debug(f"申请添加好友结果: {json_blob}")
                return json_blob

    async def get_group(self, group_id: str):
        payload = {
            "appId": self.appid,
            "chatroomId": group_id,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/group/getChatroomInfo",
                headers=self.headers,
                json=payload,
            ) as resp:
                json_blob = await resp.json()
                logger.debug(f"获取群信息结果: {json_blob}")
                return json_blob

    async def get_group_member(self, group_id: str):
        payload = {
            "appId": self.appid,
            "chatroomId": group_id,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/group/getChatroomMemberList",
                headers=self.headers,
                json=payload,
            ) as resp:
                json_blob = await resp.json()
                logger.debug(f"获取群信息结果: {json_blob}")
                return json_blob

    async def accept_group_invite(self, url: str):
        """同意进群"""
        payload = {"appId": self.appid, "url": url}

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/group/agreeJoinRoom",
                headers=self.headers,
                json=payload,
            ) as resp:
                json_blob = await resp.json()
                logger.debug(f"获取群信息结果: {json_blob}")
                return json_blob

    async def add_group_member_to_friend(
        self, group_id: str, to_wxid: str, content: str
    ):
        payload = {
            "appId": self.appid,
            "chatroomId": group_id,
            "content": content,
            "memberWxid": to_wxid,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/group/addGroupMemberAsFriend",
                headers=self.headers,
                json=payload,
            ) as resp:
                json_blob = await resp.json()
                logger.debug(f"获取群信息结果: {json_blob}")
                return json_blob

    async def get_user_or_group_info(self, *ids):
        """
        获取用户或群组信息。

        :param ids: 可变数量的 wxid 参数
        """

        wxids_str = list(ids)

        payload = {
            "appId": self.appid,
            "wxids": wxids_str,  # 使用逗号分隔的字符串
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/contacts/getDetailInfo",
                headers=self.headers,
                json=payload,
            ) as resp:
                json_blob = await resp.json()
                logger.debug(f"获取群信息结果: {json_blob}")
                return json_blob

    async def get_contacts_list(self):
        """
        获取通讯录列表
        见 https://apifox.com/apidoc/shared/69ba62ca-cb7d-437e-85e4-6f3d3df271b1/api-196794504
        """
        payload = {"appId": self.appid}

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/contacts/fetchContactsList",
                headers=self.headers,
                json=payload,
            ) as resp:
                json_blob = await resp.json()
                logger.debug(f"获取通讯录列表结果: {json_blob}")
                return json_blob
