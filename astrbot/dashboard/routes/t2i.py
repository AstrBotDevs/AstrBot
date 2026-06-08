# astrbot/dashboard/routes/t2i.py

from dataclasses import asdict

from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.dashboard.fastapi_compat import jsonify, request
from astrbot.dashboard.services.t2i_service import T2iService, T2iServiceError

from .route import Response, Route, RouteContext


class T2iRoute(Route):
    def __init__(
        self, context: RouteContext, core_lifecycle: AstrBotCoreLifecycle
    ) -> None:
        super().__init__(context)
        self.service = T2iService(core_lifecycle)
        # 使用列表保证路由注册顺序，避免 /<name> 路由优先匹配 /reset_default
        self.routes = [
            ("/t2i/templates", ("GET", self.list_templates)),
            ("/t2i/templates/active", ("GET", self.get_active_template)),
            ("/t2i/templates/create", ("POST", self.create_template)),
            ("/t2i/templates/reset_default", ("POST", self.reset_default_template)),
            ("/t2i/templates/set_active", ("POST", self.set_active_template)),
            # 动态路由应该在静态路由之后注册
            (
                "/t2i/templates/<path:name>",
                [
                    ("GET", self.get_template),
                    ("PUT", self.update_template),
                    ("DELETE", self.delete_template),
                ],
            ),
        ]
        self.register_routes()

    @staticmethod
    def _ok(data=None, message: str | None = None, status_code: int = 200):
        response = jsonify(asdict(Response().ok(data=data, message=message)))
        response.status_code = status_code
        return response

    @staticmethod
    def _service_error(exc: T2iServiceError):
        response = jsonify(asdict(Response().error(str(exc))))
        response.status_code = exc.status_code
        return response

    @staticmethod
    async def _request_data() -> dict:
        data = await request.get_json()
        return data if isinstance(data, dict) else {}

    async def _run(
        self,
        operation,
        *,
        message: str | None = None,
        status_code: int = 200,
        result_as_message: bool = False,
    ):
        try:
            result = operation() if callable(operation) else operation
            while hasattr(result, "__await__"):
                result = await result
            if isinstance(result, tuple):
                payload, result_message = result
                return self._ok(data=payload, message=result_message)
            if result_as_message:
                return self._ok(message=str(result), status_code=status_code)
            return self._ok(data=result, message=message, status_code=status_code)
        except T2iServiceError as exc:
            return self._service_error(exc)

    async def _run_json(self, operation, **kwargs):
        async def invoke():
            data = await self._request_data()
            return operation(data)

        return await self._run(invoke, **kwargs)

    async def list_templates(self):
        """获取所有T2I模板列表"""
        return await self._run(self.service.list_templates)

    async def get_active_template(self):
        """获取当前激活的T2I模板"""
        return await self._run(self.service.get_active_template)

    async def get_template(self, name: str):
        """获取指定名称的T2I模板内容"""
        return await self._run(lambda: self.service.get_template(name))

    async def create_template(self):
        """创建一个新的T2I模板"""
        return await self._run_json(
            self.service.create_template_from_legacy_payload,
            message="Template created successfully.",
            status_code=201,
        )

    async def update_template(self, name: str):
        """更新一个已存在的T2I模板"""
        return await self._run_json(
            lambda data: self.service.update_template_from_legacy_payload(name, data)
        )

    async def delete_template(self, name: str):
        """删除一个T2I模板"""
        return await self._run(
            lambda: self.service.delete_template(name),
            message="Template deleted successfully.",
        )

    async def set_active_template(self):
        """设置当前活动的T2I模板"""
        return await self._run_json(
            self.service.set_active_template_from_legacy_payload,
            result_as_message=True,
        )

    async def reset_default_template(self):
        """重置默认的'base'模板"""
        return await self._run(
            self.service.reset_default_template(),
            result_as_message=True,
        )
