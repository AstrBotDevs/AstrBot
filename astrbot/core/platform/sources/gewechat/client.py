import threading
import asyncio
import aiohttp
import quart
import base64
import datetime
import re
from astrbot.api.platform import AstrBotMessage, MessageMember, MessageType
from astrbot.api.message_components import Plain, Image, At, Record
from astrbot.api import logger, sp
from .downloader import GeweDownloader
from astrbot.core.utils.io import download_image_by_url


class SimpleGewechatClient():
    '''针对 Gewechat 的简单实现。
    
    @author: Soulter
    @website: https://github.com/Soulter
    '''
    def __init__(self, base_url: str, nickname: str, host: str, port: int, event_queue: asyncio.Queue):
        self.base_url = base_url
        if self.base_url.endswith('/'):
            self.base_url = self.base_url[:-1]
            
        self.download_base_url = self.base_url.split(':')[:-1] # 去掉端口
        self.download_base_url = ':'.join(self.download_base_url) + ":2532/download/"
        
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
        self.server.add_url_rule('/astrbot-gewechat/callback', view_func=self.callback, methods=['POST'])
        self.server.add_url_rule('/astrbot-gewechat/file/<file_id>', view_func=self.handle_file, methods=['GET'])
        
        self.host = host
        self.port = port 
        self.callback_url = f"http://{self.host}:{self.port}/astrbot-gewechat/callback"
        self.file_server_url = f"http://{self.host}:{self.port}/astrbot-gewechat/file"
        
        self.event_queue = event_queue
        
        self.multimedia_downloader = None
    
    async def get_token_id(self):
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.base_url}/tools/getTokenId") as resp:
                json_blob = await resp.json()
                self.token = json_blob['data']
                logger.info(f"获取到 Gewechat Token: {self.token}")
                self.headers = {
                    "X-GEWE-TOKEN": self.token
                }
                
    async def _convert(self, data: dict) -> AstrBotMessage:
        type_name = data['TypeName']
        if type_name == "Offline":
            logger.critical("收到 gewechat 下线通知。")
            return
        
        if 'Data' in data and 'CreateTime' in data['Data']:
            # 得到系统 UTF+8 的 ts
            tz_offset = datetime.timedelta(hours=8)
            tz = datetime.timezone(tz_offset)
            ts = datetime.datetime.now(tz).timestamp()
            create_time = data['Data']['CreateTime']
            if create_time < ts - 30:
                logger.warning(f"消息时间戳过旧: {create_time}，当前时间戳: {ts}")
                return

        
        abm = AstrBotMessage()
        d = data['Data']
    
        from_user_name = d['FromUserName']['string'] # 消息来源
        d['to_wxid'] = from_user_name # 用于发信息
        
        abm.message_id = str(d.get('MsgId'))
        abm.session_id = from_user_name
        abm.self_id = data['Wxid'] # 机器人的 wxid
        
        user_id = "" # 发送人 wxid
        content = d['Content']['string'] # 消息内容
        
        at_me = False
        if "@chatroom" in from_user_name:
            abm.type = MessageType.GROUP_MESSAGE
            _t = content.split(':\n')
            user_id = _t[0]
            content = _t[1]
            if '\u2005' in content: 
                # at
                # content = content.split('\u2005')[1]
                content = re.sub(r'@[^\u2005]*\u2005', '', content)
            abm.group_id = from_user_name
            # at
            msg_source = d['MsgSource']
            if f'<atuserlist><![CDATA[,{abm.self_id}]]>' in msg_source \
                or f'<atuserlist><![CDATA[{abm.self_id}]]>' in msg_source:
                at_me = True
            if '在群聊中@了你' in d.get('PushContent', ''):
                at_me = True
        else:
            abm.type = MessageType.FRIEND_MESSAGE
            user_id = from_user_name
            
        abm.message = []
        if at_me:
            abm.message.insert(0, At(qq=abm.self_id))
        
        user_real_name = d.get('PushContent', 'unknown : ').split(' : ')[0] \
            .replace('在群聊中@了你', '') \
            .replace('在群聊中发了一段语音', '') \
            .replace('在群聊中发了一张图片', '') # 真实昵称
        abm.sender = MessageMember(user_id, user_real_name)
        abm.raw_message = d
        abm.message_str = ""
        # 不同消息类型
        match d['MsgType']:
            case 1:
                # 文本消息
                abm.message.append(Plain(content))
                abm.message_str = content
            case 3:
                # 图片消息
                file_url = await self.multimedia_downloader.download_image(
                    self.appid, 
                    content
                )
                logger.debug(f"下载图片: {file_url}")
                file_path = await download_image_by_url(file_url)
                abm.message.append(Image(file=file_path, url=file_path))
                
            case 34:
                # 语音消息
                # data = await self.multimedia_downloader.download_voice(
                #     self.appid, 
                #     content, 
                #     abm.message_id
                # )
                # print(data)
                if 'ImgBuf' in d and 'buffer' in d['ImgBuf']:
                    voice_data = base64.b64decode(d['ImgBuf']['buffer'])
                    file_path = f"data/temp/gewe_voice_{abm.message_id}.silk"
                    with open(file_path, "wb") as f:
                        f.write(voice_data)
                    abm.message.append(Record(file=file_path, url=file_path))
            case _:
                logger.info(f"未实现的消息类型: {d['MsgType']}")
                abm.raw_message = d
        
        logger.debug(f"abm: {abm}")
        return abm

    async def callback(self):
        data = await quart.request.json
        logger.debug(f"收到 gewechat 回调: {data}")
        
        if data.get('testMsg', None):
            return quart.jsonify({"r": "AstrBot ACK"})
        
        abm = None
        try:
            abm = await self._convert(data)
        except BaseException as e:
            logger.warning(f"尝试解析 GeweChat 下发的消息时遇到问题: {e}。下发消息内容: {data}。")
            
        if abm:
            coro = getattr(self, "on_event_received")
            if coro:
                await coro(abm)
        
        return quart.jsonify({"r": "AstrBot ACK"})
    
    async def handle_file(self, file_id):
        file_path = f"data/temp/{file_id}"
        return await quart.send_file(file_path)
        
    async def _set_callback_url(self):
        logger.info("设置回调，请等待...")
        await asyncio.sleep(3)
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/tools/setCallback",
                headers=self.headers,
                json={
                    "token": self.token,
                    "callbackUrl": self.callback_url
                }
            ) as resp:
                json_blob = await resp.json()
                logger.info(f"设置回调结果: {json_blob}")
                if json_blob['ret'] != 200:
                    raise Exception(f"设置回调失败: {json_blob}")
                logger.info(f"将在 {self.callback_url} 上接收 gewechat 下发的消息。如果一直没收到消息请先尝试重启 AstrBot。如果仍没收到请到管理面板聊天页输入 /gewe_logout 重新登录。")
        
    async def start_polling(self):
        threading.Thread(target=asyncio.run, args=(self._set_callback_url(),)).start()
        await self.server.run_task(
            host='0.0.0.0', 
            port=self.port, 
            shutdown_trigger=self.shutdown_trigger_placeholder
        )
    
    async def shutdown_trigger_placeholder(self):
        while not self.event_queue.closed:
            await asyncio.sleep(1)
        logger.info("gewechat 适配器已关闭。")
        
    async def check_online(self, appid: str):
        # /login/checkOnline
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/login/checkOnline",
                headers=self.headers,
                json={
                    "appId": appid
                }
            ) as resp:
                json_blob = await resp.json()
                return json_blob['data']
            
    async def logout(self):
        if self.appid:
            online = await self.check_online(self.appid)
            if online:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{self.base_url}/login/logout",
                        headers=self.headers,
                        json={
                            "appId": self.appid
                        }
                    ) as resp:
                        json_blob = await resp.json()
                        logger.info(f"登出结果: {json_blob}")
        
    async def login(self):
        if self.token is None:
            await self.get_token_id()
            
        self.multimedia_downloader = GeweDownloader(self.base_url, self.download_base_url, self.token)
        
        if self.appid:
            online = await self.check_online(self.appid)
            if online:
                logger.info(f"APPID: {self.appid} 已在线")
                return
        
        payload = {
            "appId": self.appid
        }
        
        if self.appid:
            logger.info(f"使用 APPID: {self.appid}, {self.nickname}")
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/login/getLoginQrCode", 
                headers=self.headers,
                json=payload
            ) as resp:
                json_blob = await resp.json()
                if json_blob['ret'] != 200:
                    raise Exception(f"获取二维码失败: {json_blob}")
                qr_data = json_blob['data']['qrData']
                qr_uuid = json_blob['data']['uuid']
                appid = json_blob['data']['appId']
                logger.info(f"APPID: {appid}")
                logger.warning(f"请打开该网址，然后使用微信扫描二维码登录: https://api.cl2wm.cn/api/qrcode/code?text={qr_data}")
        
        # 执行登录
        retry_cnt = 64
        payload.update({
            "uuid": qr_uuid,
            "appId": appid
        })
        while retry_cnt > 0:
            retry_cnt -= 1
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/login/checkLogin",
                    headers=self.headers,
                    json=payload
                ) as resp:
                    json_blob = await resp.json()
                    logger.info(f"检查登录状态: {json_blob}")
                    status = json_blob['data']['status']
                    nickname = json_blob['data'].get('nickName', '')
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
    
    async def post_text(self, to_wxid, content: str, ats: str = ""):
        payload = {
            "appId": self.appid,
            "toWxid": to_wxid,
            "content": content,
        }
        if ats:
            payload['ats'] = ats
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/message/postText",
                headers=self.headers,
                json=payload
            ) as resp:
                json_blob = await resp.json()
                logger.debug(f"发送消息结果: {json_blob}")
                
    async def post_image(self, to_wxid, image_url: str):
        payload = {
            "appId": self.appid,
            "toWxid": to_wxid,
            "imgUrl": image_url,
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/message/postImage",
                headers=self.headers,
                json=payload
            ) as resp:
                json_blob = await resp.json()
                logger.debug(f"发送图片结果: {json_blob}")
                
    async def post_voice(self, to_wxid, voice_url: str, voice_duration: int):
        payload = {
            "appId": self.appid,
            "toWxid": to_wxid,
            "voiceUrl": voice_url,
            "voiceDuration": voice_duration
        }
        
        logger.debug(f"发送语音: {payload}")
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/message/postVoice",
                headers=self.headers,
                json=payload
            ) as resp:
                json_blob = await resp.json()
                logger.debug(f"发送语音结果: {json_blob}")
                
    async def post_file(self, to_wxid, file_url: str, file_name: str):
        payload = {
            "appId": self.appid,
            "toWxid": to_wxid,
            "fileUrl": file_url,
            "fileName": file_name
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/message/postFile",
                headers=self.headers,
                json=payload
            ) as resp:
                json_blob = await resp.json()
                logger.debug(f"发送文件结果: {json_blob}")