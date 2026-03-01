from astrbot.core.lang import t
from astrbot.dashboard.routes.route import Response, Route, RouteContext
from quart import request
from astrbot.api import logger


class LangRoute(Route):
    def __init__(self, context: RouteContext) -> None:
        super().__init__(context)
        self.routes = {
            "/setLang": ("POST", self.set_Lang),
        }
        self.register_routes()

    # TODO 删除日志
    async def set_Lang(self):
        data = await request.get_json()
        lang = data.get("lang")
        logger.debug(f"[LangRoute] lang:{lang}")
        if lang is None:
            return Response().error("lang 为必填参数。").__dict__
        try:
            t.load_locale(locale=lang.lower(), files=None)
        except ValueError as exc:
            return Response().error(str(exc)).__dict__
        payload = {"lang": lang.lower(), "message": f"语言已设置为 {lang}"}
        return Response().ok(payload).__dict__
