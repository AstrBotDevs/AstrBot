from addons.dashboard.server import AstrBotDashBoard, DashBoardData
from pydantic import BaseModel
from typing import Union, Optional
import uuid
from util import general_utils as gu
from util.cmd_config import CmdConfig
from dataclasses import dataclass
import sys
import os
import threading
import time


def shutdown_bot(delay_s: int):
    time.sleep(delay_s)
    py = sys.executable
    os.execl(py, py, *sys.argv)

@dataclass
class DashBoardConfig():
    config_type: str
    name: Optional[str] = None
    description: Optional[str] = None
    path: Optional[str] = None # 仅 item 才需要
    body: Optional[list['DashBoardConfig']] = None # 仅 group 才需要
    value: Optional[Union[list, dict, str, int, bool]] = None # 仅 item 才需要
    val_type: Optional[str] = None # 仅 item 才需要

class DashBoardHelper():
    def __init__(self, dashboard_data: DashBoardData, config: dict):
        dashboard_data.configs = {
            "data": []
        }
        self.parse_default_config(dashboard_data, config)
        self.dashboard_data: DashBoardData = dashboard_data
        self.dashboard = AstrBotDashBoard(self.dashboard_data)
        self.key_map = {} # key: uuid, value: config key name
        self.cc = CmdConfig()
        
        @self.dashboard.register("post_configs")
        def on_post_configs(post_configs: dict):
            try:
                gu.log(f"收到配置更新请求", gu.LEVEL_INFO, tag="可视化面板")
                self.save_config(post_configs)
                self.parse_default_config(self.dashboard_data, self.cc.get_all())
                # 重启
                threading.Thread(target=shutdown_bot, args=(2,), daemon=True).start()
            except Exception as e:
                gu.log(f"在保存配置时发生错误：{e}", gu.LEVEL_ERROR, tag="可视化面板")
                raise e

        
    # 将 config.yaml、 中的配置解析到 dashboard_data.configs 中
    def parse_default_config(self, dashboard_data: DashBoardData, config: dict):
        
        try:
            bot_platform_group = DashBoardConfig(
                config_type="group",
                name="机器人平台配置",
                description="机器人平台配置描述",
                body=[
                    DashBoardConfig(
                        config_type="item",
                        val_type="bool",
                        name="启用 QQ 频道平台",
                        description="机器人平台名称描述",
                        value=config['qqbot']['enable'],
                        path="qqbot.enable",
                    ),
                    DashBoardConfig(
                        config_type="item",
                        val_type="string",
                        name="QQ机器人APPID",
                        description="机器人平台名称描述",
                        value=config['qqbot']['appid'],
                        path="qqbot.appid",
                    ),
                    DashBoardConfig(
                        config_type="item",
                        val_type="string",
                        name="QQ机器人令牌",
                        description="机器人平台名称描述",
                        value=config['qqbot']['token'],
                        path="qqbot.token",
                    ),
                    DashBoardConfig(
                        config_type="divider"
                    ),
                    DashBoardConfig(
                        config_type="item",
                        val_type="bool",
                        name="启用 GO-CQHTTP 平台",
                        description="机器人平台名称描述",
                        value=config['gocqbot']['enable'],
                        path="gocqbot.enable",
                    )
                ]
            )
            
            proxy_group = DashBoardConfig(
                config_type="group",
                name="代理配置",
                description="代理配置描述",
                body=[
                    DashBoardConfig(
                        config_type="item",
                        val_type="string",
                        name="HTTP 代理地址",
                        description="代理配置描述",
                        value=config['http_proxy'],
                        path="proxy",
                    ),
                    DashBoardConfig(
                        config_type="item",
                        val_type="string",
                        name="HTTPS 代理地址",
                        description="代理配置描述",
                        value=config['https_proxy'],
                        path="proxy",
                    )
                ]
            )
            
            other_group = DashBoardConfig(
                config_type="group",
                name="其他配置",
                description="其他配置描述",
                body=[
                    DashBoardConfig(
                        config_type="item",
                        val_type="string",
                        name="回复前缀",
                        description="[xxxx] 你好！ 其中xxxx是你可以填写的前缀。如果为空则不显示。",
                        value=config['reply_prefix'],
                        path="reply_prefix",
                    )
                ]
            )
            
            dashboard_data.configs['data'] = [
                bot_platform_group,
                proxy_group,
                other_group
            ]
        
        except Exception as e:
            gu.log(f"配置文件解析错误：{e}", gu.LEVEL_ERROR)
            raise e
        
    
    def save_config(self, post_config: dict):
        '''
        根据 path 解析并保存配置
        '''
        # for config in dashboard_data.configs['data']:
        #     if config['config_type'] == "group":
        #         for item in config['body']:
        #             queue.append(item)
        
        queue = []
        for config in post_config['data']:
            queue.append(config)
            
        while len(queue) > 0:
            config = queue.pop(0)
            if config['config_type'] == "group":
                for item in config['body']:
                    queue.append(item)
            elif config['config_type'] == "item":
                if config['path'] is None or config['path'] == "":
                    continue
                
                path = config['path'].split('.')
                if len(path) == 0:
                    continue
                
                if config['val_type'] == "bool":
                    self.cc.put_by_dot_str(config['path'], config['value'])
                elif config['val_type'] == "string":
                    self.cc.put_by_dot_str(config['path'], config['value'])
                elif config['val_type'] == "int":
                    try:
                        self.cc.put_by_dot_str(config['path'], int(config['value']))
                    except:
                        raise ValueError(f"配置项 {config['name']} 的值必须是整数")
                elif config['val_type'] == "float":
                    try:
                        self.cc.put_by_dot_str(config['path'], float(config['value']))
                    except:
                        raise ValueError(f"配置项 {config['name']} 的值必须是浮点数")
                else:
                    raise NotImplementedError(f"未知或者未实现的的配置项类型：{config['val_type']}")
        
    def run(self):
        self.dashboard.run()