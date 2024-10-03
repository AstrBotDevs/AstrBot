from .. import Route
from quart import Quart
from type.types import Context

class StaticFileRoute(Route):
    def __init__(self, context: Context, app: Quart) -> None:
        super().__init__(context, app)
        
        index_ = ['/', '/auth/login', '/config', '/logs', '/extension', '/dashboard/default']
        for i in index_:
            self.app.add_url_rule(i, view_func=self.index)
    
    async def index(self):
        return await self.app.send_static_file('index.html')