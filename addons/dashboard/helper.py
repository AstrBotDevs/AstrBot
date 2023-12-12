from addons.dashboard.server import AstrBotDashBoard, DashBoardData
from pydantic import BaseModel
from typing import Union, Optional, 

class DashBoardConfig(BaseModel):
    type: str["group", "item"]
    name: str
    description: str
    body: Union[dict, list]
    value: Optional[Union[list, dict, str, int, bool]]
    val_type: Optional[str["list", "dict", "str", "int", "bool"]]
    body: Optional['DashBoardConfig']
    

class DashBoardHelper():
    def __init__(self, dashboard_data: DashBoardData):
        self.dashboard_data = dashboard_data
        self.dashboard = AstrBotDashBoard(self.dashboard_data)
        
        @self.dashboard.register("post_configs")
        def on_post_configs(configs: dict):
            self.dashboard_data.configs = configs
            
            return True
        
    # 将 config.yaml、 中的配置解析到 dashboard_data.configs 中
    def parse_config(self, config: dict):
        pass
    
    def run(self):
        self.dashboard.run()