import threading
import asyncio
import aiohttp
import quart

from astrbot.api.platform import AstrBotMessage, MessageMember, MessageType
from astrbot.api.message_components import Plain, Image, At
from astrbot.api import logger, sp

class SimpleGewechatClient():
    '''针对 Gewechat 的简单实现。
    
    @author: Soulter
    @website: https://github.com/Soulter
    '''
    def __init__(self, base_url: str, nickname: str, host: str, port: int, event_queue: asyncio.Queue):
        self.base_url = base_url
        if self.base_url.endswith('/'):
            self.base_url = self.base_url[:-1]
        
        self.base_url += "/v2/api"
        
        if isinstance(port, str):
            port = int(port)
            
        self.token = None
        self.headers = {}
        self.nickname = nickname
        self.appid = sp.get(f"gewechat-appid-{nickname}", "")
        self.callback_url = None
        
        self.server = quart.Quart(__name__)
        self.server.add_url_rule('/astrbot-gewechat/callback', view_func=self.callback, methods=['POST'])  
        
        self.host = host
        self.port = port 
        
        self.event_queue = event_queue
    
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
        abm = AstrBotMessage()
        d = data['Data']
        msg_type = d['MsgType']
        
        match msg_type:
            case 1:
                from_user_name = d['FromUserName']['string'] # 消息来源
                d['to_wxid'] = from_user_name # 用于发信息
                
                user_id = "" # 发送人 wxid
                content = d['Content']['string'] # 消息内容
                user_real_name = d['PushContent'].split(' : ')[0] # 真实昵称
                user_real_name.replace('在群聊中@了你', '') # trick
                abm.self_id = data['Wxid'] # 机器人的 wxid
                at_me = False
                if "@chatroom" in from_user_name:
                    abm.type = MessageType.GROUP_MESSAGE
                    _t = content.split(':\n')
                    user_id = _t[0]
                    content = _t[1]
                    if '\u2005' in content: 
                        # at
                        content = content.split('\u2005')[1]
                    
                    abm.group_id = from_user_name
                    
                    # at
                    msg_source = d['MsgSource']
                    if f'<atuserlist><![CDATA[,{abm.self_id}]]>' in msg_source:
                        at_me = True
                    
                else:
                    abm.type = MessageType.FRIEND_MESSAGE
                    user_id = from_user_name
                abm.session_id = from_user_name
                abm.sender = MessageMember(user_id, user_real_name)
                abm.message = [Plain(content)]
                
                if at_me:
                    abm.message.insert(0, At(qq=abm.self_id))
                
                abm.message_id = str(d['MsgId'])
                abm.raw_message = d
                abm.message_str = content
                
                logger.info(f"abm: {abm}")
                return abm
            case _:
                logger.error(f"未实现的消息类型: {msg_type}")
                
    async def callback(self):
        data = await quart.request.json
        logger.debug(f"收到 gewechat 回调: {data}")
        
        if data.get('testMsg', None):
            return quart.jsonify({"r": "AstrBot ACK"})
        
        abm = await self._convert(data)
        
        if abm:
            coro = getattr(self, "on_event_received")
            if coro:
                await coro(abm)
            
        return quart.jsonify({"r": "AstrBot ACK"})
        
    async def _set_callback_url(self):
        logger.info("设置回调，请等待...")
        await asyncio.sleep(3)
        callback_url = f"http://{self.host}:{self.port}/astrbot-gewechat/callback"
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/tools/setCallback",
                headers=self.headers,
                json={
                    "token": self.token,
                    "callbackUrl": callback_url
                }
            ) as resp:
                json_blob = await resp.json()
                logger.info(f"设置回调结果: {json_blob}")
                if json_blob['ret'] != 200:
                    raise Exception(f"设置回调失败: {json_blob}")
                logger.info(f"将在 {callback_url} 上接收 gewechat 下发的消息。")
        
    async def start_polling(self):
        
        # 设置回调
        threading.Thread(target=asyncio.run, args=(self._set_callback_url(),)).start()

                
        await self.server.run_task(
            host=self.host, 
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
            
        if not self.appid and appid:
            sp.put(f"gewechat-appid-{nickname}", appid)
            self.appid = appid
            logger.info(f"已保存 APPID: {appid}")
    
    async def post_text(self, to_wxid, content: str):
        payload = {
            "appId": self.appid,
            "toWxid": to_wxid,
            "content": content,
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/message/postText",
                headers=self.headers,
                json=payload
            ) as resp:
                json_blob = await resp.json()
                logger.info(f"发送消息结果: {json_blob}")