import datetime
import secrets

import jwt
from quart import request

from astrbot import logger
from astrbot.core import DEMO_MODE
from astrbot.core.utils.auth_password import (
    get_dashboard_login_challenge,
    hash_dashboard_password,
    is_default_dashboard_password,
    is_legacy_dashboard_password,
    validate_dashboard_password,
    verify_dashboard_login_proof,
    verify_dashboard_password,
)

from .route import Response, Route, RouteContext


class AuthRoute(Route):
    def __init__(self, context: RouteContext) -> None:
        super().__init__(context)
        self._login_challenges: dict[str, dict[str, object]] = {}
        self.routes = {
            "/auth/login/challenge": ("POST", self.login_challenge),
            "/auth/login": ("POST", self.login),
            "/auth/account/edit": ("POST", self.edit_account),
        }
        self.register_routes()

    async def login_challenge(self):
        password = self.config["dashboard"]["password"]
        self._prune_login_challenges()

        try:
            challenge = get_dashboard_login_challenge(password)
        except ValueError as exc:
            logger.error("Failed to create dashboard login challenge: %s", exc)
            return (
                Response()
                .error("Unsupported dashboard password configuration")
                .__dict__
            )

        challenge_id = secrets.token_hex(16)
        nonce = secrets.token_hex(32)
        self._login_challenges[challenge_id] = {
            "nonce": nonce,
            "expires_at": datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(minutes=1),
        }

        return (
            Response()
            .ok(
                {
                    "challenge_id": challenge_id,
                    "nonce": nonce,
                    **challenge,
                }
            )
            .__dict__
        )

    async def login(self):
        username = self.config["dashboard"]["username"]
        password = self.config["dashboard"]["password"]
        post_data = await request.json

        req_username = (
            post_data.get("username") if isinstance(post_data, dict) else None
        )
        req_password = (
            post_data.get("password") if isinstance(post_data, dict) else None
        )
        req_challenge_id = (
            post_data.get("challenge_id") if isinstance(post_data, dict) else None
        )
        req_password_proof = (
            post_data.get("password_proof") if isinstance(post_data, dict) else None
        )
        if not isinstance(req_username, str):
            return Response().error("Invalid request payload").__dict__

        login_verified = False
        if isinstance(req_password, str):
            login_verified = req_username == username and verify_dashboard_password(
                password, req_password
            )
        elif isinstance(req_challenge_id, str) and isinstance(req_password_proof, str):
            challenge_nonce = self._consume_login_challenge(req_challenge_id)
            login_verified = (
                req_username == username
                and isinstance(challenge_nonce, str)
                and verify_dashboard_login_proof(
                    password, challenge_nonce, req_password_proof
                )
            )
        else:
            return Response().error("Invalid request payload").__dict__

        if login_verified:
            change_pwd_hint = False
            legacy_pwd_hint = is_legacy_dashboard_password(password)
            if (
                username == "astrbot"
                and is_default_dashboard_password(password)
                and not DEMO_MODE
            ):
                change_pwd_hint = True
                logger.warning(
                    "The dashboard is using the default password, please change it immediately to ensure security."
                )
                legacy_pwd_hint = True

            return (
                Response()
                .ok(
                    {
                        "token": self.generate_jwt(username),
                        "username": username,
                        "change_pwd_hint": change_pwd_hint,
                        "legacy_pwd_hint": legacy_pwd_hint,
                    },
                )
                .__dict__
            )
        return Response().error("User not found or incorrect password").__dict__

    def _prune_login_challenges(self) -> None:
        now = datetime.datetime.now(datetime.timezone.utc)
        expired_ids = [
            challenge_id
            for challenge_id, challenge in self._login_challenges.items()
            if challenge.get("expires_at") <= now
        ]
        for challenge_id in expired_ids:
            self._login_challenges.pop(challenge_id, None)

    def _consume_login_challenge(self, challenge_id: str) -> str | None:
        self._prune_login_challenges()
        challenge = self._login_challenges.pop(challenge_id, None)
        if not isinstance(challenge, dict):
            return None
        nonce = challenge.get("nonce")
        return nonce if isinstance(nonce, str) else None

    async def edit_account(self):
        if DEMO_MODE:
            return (
                Response()
                .error("You are not permitted to do this operation in demo mode")
                .__dict__
            )

        password = self.config["dashboard"]["password"]
        post_data = await request.json
        if not isinstance(post_data, dict):
            return Response().error("Invalid request payload").__dict__

        req_password = post_data.get("password")
        if not isinstance(req_password, str):
            return Response().error("Invalid request payload").__dict__

        if not verify_dashboard_password(password, req_password):
            return Response().error("原密码错误").__dict__

        new_pwd = post_data.get("new_password", None)
        new_username = post_data.get("new_username", None)
        if not new_pwd and not new_username:
            return Response().error("新用户名和新密码不能同时为空").__dict__

        # Verify password confirmation
        if new_pwd:
            if not isinstance(new_pwd, str):
                return Response().error("新密码无效").__dict__
            confirm_pwd = post_data.get("confirm_password", None)
            if not isinstance(confirm_pwd, str) or confirm_pwd != new_pwd:
                return Response().error("两次输入的新密码不一致").__dict__
            try:
                validate_dashboard_password(new_pwd)
            except ValueError as e:
                return Response().error(str(e)).__dict__
            self.config["dashboard"]["password"] = hash_dashboard_password(new_pwd)
        if new_username:
            self.config["dashboard"]["username"] = new_username

        self.config.save_config()

        return Response().ok(None, "Updated account successfully").__dict__

    def generate_jwt(self, username):
        payload = {
            "username": username,
            "exp": datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(days=7),
        }
        jwt_token = self.config["dashboard"].get("jwt_secret", None)
        if not jwt_token:
            raise ValueError("JWT secret is not set in the cmd_config.")
        token = jwt.encode(payload, jwt_token, algorithm="HS256")
        return token
