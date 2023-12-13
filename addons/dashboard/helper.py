from addons.dashboard.server import AstrBotDashBoard, DashBoardData
from pydantic import BaseModel
from typing import Union, Optional
import uuid

class DashBoardConfig(BaseModel):
    type: str["group", "item"]
    name: str
    description: str
    uuid: Optional[str] # 仅 item 才需要
    body: Optional[list['DashBoardConfig']] # 仅 group 才需要
    value: Optional[Union[list, dict, str, int, bool]] # 仅 item 才需要
    val_type: Optional[str] # 仅 item 才需要

class DashBoardHelper():
    def __init__(self, dashboard_data: DashBoardData, config: dict):
        self.parse_config(config)
        self.dashboard_data: DashBoardData = dashboard_data
        self.dashboard = AstrBotDashBoard(self.dashboard_data)
        self.key_map = {} # key: uuid, value: config key name
        
        @self.dashboard.register("post_configs")
        def on_post_configs(configs: dict):
            self.dashboard_data.configs = configs
            
            return True
        
    # 将 config.yaml、 中的配置解析到 dashboard_data.configs 中
    def parse_config(self, config: dict):
        self.dashboard_data.configs = {
            "data": []
        }
        '''
 {
    "data": [
        {
            "type": "group",
            "name": "机器人平台配置",
            "description": "机器人平台配置描述",
            "body": [
                {
                    "type": "item",
                    "val_type": "bool",
                    "name": "启用 QQ 频道平台",
                    "description": "机器人平台名称描述",
                    "value": true
                },
                {
                    "type": "item",
                    "val_type": "string",
                    "name": "QQ机器人APPID",
                    "description": "机器人平台名称描述",
                    "value": "123456"
                },
                {
                    "type": "item",
                    "val_type": "string",
                    "name": "QQ机器人令牌",
                    "description": "机器人平台名称描述",
                    "value": "123456"
                },
                {
                    "type": "divider"
                },
                {
                    "type": "item",
                    "val_type": "bool",
                    "name": "启用 GO-CQHTTP 平台",
                    "description": "机器人平台名称描述",
                    "value": false
                }
            ]
        },
        {
            "type": "group",
            "name": "代理配置",
            "description": "代理配置描述",
            "body": [
                {
                    "type": "item",
                    "val_type": "string",
                    "name": "代理地址",
                    "description": "代理配置描述",
                    "value": "http://localhost:7890"
                }
            ]
        },
        {
            "type": "group",
            "name": "其他配置",
            "description": "其他配置描述",
            "body": [
                {
                    "type": "item",
                    "val_type": "string",
                    "name": "回复前缀",
                    "description": "[xxxx] 你好！ 其中xxxx是你可以填写的前缀。如果为空则不显示。",
                    "value": "GPT"
                }
            ]
        }
                
    ]
}
        '''
        for k in config:
            if 'qqbot' in k and 'enable' in k['qqbot'] and 'gocqbot' in k and 'enable' in k['gocqbot']':
                self.dashboard_data.configs['data'].append({
                    "type": "group",
                    "name": "机器人平台配置",
                    "description": "机器人平台配置描述",
                    "body": [
                        {
                            "type": "item",
                            "val_type": "bool",
                            "name": "启用 QQ 频道平台",
                            "description": "机器人平台名称描述",
                            "value": k['qqbot']['enable'],
                            "uuid": uuid.uuid4().hex
                        },
                        {
                            "type": "item",
                            "val_type": "string",
                            "name": "QQ机器人APPID",
                            "description": "机器人平台名称描述",
                            "value": k['qqbot']['appid'],
                            "uuid": uuid.uuid4().hex
                        },
                        {
                            "type": "item",
                            "val_type": "string",
                            "name": "QQ机器人令牌",
                            "description": "机器人平台名称描述",
                            "value": k['qqbot']['token'],
                            "uuid": uuid.uuid4().hex
                        },
                        {
                            "type": "divider"
                        },
                        {
                            "type": "item",
                            "val_type": "bool",
                            "name": "启用 GO-CQHTTP 平台",
                            "description": "机器人平台名称描述",
                            "value": k['gocqbot']['enable'],
                            "uuid": uuid.uuid4().hex
                        }
                    ]
                })
            
            if 'http_proxy' in k:
                self.dashboard_data.configs['data'].append({
                    "type": "group",
                    "name": "代理配置",
                    "description": "代理配置描述",
                    "body": [
                        {
                            "type": "item",
                            "val_type": "string",
                            "name": "代理地址",
                            "description": "代理配置描述",
                            "value": k['proxy'],
                            "uuid": uuid.uuid4().hex
                        }
                    ]
                })
            
    
    def run(self):
        self.dashboard.run()