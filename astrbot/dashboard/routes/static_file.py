from .route import Route
from quart import Quart
from core.config.astrbot_config import AstrBotConfig

class StaticFileRoute(Route):
    def __init__(self, config: AstrBotConfig, app: Quart) -> None:
        super().__init__(config, app)
        
        index_ = ['/', '/auth/login', '/config', '/logs', '/extension', '/dashboard/default']
        for i in index_:
            self.app.add_url_rule(i, view_func=self.index)
    
    async def index(self):
        return await self.app.send_static_file('index.html')