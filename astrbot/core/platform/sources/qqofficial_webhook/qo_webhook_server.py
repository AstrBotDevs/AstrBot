import aiohttp
import quart
import json
import asyncio
import typing
from botpy import BotAPI, BotHttp, Client, Token, BotWebSocket, ConnectionSession
from astrbot.api import logger

class QQOfficialWebhook():
    def __init__(self, config: dict, event_queue: asyncio.Queue):
        self.appid = config['appid']
        self.secret = config['secret']
        self.port = config.get("port", 6194)
        
        if isinstance(self.port, str):
            self.port = int(self.port)
        
        self.http: BotHttp = BotHttp(timeout=300)
        self.api: BotAPI = BotAPI(http=self.http)
        
        self.token = Token(self.appid, self.secret)
        
        self.server = quart.Quart(__name__)
        self.server.add_url_rule('/astrbot-qo-webhook/callback', view_func=self.callback, methods=['POST'])
        
        self.event_queue = event_queue
        
    async def initialize(self):
        self.user = await self.http.login(self.token)
        logger.info(f"已登录 QQ 官方机器人账号: {self.user}")
        
        async def bot_connect():
            pass
        
        self._connection = ConnectionSession(
            max_async=1,
            connect=bot_connect,
            dispatch=self.dispatch,
            loop=asyncio.get_event_loop(),
            api=self.api,
        )
    
    async def dispatch(self, event: str, *args: typing.Any, **kwargs: typing.Any):
        print("dispatch:", locals())
        
    async def callback(self):
        msg: dict = await quart.request.json
        logger.debug(f"收到 qq_official_webhook 回调: {msg}")

        # if await self._is_system_event(msg, ws):
        #     return

        event = msg.get("t")
        opcode = msg.get("op")
        event_seq = msg["s"]
        # if event_seq > 0:
        #     self._session["last_seq"] = event_seq

        if event == "READY":
            # 心跳检查
            pass

        if event == "RESUMED":
            # 心跳检查
            pass

        if event and opcode == BotWebSocket.WS_DISPATCH_EVENT:
            event = msg["t"].lower()
            try:
                func = self._connection.parser[event]
            except KeyError:
                logger.error("_parser unknown event %s.", event)
            else:
                func(msg)
                
    
    async def start_polling(self):
        await self.server.run_task(
            host='0.0.0.0', 
            port=self.port, 
            shutdown_trigger=self.shutdown_trigger_placeholder
        )
        
    async def shutdown_trigger_placeholder(self):
        while not self.event_queue.closed:
            await asyncio.sleep(1)
        logger.info("qq_official_webhook 适配器已关闭。")
        