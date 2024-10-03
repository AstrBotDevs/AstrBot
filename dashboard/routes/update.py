import threading, traceback
from .. import Route, Response, logger
from quart import Quart, request
from type.types import Context
from util.updator.astrbot_updator import AstrBotUpdator

class UpdateRoute(Route):
    def __init__(self, context: Context, app: Quart, astrbot_updator: AstrBotUpdator) -> None:
        super().__init__(context, app)
        self.routes = {
            '/update/check': ('GET', self.check_update),
            '/update/do': ('POST', self.update_project),
        }
        self.astrbot_updator = astrbot_updator
        self.register_routes()
    
    async def check_update(self):
        try:
            ret = await self.astrbot_updator.check_update(None, None)
            return Response(
                status="success",
                message=str(ret) if ret is not None else "已经是最新版本了。",
                data={
                    "has_new_version": ret is not None
                }
            ).__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(e.__str__()).__dict__
    
    async def update_project(self):
        data = await request.json
        version = data.get('version', '')
        if version == "" or version == "latest":
            latest = True
            version = ''
        else:
            latest = False
        try:
            await self.astrbot_updator.update(latest=latest, version=version)
            threading.Thread(target=self.astrbot_updator._reboot, args=(2, self.context)).start()
            return Response().ok(None, "更新成功，程序将在 2 秒内重启。").__dict__
        except Exception as e:
            logger.error(f"/api/update_project: {traceback.format_exc()}")
            return Response().error(e.__str__()).__dict__