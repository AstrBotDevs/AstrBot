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
                        description="就是你想到的那个 QQ 频道平台。详见 q.qq.com",
                        value=config['qqbot']['enable'],
                        path="qqbot.enable",
                    ),
                    DashBoardConfig(
                        config_type="item",
                        val_type="string",
                        name="QQ机器人APPID",
                        description="详见 q.qq.com",
                        value=config['qqbot']['appid'],
                        path="qqbot.appid",
                    ),
                    DashBoardConfig(
                        config_type="item",
                        val_type="string",
                        name="QQ机器人令牌",
                        description="详见 q.qq.com",
                        value=config['qqbot']['token'],
                        path="qqbot.token",
                    ),
                    DashBoardConfig(
                        config_type="item",
                        val_type="string",
                        name="QQ机器人 Secret",
                        description="详见 q.qq.com",
                        value=config['qqbot_secret'],
                        path="qqbot_secret",
                    ),
                    DashBoardConfig(
                        config_type="divider"
                    ),
                    DashBoardConfig(
                        config_type="item",
                        val_type="bool",
                        name="启用 GO-CQHTTP 平台",
                        description="gocq 是一个基于 HTTP 协议的 CQHTTP 协议的实现。详见 github.com/Mrs4s/go-cqhttp",
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
                        description="建议上下一致",
                        value=config['http_proxy'],
                        path="proxy",
                    ),
                    DashBoardConfig(
                        config_type="item",
                        val_type="string",
                        name="HTTPS 代理地址",
                        description="建议上下一致",
                        value=config['https_proxy'],
                        path="proxy",
                    )
                ]
            )
            general_platform_detail_group = DashBoardConfig(
                config_type="group",
                name="通用平台配置",
                description="",
                body=[
                    DashBoardConfig(
                        config_type="item",
                        val_type="bool",
                        name="启动消息文字转图片",
                        description="启动后，机器人会将消息转换为图片发送，以降低风控风险。",
                        value=config['qq_pic_mode'],
                        path="qq_pic_mode",
                    ),
                    DashBoardConfig(
                        config_type="item",
                        val_type="int",
                        name="消息限制时间",
                        description="在此时间内，机器人不会回复同一个用户的消息。单位：秒",
                        value=config['limit']['time'],
                        path="limit.time",
                    ),
                    DashBoardConfig(
                        config_type="item",
                        val_type="int",
                        name="消息限制次数",
                        description="在上面的时间内，如果用户发送消息超过此次数，则机器人不会回复。单位：次",
                        value=config['limit']['count'],
                        path="limit.count",
                    ),
                    DashBoardConfig(
                        config_type="item",
                        val_type="string",
                        name="回复前缀",
                        description="[xxxx] 你好！ 其中xxxx是你可以填写的前缀。如果为空则不显示。",
                        value=config['reply_prefix'],
                        path="reply_prefix",
                    ),
                    DashBoardConfig(
                        config_type="item",
                        val_type="string",
                        name="管理员用户 ID",
                        description="对机器人 !myid 即可获得。如果此功能不可用，请加群 322154837",
                        value=config['gocq_qqchan_admin'],
                        path="gocq_qqchan_admin",
                    ),
                    DashBoardConfig(
                        config_type="item",
                        val_type="list",
                        name="通用管理员用户 ID（同上，此项支持多个管理员）",
                        description="",
                        value=config['other_admins'],
                        path="other_admins",
                    ),
                    DashBoardConfig(
                        config_type="item",
                        val_type="bool",
                        name="独立会话",
                        description="是否启用独立会话模式，即 1 个用户自然账号 1 个会话。",
                        value=config['uniqueSessionMode'],
                        path="uniqueSessionMode",
                    ),
                    DashBoardConfig(
                        config_type="item",
                        val_type="bool",
                        name="是否允许 QQ 频道私聊",
                        description="仅针对 QQ 频道 SDK，而非 GO-CQHTTP。如果启用，那么机器人会响应私聊消息。",
                        value=config['direct_message_mode'],
                        path="direct_message_mode",
                    ),
                    DashBoardConfig(
                        config_type="item",
                        val_type="string",
                        name="LLM 唤醒词",
                        description="如果不为空, 那么只有当消息以此词开头时，才会调用大语言模型进行回复。如设置为 /chat，那么只有当消息以 /chat 开头时，才会调用大语言模型进行回复。",
                        value=config['llm_wake_prefix'],
                        path="llm_wake_prefix",
                    )
                ]
            )
            
            gocq_platform_detail_group = DashBoardConfig(
                config_type="group",
                name="GO-CQHTTP 平台配置",
                description="",
                body=[
                    DashBoardConfig(
                        config_type="item",
                        val_type="string",
                        name="HTTP 服务器地址",
                        description="",
                        value=config['gocq_host'],
                        path="gocq_host",
                    ),
                    DashBoardConfig(
                        config_type="item",
                        val_type="int",
                        name="HTTP 服务器端口",
                        description="",
                        value=config['gocq_http_port'],
                        path="gocq_http_port",
                    ),
                    DashBoardConfig(
                        config_type="item",
                        val_type="int",
                        name="WebSocket 服务器端口",
                        description="",
                        value=config['gocq_websocket_port'],
                        path="gocq_websocket_port",
                    ),
                    DashBoardConfig(
                        config_type="item",
                        val_type="bool",
                        name="是否响应群消息",
                        description="",
                        value=config['gocq_react_group'],
                        path="gocq_react_group",
                    ),
                    DashBoardConfig(
                        config_type="item",
                        val_type="bool",
                        name="是否响应私聊消息",
                        description="",
                        value=config['gocq_react_friend'],
                        path="gocq_react_friend",
                    ),
                    DashBoardConfig(
                        config_type="item",
                        val_type="bool",
                        name="是否响应群成员增加消息",
                        description="",
                        value=config['gocq_react_group_increase'],
                        path="gocq_react_group_increase",
                    ),
                    DashBoardConfig(
                        config_type="item",
                        val_type="bool",
                        name="是否响应频道消息",
                        description="",
                        value=config['gocq_react_guild'],
                        path="gocq_react_guild",
                    ),
                    DashBoardConfig(
                        config_type="item",
                        val_type="int",
                        name="转发阈值（字符数）",
                        description="机器人回复的消息长度超出这个值后，会被折叠成转发卡片发出以减少刷屏。",
                        value=config['qq_forward_threshold'],
                        path="qq_forward_threshold",
                    ),
                ]
            )

            llm_group = DashBoardConfig(
                config_type="group",
                name="LLM 配置",
                description="",
                body=[
                    DashBoardConfig(
                        config_type="item",
                        val_type="list",
                        name="OpenAI API KEY",
                        description="OpenAI API 的 KEY。支持使用非官方但是兼容的 API。",
                        value=config['openai']['key'],
                        path="openai.key",
                    ),
                    DashBoardConfig(
                        config_type="item",
                        val_type="string",
                        name="OpenAI API 节点地址",
                        description="OpenAI API 的节点地址，配合非官方 API 使用。如果不想填写，那么请填写 none",
                        value=config['openai']['api_base'],
                        path="openai.api_base",
                    ),
                    DashBoardConfig(
                        config_type="item",
                        val_type="string",
                        name="OpenAI 模型",
                        description="OpenAI 模型。详见 https://platform.openai.com/docs/api-reference/chat",
                        value=config['openai']['chatGPTConfigs']['model'],
                        path="openai.chatGPTConfigs.model",
                    ),
                    DashBoardConfig(
                        config_type="item",
                        val_type="int",
                        name="OpenAI 最大生成长度",
                        description="OpenAI 最大生成长度。详见 https://platform.openai.com/docs/api-reference/chat",
                        value=config['openai']['chatGPTConfigs']['max_tokens'],
                        path="openai.chatGPTConfigs.max_tokens",
                    ),
                    DashBoardConfig(
                        config_type="item",
                        val_type="float",
                        name="OpenAI 温度",
                        description="OpenAI 温度。详见 https://platform.openai.com/docs/api-reference/chat",
                        value=config['openai']['chatGPTConfigs']['temperature'],
                        path="openai.chatGPTConfigs.temperature",
                    ),
                    DashBoardConfig(
                        config_type="item",
                        val_type="float",
                        name="OpenAI top_p",
                        description="OpenAI top_p。详见 https://platform.openai.com/docs/api-reference/chat",
                        value=config['openai']['chatGPTConfigs']['top_p'],
                        path="openai.chatGPTConfigs.top_p",
                    ),
                    DashBoardConfig(
                        config_type="item",
                        val_type="float",
                        name="OpenAI frequency_penalty",
                        description="OpenAI frequency_penalty。详见 https://platform.openai.com/docs/api-reference/chat",
                        value=config['openai']['chatGPTConfigs']['frequency_penalty'],
                        path="openai.chatGPTConfigs.frequency_penalty",
                    ),
                    DashBoardConfig(
                        config_type="item",
                        val_type="float",
                        name="OpenAI presence_penalty",
                        description="OpenAI presence_penalty。详见 https://platform.openai.com/docs/api-reference/chat",
                        value=config['openai']['chatGPTConfigs']['presence_penalty'],
                        path="openai.chatGPTConfigs.presence_penalty",
                    ),
                    DashBoardConfig(
                        config_type="item",
                        val_type="int",
                        name="OpenAI 总生成长度限制",
                        description="OpenAI 总生成长度限制。详见 https://platform.openai.com/docs/api-reference/chat",
                        value=config['openai']['total_tokens_limit'],
                        path="openai.total_tokens_limit",
                    ),
                    DashBoardConfig(
                        config_type="item",
                        val_type="string",
                        name="OpenAI 图像生成模型",
                        description="OpenAI 图像生成模型。",
                        value=config['openai_image_generate']['model'],
                        path="openai_image_generate.model",
                    ),
                    DashBoardConfig(
                        config_type="item",
                        val_type="string",
                        name="OpenAI 图像生成大小",
                        description="OpenAI 图像生成大小。",
                        value=config['openai_image_generate']['size'],
                        path="openai_image_generate.size",
                    ),
                    DashBoardConfig(
                        config_type="item",
                        val_type="string",
                        name="OpenAI 图像生成风格",
                        description="OpenAI 图像生成风格。修改前请参考 OpenAI 官方文档",
                        value=config['openai_image_generate']['style'],
                        path="openai_image_generate.style",
                    ),
                    DashBoardConfig(
                        config_type="item",
                        val_type="string",
                        name="OpenAI 图像生成质量",
                        description="OpenAI 图像生成质量。修改前请参考 OpenAI 官方文档",
                        value=config['openai_image_generate']['quality'],
                        path="openai_image_generate.quality",
                    ),
                    DashBoardConfig(
                        config_type="item",
                        val_type="string",
                        name="大语言模型问题题首提示词",
                        description="如果填写了此项，在每个对大语言模型的请求中，都会在问题前加上此提示词。",
                        value=config['llm_env_prompt'],
                        path="llm_env_prompt",
                    ),
                ]
            )
            
            baidu_aip_group = DashBoardConfig(
                config_type="group",
                name="百度内容审核",
                description="需要去申请",
                body=[
                    DashBoardConfig(
                        config_type="item",
                        val_type="bool",
                        name="启动百度内容审核服务",
                        description="",
                        value=config['baidu_aip']['enable'],
                        path="baidu_aip.enable"
                    ),
                    # "app_id": null,
                    # "api_key": null,
                    # "secret_key": null
                    DashBoardConfig(
                        config_type="item",
                        val_type="string",
                        name="APP ID",
                        description="",
                        value=config['baidu_aip']['app_id'],
                        path="baidu_aip.app_id"
                    ),
                    DashBoardConfig(
                        config_type="item",
                        val_type="string",
                        name="API KEY",
                        description="",
                        value=config['baidu_aip']['api_key'],
                        path="baidu_aip.api_key"
                    ),
                    DashBoardConfig(
                        config_type="item",
                        val_type="string",
                        name="SECRET KEY",
                        description="",
                        value=config['baidu_aip']['secret_key'],
                        path="baidu_aip.secret_key"
                    )
                ]
            )



            other_group = DashBoardConfig(
                config_type="group",
                name="其他配置",
                description="其他配置描述",
                body=[
                    # 人格
                    DashBoardConfig(
                        config_type="item",
                        val_type="string",
                        name="默认人格文本",
                        description="默认人格文本",
                        value=config['default_personality_str'],
                        path="default_personality_str",
                    ),
                    DashBoardConfig(
                        config_type="item",
                        val_type="string",
                        name="面板用户名",
                        description="是的，就是你理解的这个面板的用户名",
                        value=config['dashboard_username'],
                        path="dashboard_username",
                    ),
                ]
            )
            
            dashboard_data.configs['data'] = [
                bot_platform_group,
                general_platform_detail_group,
                gocq_platform_detail_group,
                proxy_group,
                llm_group,
                other_group,
                baidu_aip_group
            ]
        
        except Exception as e:
            gu.log(f"配置文件解析错误：{e}", gu.LEVEL_ERROR)
            raise e
        
    
    def save_config(self, post_config: dict):
        '''
        根据 path 解析并保存配置
        '''
        
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
                elif config['val_type'] == "list":
                    if config['value'] is None:
                        self.cc.put_by_dot_str(config['path'], [])
                    elif not isinstance(config['value'], list):
                        raise ValueError(f"配置项 {config['name']} 的值必须是列表")
                    self.cc.put_by_dot_str(config['path'], config['value'])
                else:
                    raise NotImplementedError(f"未知或者未实现的的配置项类型：{config['val_type']}")
        
    def run(self):
        self.dashboard.run()