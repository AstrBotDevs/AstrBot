import asyncio
import hashlib
import hmac
from typing import Any, cast

from astrbot import logger
from astrbot.api.event import MessageChain
from astrbot.api.message_components import Plain
from astrbot.api.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    Platform,
    PlatformMetadata,
)
from astrbot.core.platform.astr_message_event import MessageSesion
from astrbot.core.platform.platform import PlatformStatus
from astrbot.core.utils.webhook_utils import log_webhook_info

from ...register import register_platform_adapter
from .github_webhook_event import GitHubWebhookMessageEvent


@register_platform_adapter(
    "github_webhook",
    "GitHub Webhook 适配器",
    support_streaming_message=False,
)
class GitHubWebhookPlatformAdapter(Platform):
    """GitHub Webhook 平台适配器

    支持的事件:
    - issues (created)
    - issue_comment (created)
    - pull_request (opened)
    """

    def __init__(
        self,
        platform_config: dict,
        platform_settings: dict,
        event_queue: asyncio.Queue,
    ) -> None:
        super().__init__(platform_config, event_queue)

        self.unified_webhook_mode = platform_config.get("unified_webhook_mode", True)
        self.webhook_secret = platform_config.get("webhook_secret", "")
        self.shutdown_event = asyncio.Event()

    async def send_by_session(
        self,
        session: MessageSesion,
        message_chain: MessageChain,
    ):
        """GitHub Webhook 是单向接收，不支持主动发送消息"""
        logger.warning("GitHub Webhook 适配器不支持 send_by_session")

    def meta(self) -> PlatformMetadata:
        return PlatformMetadata(
            name="github_webhook",
            description="GitHub Webhook 适配器",
            id=cast(str, self.config.get("id")),
        )

    async def run(self):
        """运行适配器"""
        self.status = PlatformStatus.RUNNING

        # 如果启用统一 webhook 模式
        webhook_uuid = self.config.get("webhook_uuid")
        if self.unified_webhook_mode and webhook_uuid:
            log_webhook_info(f"{self.meta().id}(GitHub Webhook)", webhook_uuid)
            # 保持运行状态，等待 shutdown
            await self.shutdown_event.wait()
        else:
            logger.warning("GitHub Webhook 适配器需要启用统一 webhook 模式")
            await self.shutdown_event.wait()

    async def webhook_callback(self, request: Any) -> Any:
        """统一 Webhook 回调入口

        处理 GitHub webhook 事件

        Args:
            request: Quart 请求对象

        Returns:
            响应数据
        """
        try:
            # 获取事件类型
            event_type = request.headers.get("X-GitHub-Event", "")

            # 获取请求数据
            payload = await request.json

            # 验证 webhook 签名（如果配置了 secret）
            if self.webhook_secret:
                if not await self._verify_signature(request, payload):
                    logger.warning("GitHub webhook 签名验证失败")
                    return {"error": "Invalid signature"}, 401

            logger.debug(f"收到 GitHub Webhook 事件: {event_type}")

            # 处理不同类型的事件
            if event_type == "issues":
                await self._handle_issue_event(payload)
            elif event_type == "issue_comment":
                await self._handle_issue_comment_event(payload)
            elif event_type == "pull_request":
                await self._handle_pull_request_event(payload)
            elif event_type == "ping":
                # GitHub webhook 验证事件
                return {"message": "pong"}
            else:
                logger.debug(f"忽略不支持的 GitHub 事件类型: {event_type}")

            return {"status": "ok"}

        except Exception as e:
            logger.error(f"处理 GitHub webhook 回调时发生错误: {e}", exc_info=True)
            return {"error": str(e)}, 500

    async def _verify_signature(self, request: Any, payload: dict) -> bool:
        """验证 GitHub webhook 签名

        Args:
            request: Quart 请求对象
            payload: 请求负载数据

        Returns:
            签名是否有效
        """
        signature_header = request.headers.get("X-Hub-Signature-256", "")
        if not signature_header:
            # 如果没有签名头，检查是否有旧版本的签名
            signature_header = request.headers.get("X-Hub-Signature", "")
            if not signature_header:
                return False

        # 获取原始请求体
        body = await request.get_data()

        # 计算 HMAC
        if signature_header.startswith("sha256="):
            expected_signature = hmac.new(
                self.webhook_secret.encode("utf-8"),
                body,
                hashlib.sha256,
            ).hexdigest()
            received_signature = signature_header.replace("sha256=", "")
        elif signature_header.startswith("sha1="):
            expected_signature = hmac.new(
                self.webhook_secret.encode("utf-8"),
                body,
                hashlib.sha1,
            ).hexdigest()
            received_signature = signature_header.replace("sha1=", "")
        else:
            return False

        # 使用 hmac.compare_digest 防止时序攻击
        return hmac.compare_digest(expected_signature, received_signature)

    async def _handle_issue_event(self, payload: dict):
        """处理 issue 事件"""
        action = payload.get("action", "")

        # 只处理创建事件
        if action != "created" and action != "opened":
            return

        issue = payload.get("issue", {})
        repo = payload.get("repository", {})
        sender = payload.get("sender", {})

        # 构造消息文本
        message_text = (
            f"📝 新 Issue 创建\n"
            f"仓库: {repo.get('full_name', 'unknown')}\n"
            f"标题: {issue.get('title', 'No title')}\n"
            f"作者: {sender.get('login', 'unknown')}\n"
            f"链接: {issue.get('html_url', '')}\n"
            f"内容:\n{issue.get('body', 'No description')[:200]}"
        )

        # 创建 AstrBotMessage
        abm = self._create_message(
            message_text,
            sender.get("login", "unknown"),
            sender.get("login", "unknown"),
            repo.get("full_name", "unknown"),
        )

        # 提交事件
        self.commit_event(
            GitHubWebhookMessageEvent(
                message_text,
                abm,
                self.meta(),
                repo.get("full_name", "unknown"),
                "issues",
                payload,
            )
        )

    async def _handle_issue_comment_event(self, payload: dict):
        """处理 issue 评论事件"""
        action = payload.get("action", "")

        # 只处理创建事件
        if action != "created":
            return

        issue = payload.get("issue", {})
        comment = payload.get("comment", {})
        repo = payload.get("repository", {})
        sender = payload.get("sender", {})

        # 构造消息文本
        message_text = (
            f"💬 新 Issue 评论\n"
            f"仓库: {repo.get('full_name', 'unknown')}\n"
            f"Issue: {issue.get('title', 'No title')}\n"
            f"评论者: {sender.get('login', 'unknown')}\n"
            f"链接: {comment.get('html_url', '')}\n"
            f"内容:\n{comment.get('body', 'No comment')[:200]}"
        )

        # 创建 AstrBotMessage
        abm = self._create_message(
            message_text,
            sender.get("login", "unknown"),
            sender.get("login", "unknown"),
            repo.get("full_name", "unknown"),
        )

        # 提交事件
        self.commit_event(
            GitHubWebhookMessageEvent(
                message_text,
                abm,
                self.meta(),
                repo.get("full_name", "unknown"),
                "issue_comment",
                payload,
            )
        )

    async def _handle_pull_request_event(self, payload: dict):
        """处理 pull request 事件"""
        action = payload.get("action", "")

        # 只处理打开事件
        if action != "opened":
            return

        pr = payload.get("pull_request", {})
        repo = payload.get("repository", {})
        sender = payload.get("sender", {})

        # 构造消息文本
        message_text = (
            f"🔀 新 Pull Request\n"
            f"仓库: {repo.get('full_name', 'unknown')}\n"
            f"标题: {pr.get('title', 'No title')}\n"
            f"作者: {sender.get('login', 'unknown')}\n"
            f"链接: {pr.get('html_url', '')}\n"
            f"内容:\n{pr.get('body', 'No description')[:200]}"
        )

        # 创建 AstrBotMessage
        abm = self._create_message(
            message_text,
            sender.get("login", "unknown"),
            sender.get("login", "unknown"),
            repo.get("full_name", "unknown"),
        )

        # 提交事件
        self.commit_event(
            GitHubWebhookMessageEvent(
                message_text,
                abm,
                self.meta(),
                repo.get("full_name", "unknown"),
                "pull_request",
                payload,
            )
        )

    def _create_message(
        self,
        message_text: str,
        user_id: str,
        nickname: str,
        session_id: str,
    ) -> AstrBotMessage:
        """创建 AstrBotMessage 对象"""
        abm = AstrBotMessage()
        abm.type = MessageType.GROUP_MESSAGE
        abm.self_id = self.client_self_id
        abm.session_id = session_id
        abm.message_id = ""
        abm.sender = MessageMember(user_id=user_id, nickname=nickname)
        abm.message = [Plain(message_text)]
        abm.message_str = message_text
        abm.raw_message = message_text

        return abm

    async def terminate(self):
        """终止适配器运行"""
        self.shutdown_event.set()
        logger.info("GitHub Webhook 适配器已经被优雅地关闭")
