import requests
import asyncio
import websockets
from websockets import WebSocketClientProtocol
import json
import inspect
from typing import Callable, Awaitable, Union
from pydantic import BaseModel
import datetime

class Event(BaseModel):
    GroupMessage: str = "GuildMessage"

class Sender(BaseModel):
    user_id: str
    member_openid: str


class MessageComponent(BaseModel):
    type: str

class PlainText(MessageComponent):
    text: str

class Image(MessageComponent):
    path: str
    file: str
    url: str

class MessageChain(list):

    def append(self, __object: MessageComponent) -> None:
        if not isinstance(__object, MessageComponent):
            raise TypeError("不受支持的消息链元素类型。回复的消息链必须是 MessageComponent 的子类。")
        return super().append(__object)
    
    def insert(self, __index: int, __object: MessageComponent) -> None:
        if not isinstance(__object, MessageComponent):
            raise TypeError("不受支持的消息链元素类型。回复的消息链必须是 MessageComponent 的子类。")
        return super().insert(__index, __object)
    
    def parse_from_nakuru(self, nakuru_message_chain: Union[list, str]) -> None:
        if isinstance(nakuru_message_chain, str):
            self.append(PlainText(type='Plain', text=nakuru_message_chain))
        else:
            for i in nakuru_message_chain:
                if i['type'] == 'Plain':
                    self.append(PlainText(type='Plain', text=i['text']))
                elif i['type'] == 'Image':
                    self.append(Image(path=i['path'], file=i['file'], url=i['url']))

class Message(BaseModel):
    type: str
    user_id: str
    member_openid: str
    message_id: str
    group_id: str
    group_openid: str
    content: str
    message: MessageChain
    time: int
    sender: Sender

class UnofficialQQBotSDK:

    GET_APP_ACCESS_TOKEN_URL = "https://bots.qq.com/app/getAppAccessToken"
    OPENAPI_BASE_URL = "https://api.sgroup.qq.com"

    def __init__(self, appid: str, client_secret: str) -> None:
        self.appid = appid
        self.client_secret = client_secret
        self.events: dict[str, Awaitable] = {}


    def run_bot(self) -> None:
        self.__get_access_token()
        self.__get_wss_endpoint()
        asyncio.get_event_loop().run_until_complete(self.__ws_client())

    def __get_access_token(self) -> None:
        res = requests.post(self.GET_APP_ACCESS_TOKEN_URL, json={
            "appId": self.appid,
            "clientSecret": self.client_secret
        }, headers={
            "Content-Type": "application/json"
        })
        res = res.json()
        code = res['code'] if 'code' in res else 1
        if 'access_token' not in res:
            raise Exception(f"获取 access_token 失败。原因：{res['message'] if 'message' in res else '未知'}")
        self.access_token = 'QQBot ' + res['access_token']

    def __auth_header(self) -> str:
        return {
            'Authorization': self.access_token,
            'X-Union-Appid': self.appid,
        }

    def __get_wss_endpoint(self):
        res = requests.get(self.OPENAPI_BASE_URL + "/gateway", headers=self.__auth_header())
        self.wss_endpoint = res.json()['url']
        # print("wss_endpoint: " + self.wss_endpoint)

    async def __behav_heartbeat(self, ws: WebSocketClientProtocol, t: int):
        while True:
            await asyncio.sleep(t - 1)
            try:
                await ws.send(json.dumps({
                    "op": 1,
                    "d": self.s
                }))
            except:
                print("heartbeat error.")

    async def __handle_msg(self, ws: WebSocketClientProtocol, msg: dict):
        if msg['op'] == 10:
            asyncio.get_event_loop().create_task(self.__behav_heartbeat(ws, msg['d']['heartbeat_interval'] / 1000))
            # 鉴权，获得session
            await ws.send(json.dumps({
                "op": 2,
                "d": {
                    "token": self.access_token,
                    "intents": 33554432,
                    "shard": [0, 1],
                    "properties": {
                        "$os": "linux",
                        "$browser": "my_library",
                        "$device": "my_library"
                    }
                }
            }))
        if msg['op'] == 0:
            # ready
            data = msg['d']
            event_typ: str = msg['t'] if 't' in msg else None
            if event_typ == 'GROUP_AT_MESSAGE_CREATE':
                if 'GroupMessage' in self.events:
                    coro = self.events['GroupMessage']
                else:
                    return
                message_chain = MessageChain()
                message_chain.append(PlainText(type="Plain", text=data['content']))
                group_message = Message(
                    type='GroupMessage',
                    user_id=data['author']['id'],
                    member_openid=data['author']['member_openid'],
                    message_id=data['id'],
                    group_id=data['group_id'],
                    group_openid=data['group_openid'],
                    content=data['content'],
                    # 2023-11-24T19:51:11+08:00
                    time=int(datetime.datetime.strptime(data['timestamp'], "%Y-%m-%dT%H:%M:%S%z").timestamp()),
                    sender=Sender(
                        user_id=data['author']['id'],
                        member_openid=data['author']['member_openid']
                    ),
                    message=message_chain
                )
                await coro(self, group_message)

    async def send(self, message: Message, message_chain: MessageChain) -> None:
        # todo: 消息链转换支持更多类型。
        plain_text = ""
        for i in message_chain:
            if isinstance(i, PlainText):
                plain_text += i.text
        requests.post(self.OPENAPI_BASE_URL + f"/v2/groups/{message.group_openid}/messages", headers=self.__auth_header(), json={
            "content": plain_text,
            "message_type": 0,
            "msg_id": message.message_id
        })

    async def __ws_client(self):
        self.s = 0
        async with websockets.connect(self.wss_endpoint) as websocket:
            while True:
                msg = await websocket.recv()
                msg = json.loads(msg)
                if 's' in msg:
                    self.s = msg['s']
                await self.__handle_msg(websocket, msg)
    
    def on(self, event: str) -> None:
        def wrapper(func: Awaitable):
            if inspect.iscoroutinefunction(func) == False:
                raise TypeError("func must be a coroutine function")
            self.events[event] = func
        return wrapper