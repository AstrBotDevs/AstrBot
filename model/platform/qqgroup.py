import requests
import asyncio
import websockets
from websockets import WebSocketClientProtocol
import threading
import json

class UnofficialQQBotSDK:

    GET_APP_ACCESS_TOKEN_URL = "https://bots.qq.com/app/getAppAccessToken"
    OPENAPI_BASE_URL = "https://api.sgroup.qq.com"

    def __init__(self, appid: str, client_secret: str) -> None:
        self.appid = appid
        self.client_secret = client_secret
        self.get_access_token()
        self.get_wss_endpoint()
        asyncio.get_event_loop().run_until_complete(self.ws_client())


    
    
    
    def get_access_token(self) -> None:
        res = requests.post(self.GET_APP_ACCESS_TOKEN_URL, json={
            "appId": self.appid,
            "clientSecret": self.client_secret
        }, headers={
            "Content-Type": "application/json"
        })
        print(res.text)
        self.access_token = 'QQBot ' + res.json()['access_token']
        print("access_token: " + self.access_token)

    def auth_header(self) -> str:
        return {
            'Authorization': self.access_token,
            'X-Union-Appid': self.appid,
        }

    def get_wss_endpoint(self):
        # self.wss_endpoint = requests.get(self.OPENAPI_BASE_URL + "/gateway", headers=self.auth_header()).json()['url']
        res = requests.get(self.OPENAPI_BASE_URL + "/gateway", headers=self.auth_header())
        print(res.text)
        self.wss_endpoint = res.json()['url']
        print("wss_endpoint: " + self.wss_endpoint)

    async def behav_heartbeat(self, ws: WebSocketClientProtocol, t: int):
        while True:
            await asyncio.sleep(t - 1)
            try:
                print("heartbeat., s: " + str(self.s))
                await ws.send(json.dumps({
                    "op": 1,
                    "d": self.s
                }))
            except:
                print("heartbeat error.")

    async def handle_msg(self, ws: WebSocketClientProtocol, msg: dict):
        if msg['op'] == 10:
            # hello
            # 创建心跳任务
            print("hello.")
            asyncio.get_event_loop().create_task(self.behav_heartbeat(ws, msg['d']['heartbeat_interval'] / 1000))
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
            print("ready.")
            data = msg['d']
            print(data)

            if 'group_openid' in data:
                group_openid = data['group_openid']
                message_str = data['content'].strip()
                message_id = data['id']
                # 发送消息
                requests.post(self.OPENAPI_BASE_URL + f"/v2/groups/{group_openid}/messages", headers=self.auth_header(), json={
                    "content": message_str,
                    "message_type": 0,
                    "msg_id": message_id
                })

    async def ws_client(self):
        self.s = 0
        async with websockets.connect(self.wss_endpoint) as websocket:
            print("ws connected.")
            while True:
                msg = await websocket.recv()
                msg = json.loads(msg)
                if 's' in msg:
                    self.s = msg['s']
                print("recv: " + str(msg))
                await self.handle_msg(websocket, msg)
                
    
if __name__ == "__main__":
    UnofficialQQBotSDK("", "")