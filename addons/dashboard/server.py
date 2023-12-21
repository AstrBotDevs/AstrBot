from flask import Flask, request
from flask.logging import default_handler
from werkzeug.serving import make_server
import datetime
from util import general_utils as gu
from dataclasses import dataclass
import logging
from cores.database.conn import dbConn
from util.cmd_config import CmdConfig

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
    def __init__(self, dashboard_data: DashBoardData):
        self.dashboard_data = dashboard_data
        self.dashboard_be = Flask(__name__, static_folder="dist", static_url_path="/")
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)
        self.funcs = {}
        self.cc = CmdConfig()
        
        
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
            last_24_platform = db_inst.get_last_24h_stat_platform()
            self.dashboard_data.stats["session"] = []
            self.dashboard_data.stats["session_total"] = db_inst.get_session_cnt_total()
            self.dashboard_data.stats["message"] = last_24_message
            self.dashboard_data.stats["message_total"] = db_inst.get_message_cnt_total()
            self.dashboard_data.stats["platform"] = last_24_platform

            return Response(
                status="success",
                message="",
                data=self.dashboard_data.stats
            ).__dict__
        
        @self.dashboard_be.get("/api/configs")
        def get_configs():
            return Response(
                status="success",
                message="",
                data=self.dashboard_data.configs
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
        
        @self.dashboard_be.get("/api/logs")
        def get_logs():
            return Response(
                status="success",
                message="",
                data=self.dashboard_data.logs
            ).__dict__
            
        @self.dashboard_be.get("/api/extensions")
        def get_plugins():
            """
            {
                "name": "GoodPlugins",
                "repo": "https://gitee.com/soulter/goodplugins",
                "author": "soulter",
                "desc": "一些好用的插件",
                "version": "1.0"
            }
            """
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
            pass
        
        @self.dashboard_be.post("/api/extensions/uninstall")
        def uninstall_plugin():
            pass
        
    def register(self, name: str):
        def decorator(func):
            self.funcs[name] = func
            return func
        return decorator

    def run(self):
        ip_address = gu.get_local_ip_addresses()
        ip_str = f"http://{ip_address}:6185\n\thttp://localhost:6185"
        gu.log(f"\n\n==================\n您可以访问:\n\n\t{ip_str}\n\n来登录可视化面板。\n注意: 所有配置项现已全量迁移至 cmd_config.json 文件下。您可以登录可视化面板在线修改配置。\n==================\n\n", tag="可视化面板")
        # self.dashboard_be.run(host="0.0.0.0", port=6185)
        http_server = make_server('0.0.0.0', 6185, self.dashboard_be)
        http_server.serve_forever()
