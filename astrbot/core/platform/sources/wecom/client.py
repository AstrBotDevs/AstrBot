
import asyncio
import aiohttp
import quart
import base64

from astrbot.api.platform import AstrBotMessage, MessageMember, MessageType
from astrbot.api.message_components import Plain, Image, At, Record
from astrbot.api import logger, sp
from .downloader import GeweDownloader
from astrbot.core.utils.io import download_image_by_url


class WeComClient():
    def __init__(self, config: dict):
        self.base_url = base_url
        if self.base_url.endswith('/'):
            self.base_url = self.base_url[:-1]
            
        self.download_base_url = self.base_url.split(':')[:-1] # 去掉端口
        self.download_base_url = ':'.join(self.download_base_url) + ":2532/download/"
        
        self.base_url += "/v2/api"
        
        logger.info(f"wecom API: {self.base_url}")
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
    