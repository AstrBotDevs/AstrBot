from flask import Flask
import datetime
from pydantic import BaseModel
from util import general_utils as gu

class DashBoardData(BaseModel):
    stats: dict
    configs: dict
    logs: dict
    
class Response(BaseModel):
    status: str
    message: str
    data: dict
    
class AstrBotDashBoard():
    def __init__(self, dashboard_data: DashBoardData):
        self.dashboard_data = dashboard_data
        self.dashboard_be = Flask(__name__)
        self.funcs = {}

        @self.dashboard_be.get("/stats")
        def get_stats():
            return Response(
                status="success",
                message="",
                data=self.dashboard_data.stats
            ).dict()
        
        @self.dashboard_be.get("/configs")
        def get_configs():
            return Response(
                status="success",
                message="",
                data=self.dashboard_data.configs
            ).__dict__
            
        @self.dashboard_be.post("/configs")
        def post_configs():
            if self.funcs["post_configs"](self.dashboard_data.configs):
                return Response(
                    status="success",
                    message="",
                    data=self.dashboard_data.configs
                ).__dict__
            return Response(
                status="error",
                message="",
                data=self.dashboard_data.configs
            ).__dict__
        
        @self.dashboard_be.get("/logs")
        def get_logs():
            return Response(
                status="success",
                message="",
                data=self.dashboard_data.logs
            ).__dict__
        
    def register(self, name: str):
        def decorator(func):
            self.funcs[name] = func
            return func
        return decorator

    def run(self):
        gu.log(f"\n\n==================\n您可以访问:\n\thttp://localhost:6185/\n来登录可视化面板。\n==================\n\n", tag="可视化面板")
        self.dashboard_be.run(host="0.0.0.0", port=6185)
