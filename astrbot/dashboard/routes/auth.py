from astrbot.dashboard.fastapi_compat import (
    current_app,
    g,
    jsonify,
    make_response,
    request,
)
from astrbot.dashboard.services.auth_service import (
    DASHBOARD_JWT_COOKIE_MAX_AGE,
    DASHBOARD_JWT_COOKIE_NAME,
    TOTP_TRUSTED_DEVICE_COOKIE_NAME,
    TOTP_TRUSTED_DEVICE_MAX_AGE,
    AuthService,
    AuthServiceResult,
)

from .route import Response, Route, RouteContext

__all__ = ("AuthRoute",)


class AuthRoute(Route):
    def __init__(self, context: RouteContext, db) -> None:
        super().__init__(context)
        self.routes = {
            "/auth/login": ("POST", self.login),
            "/auth/logout": ("POST", self.logout),
            "/auth/setup-status": ("GET", self.setup_status),
            "/auth/setup": ("POST", self.setup),
            "/auth/setup-authenticated": ("POST", self.setup_authenticated),
            "/auth/totp/setup": ("POST", self.totp_setup),
            "/auth/totp/recovery": ("POST", self.totp_recovery),
            "/auth/account/edit": ("POST", self.edit_account),
        }
        self.service = AuthService(db, self.config)
        self.register_routes()

    async def _json_body(self):
        return await request.json

    async def _service_json_response(self, operation, *args, **kwargs):
        return await self._service_response(
            await operation(await self._json_body(), *args, **kwargs)
        )

    async def setup_status(self):
        return await self._service_response(await self.service.setup_status())

    async def totp_setup(self):
        return await self._service_json_response(self.service.totp_setup)

    async def totp_recovery(self):
        return await self._service_response(await self.service.totp_recovery())

    async def setup(self):
        return await self._service_json_response(self.service.setup)

    async def setup_authenticated(self):
        return await self._service_json_response(
            self.service.setup_authenticated,
            getattr(g, "username", None),
        )

    async def login(self):
        return await self._service_json_response(
            self.service.login,
            trusted_device_cookie_token=request.cookies.get(
                TOTP_TRUSTED_DEVICE_COOKIE_NAME,
                "",
            ).strip(),
        )

    async def logout(self):
        response = await make_response(
            jsonify(Response().ok(None, "已退出登录").__dict__)
        )
        self._clear_dashboard_jwt_cookie(response)
        return response

    async def edit_account(self):
        return await self._service_json_response(self.service.edit_account)

    def generate_jwt(self, username):
        return self.service.generate_jwt(username)

    async def _service_response(self, result: AuthServiceResult):
        payload = (
            Response().error(result.message or "")
            if result.status == "error"
            else Response().ok(result.data, result.message)
        )
        if result.status == "error" and result.data is not None:
            payload.data = result.data

        response = await make_response(jsonify(payload.__dict__))
        response.status_code = result.status_code

        if result.jwt_token:
            self._set_dashboard_jwt_cookie(response, result.jwt_token)

        if result.trusted_device_token:
            response.set_cookie(
                TOTP_TRUSTED_DEVICE_COOKIE_NAME,
                result.trusted_device_token,
                max_age=TOTP_TRUSTED_DEVICE_MAX_AGE,
                httponly=True,
                samesite="Strict",
                secure=AuthRoute._use_secure_dashboard_jwt_cookie(),
                path="/api/auth",
            )
        return response

    @staticmethod
    def _use_secure_dashboard_jwt_cookie() -> bool:
        return bool(
            current_app.config.get(
                "DASHBOARD_JWT_COOKIE_SECURE",
                not current_app.debug and not current_app.testing,
            )
        )

    @staticmethod
    def _set_dashboard_jwt_cookie(response, token: str) -> None:
        response.set_cookie(
            DASHBOARD_JWT_COOKIE_NAME,
            token,
            max_age=DASHBOARD_JWT_COOKIE_MAX_AGE,
            httponly=True,
            samesite="Strict",
            secure=AuthRoute._use_secure_dashboard_jwt_cookie(),
            path="/",
        )

    @staticmethod
    def _clear_dashboard_jwt_cookie(response) -> None:
        response.delete_cookie(
            DASHBOARD_JWT_COOKIE_NAME,
            httponly=True,
            samesite="Strict",
            secure=AuthRoute._use_secure_dashboard_jwt_cookie(),
            path="/",
        )
