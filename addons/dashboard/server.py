from flask import Flask, request
from flask.logging import default_handler
from werkzeug.serving import make_server
from util import general_utils as gu
from dataclasses import dataclass
import logging
from cores.database.conn import dbConn
from util.cmd_config import CmdConfig
from util.updator import check_update, update_project, request_release_info
import util.plugin_util as putil
import websockets
import json
import threading
import asyncio
import os, sys
import time

@dataclass
class DashBoardData():
    stats: dict
    configs: dict
    logs: dict
    plugins: list[dict]

@dataclass
class Response():
    status: str
    message: str
    data: dict
    
class AstrBotDashBoard():
    def __init__(self, global_object: 'gu.GlobalObject'):
        self.global_object = global_object
        self.loop = asyncio.get_event_loop()
        asyncio.set_event_loop(self.loop)
        self.dashboard_data = global_object.dashboard_data
        self.dashboard_be = Flask(__name__, static_folder="dist", static_url_path="/")
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)
        self.funcs = {}
        self.cc = CmdConfig()
        self.logger = global_object.logger
        self.ws_clients = {} # remote_ip: ws
        # 启动 websocket 服务器
        self.ws_server = websockets.serve(self.__handle_msg, "0.0.0.0", 6186)
        
        @self.dashboard_be.get("/")
        def index():
            # 返回页面
            return self.dashboard_be.send_static_file("index.html")
        
        @self.dashboard_be.post("/api/authenticate")
        def authenticate():
            username = self.cc.get("dashboard_username", "")
            password = self.cc.get("dashboard_password", "")
            # 获得请求体
            post_data = request.json
            if post_data["username"] == username and post_data["password"] == password:
                return Response(
                    status="success",
                    message="登录成功。",
                    data={
                        "token": "astrbot-test-token",
                        "username": username
                    }
                ).__dict__
            else:
                return Response(
                    status="error",
                    message="用户名或密码错误。",
                    data=None
                ).__dict__
                
        @self.dashboard_be.post("/api/change_password")
        def change_password():
            password = self.cc.get("dashboard_password", "")
            # 获得请求体
            post_data = request.json
            if post_data["password"] == password:
                self.cc.put("dashboard_password", post_data["new_password"])
                return Response(
                    status="success",
                    message="修改成功。",
                    data=None
                ).__dict__
            else:
                return Response(
                    status="error",
                    message="原密码错误。",
                    data=None
                ).__dict__

        @self.dashboard_be.get("/api/stats")
        def get_stats():
            db_inst = dbConn()
            all_session = db_inst.get_all_stat_session()
            last_24_message = db_inst.get_last_24h_stat_message()
            # last_24_platform = db_inst.get_last_24h_stat_platform()
            platforms = db_inst.get_platform_cnt_total()
            self.dashboard_data.stats["session"] = []
            self.dashboard_data.stats["session_total"] = db_inst.get_session_cnt_total()
            self.dashboard_data.stats["message"] = last_24_message
            self.dashboard_data.stats["message_total"] = db_inst.get_message_cnt_total()
            self.dashboard_data.stats["platform"] = platforms

            return Response(
                status="success",
                message="",
                data=self.dashboard_data.stats
            ).__dict__
        
        @self.dashboard_be.get("/api/configs")
        def get_configs():
            # 如果params中有namespace，则返回该namespace下的配置
            # 否则返回所有配置
            namespace = "" if "namespace" not in request.args else request.args["namespace"]
            conf = self._get_configs(namespace)
            return Response(
                status="success",
                message="",
                data=conf
            ).__dict__
            
        @self.dashboard_be.get("/api/config_outline")
        def get_config_outline():
            outline = self._generate_outline()
            return Response(
                status="success",
                message="",
                data=outline
            ).__dict__
            
        @self.dashboard_be.post("/api/configs")
        def post_configs():
            post_configs = request.json
            try:
                self.funcs["post_configs"](post_configs)
                return Response(
                    status="success",
                    message="保存成功~ 机器人将在 2 秒内重启以应用新的配置。",
                    data=None
                ).__dict__
            except Exception as e:
                return Response(
                    status="error",
                    message=e.__str__(),
                    data=self.dashboard_data.configs
                ).__dict__
            
        @self.dashboard_be.get("/api/extensions")
        def get_plugins():
            _plugin_resp = []
            for plugin in self.dashboard_data.plugins:
                _p = self.dashboard_data.plugins[plugin]
                _t = {
                    "name": _p["info"]["name"],
                    "repo": '' if "repo" not in _p["info"] else _p["info"]["repo"],
                    "author": _p["info"]["author"],
                    "desc": _p["info"]["desc"],
                    "version": _p["info"]["version"]
                }
                _plugin_resp.append(_t)
            return Response(
                status="success",
                message="",
                data=_plugin_resp
            ).__dict__
            
        @self.dashboard_be.post("/api/extensions/install")
        def install_plugin():
            post_data = request.json
            repo_url = post_data["url"]
            try:
                self.logger.log(f"正在安装插件 {repo_url}", tag="可视化面板")
                putil.install_plugin(repo_url, self.dashboard_data.plugins)
                self.logger.log(f"安装插件 {repo_url} 成功", tag="可视化面板")
                return Response(
                    status="success",
                    message="安装成功~",
                    data=None
                ).__dict__
            except Exception as e:
                return Response(
                    status="error",
                    message=e.__str__(),
                    data=None
                ).__dict__
        
        @self.dashboard_be.post("/api/extensions/uninstall")
        def uninstall_plugin():
            post_data = request.json
            plugin_name = post_data["name"]
            try:
                self.logger.log(f"正在卸载插件 {plugin_name}", tag="可视化面板")
                putil.uninstall_plugin(plugin_name, self.dashboard_data.plugins)
                self.logger.log(f"卸载插件 {plugin_name} 成功", tag="可视化面板")
                return Response(
                    status="success",
                    message="卸载成功~",
                    data=None
                ).__dict__
            except Exception as e:
                return Response(
                    status="error",
                    message=e.__str__(),
                    data=None
                ).__dict__
                
        @self.dashboard_be.post("/api/extensions/update")
        def update_plugin():
            post_data = request.json
            plugin_name = post_data["name"]
            try:
                self.logger.log(f"正在更新插件 {plugin_name}", tag="可视化面板")
                putil.update_plugin(plugin_name, self.dashboard_data.plugins)
                self.logger.log(f"更新插件 {plugin_name} 成功", tag="可视化面板")
                return Response(
                    status="success",
                    message="更新成功~",
                    data=None
                ).__dict__
            except Exception as e:
                return Response(
                    status="error",
                    message=e.__str__(),
                    data=None
                ).__dict__
                
        @self.dashboard_be.post("/api/log")
        def log():
            for item in self.ws_clients:
                try:
                    asyncio.run_coroutine_threadsafe(self.ws_clients[item].send(request.data.decode()), self.loop)
                except Exception as e:
                    pass
            return 'ok'
        
        @self.dashboard_be.get("/api/check_update")
        def get_update_info():
            try:
                ret = check_update()
                return Response(
                    status="success",
                    message=ret,
                    data={
                        "has_new_version": ret != "当前已经是最新版本。" # 先这样吧，累了=.=
                    }
                ).__dict__
            except Exception as e:
                return Response(
                    status="error",
                    message=e.__str__(),
                    data=None
                ).__dict__
                
        @self.dashboard_be.post("/api/update_project")
        def update_project_api():
            version = request.json['version']
            if version == "" or version == "latest":
                latest = True
                version = ''
            else:
                latest = False
                version = request.json["version"]
            try:
                update_project(request_release_info(), latest=latest, version=version)
                threading.Thread(target=self.shutdown_bot, args=(3,)).start()
                return Response(
                    status="success",
                    message="更新成功，机器人将在 3 秒内重启。",
                    data=None
                ).__dict__
            except Exception as e:
                return Response(
                    status="error",
                    message=e.__str__(),
                    data=None
                ).__dict__
            
    def shutdown_bot(self, delay_s: int):
        time.sleep(delay_s)
        py = sys.executable
        os.execl(py, py, *sys.argv)
    
    def _get_configs(self, namespace: str):
        if namespace == "":
            ret = [self.dashboard_data.configs['data'][5], 
                    self.dashboard_data.configs['data'][6],]
        elif namespace == "internal_platform_qq_official":
            ret = [self.dashboard_data.configs['data'][0],]
        elif namespace == "internal_platform_qq_gocq":
            ret = [self.dashboard_data.configs['data'][1],]
        elif namespace == "internal_platform_general": # 全局平台配置
            ret = [self.dashboard_data.configs['data'][2],]
        elif namespace == "internal_llm_openai_official":
            ret = [self.dashboard_data.configs['data'][3],]
        elif namespace == "internal_llm_rev_chatgpt":
            ret = [self.dashboard_data.configs['data'][4],]
        else:
            path = f"data/config/{namespace}.json"
            if not os.path.exists(path):
                return []
            with open(path, "r", encoding="utf-8-sig") as f:
                ret = [{
                    "config_type": "group",
                    "name": namespace + " 插件配置",
                    "description": "",
                    "body": list(json.load(f).values())
                },]
        return ret

    def _generate_outline(self):
        '''
        生成配置大纲。目前分为 platform(消息平台配置) 和 llm(语言模型配置) 两大类。
        插件的info函数中如果带了plugin_type字段，则会被归类到对应的大纲中。目前仅支持 platform 和 llm 两种类型。
        '''
        outline = [
            {
            "type": "platform",
            "name": "配置通用消息平台",
            "body": [
                {
                "title": "通用",
                "desc": "通用平台配置",
                "namespace": "internal_platform_general",
                "tag": ""
                },
                {
                "title": "QQ_OFFICIAL",
                "desc": "QQ官方API，仅支持频道",
                "namespace": "internal_platform_qq_official",
                "tag": ""
                },
                {
                "title": "OneBot协议",
                "desc": "支持cq-http、shamrock等（目前仅支持QQ平台）",
                "namespace": "internal_platform_qq_gocq",
                "tag": ""
                }
            ]
            },
            {
                "type": "llm",
                "name": "配置 LLM",
                "body": [
                    {
                        "title": "OpenAI Official",
                        "desc": "也支持使用官方接口的中转服务",
                        "namespace": "internal_llm_openai_official",
                        "tag": ""
                    },
                    {
                        "title": "Rev ChatGPT",
                        "desc": "早期的逆向ChatGPT，不推荐",
                        "namespace": "internal_llm_rev_chatgpt",
                        "tag": ""
                    }
                ]
            }
        ]
        for plugin in self.global_object.cached_plugins:
            # 从插件信息中获取 plugin_type 字段，如果有则归类到对应的大纲中
            if "plugin_type" in self.global_object.cached_plugins[plugin]["info"]:
                _t = self.global_object.cached_plugins[plugin]["info"]["plugin_type"]
                for item in outline:
                    if item["type"] == _t:
                        item["body"].append({
                            "title": self.global_object.cached_plugins[plugin]["info"]["name"],
                            "desc": self.global_object.cached_plugins[plugin]["info"]["desc"],
                            "namespace": plugin,
                            "tag": plugin,
                        })
        return outline

    def register(self, name: str):
        def decorator(func):
            self.funcs[name] = func
            return func
        return decorator

    async def __handle_msg(self, websocket, path):
        address = websocket.remote_address
        # self.logger.log(f"和 {address} 建立了 websocket 连接", tag="可视化面板")
        self.ws_clients[address] = websocket
        data = ''.join(self.logger.history).replace('\n', '\r\n')
        await websocket.send(data)
        while True:
            try:
                msg = await websocket.recv()
            except websockets.exceptions.ConnectionClosedError:
                # self.logger.log(f"和 {address} 的 websocket 连接已断开", tag="可视化面板")
                del self.ws_clients[address]
                break
            except Exception as e:
                # self.logger.log(f"和 {path} 的 websocket 连接发生了错误: {e.__str__()}", tag="可视化面板")
                del self.ws_clients[address]
                break
        
    def run_ws_server(self, loop):
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.ws_server)
        loop.run_forever()

    def run(self):
        threading.Thread(target=self.run_ws_server, args=(self.loop,)).start()
        self.logger.log("已启动 websocket 服务器", tag="可视化面板")
        ip_address = gu.get_local_ip_addresses()
        ip_str = f"http://{ip_address}:6185\n\thttp://localhost:6185"
        self.logger.log(f"\n==================\n您可访问:\n\n\t{ip_str}\n\n来登录可视化面板，默认账号密码为空。\n注意: 所有配置项现已全量迁移至 cmd_config.json 文件下，可登录可视化面板在线修改配置。\n==================\n", tag="可视化面板")
        http_server = make_server('0.0.0.0', 6185, self.dashboard_be, threaded=True)
        http_server.serve_forever()

