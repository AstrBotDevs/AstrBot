import logging
from dataclasses import dataclass
from quart import Quart
from type.types import Context

logger = logging.getLogger("astrbot")
class Route():
    def __init__(self, context: Context, app: Quart):
        self.context = context
        self.app = app
    
    def register_routes(self):
        for route, (method, func) in self.routes.items():
            self.app.add_url_rule(f"/api{route}", view_func=func, methods=[method])

@dataclass
class Response():
    status: str = None
    message: str = None
    data: dict = None

    def error(self, message: str):
        self.status = "error"
        self.message = message
        return self

    def ok(self, data: dict={}, message: str=None):
        self.status = "ok"
        self.data = data
        self.message = message
        return self