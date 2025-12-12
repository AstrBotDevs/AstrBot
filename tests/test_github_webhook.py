"""Test GitHub webhook platform adapter"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.platform.sources.github_webhook.github_webhook_adapter import (
    GitHubWebhookPlatformAdapter,
)


@pytest.fixture
def event_queue():
    """Create a test event queue"""
    return asyncio.Queue()


@pytest.fixture
def platform_config():
    """Create test platform configuration"""
    return {
        "type": "github_webhook",
        "enable": True,
        "id": "test_github_webhook",
        "unified_webhook_mode": True,
        "webhook_uuid": "test-uuid-123",
        "webhook_secret": "test-secret",
    }


@pytest.fixture
def platform_settings():
    """Create test platform settings"""
    return {"unique_session": False}


@pytest.fixture
def adapter(platform_config, platform_settings, event_queue):
    """Create test adapter instance"""
    return GitHubWebhookPlatformAdapter(platform_config, platform_settings, event_queue)


class TestGitHubWebhookAdapter:
    """Test cases for GitHub webhook adapter"""

    def test_adapter_initialization(self, adapter):
        """Test adapter is initialized correctly"""
        assert adapter.unified_webhook_mode is True
        assert adapter.webhook_secret == "test-secret"
        assert adapter.meta().name == "github_webhook"
        assert adapter.meta().description == "GitHub Webhook 适配器"

    @pytest.mark.asyncio
    async def test_ping_event(self, adapter):
        """Test GitHub ping event"""
        # Mock request
        request = MagicMock()
        request.headers.get.return_value = "ping"

        async def mock_json():
            return {}

        request.json = mock_json()

        response = await adapter.webhook_callback(request)
        assert response == {"message": "pong"}

    @pytest.mark.asyncio
    async def test_issue_created_event(self, adapter, event_queue):
        """Test GitHub issue created event"""
        # Mock request with issue created payload
        request = MagicMock()
        request.headers.get.return_value = "issues"
        payload = {
            "action": "opened",
            "issue": {
                "title": "Test Issue",
                "body": "This is a test issue",
                "html_url": "https://github.com/test/repo/issues/1",
            },
            "repository": {"full_name": "test/repo"},
            "sender": {"login": "testuser"},
        }

        async def mock_json():
            return payload

        request.json = mock_json()

        response = await adapter.webhook_callback(request)
        assert response == {"status": "ok"}

        # Verify event was queued
        assert not event_queue.empty()
        event = event_queue.get_nowait()
        assert event.event_type == "issues"
        assert "新 Issue 创建" in event.message_str
        assert "Test Issue" in event.message_str

    @pytest.mark.asyncio
    async def test_issue_comment_event(self, adapter, event_queue):
        """Test GitHub issue comment event"""
        request = MagicMock()
        request.headers.get.return_value = "issue_comment"
        payload = {
            "action": "created",
            "issue": {"title": "Test Issue"},
            "comment": {
                "body": "Test comment",
                "html_url": "https://github.com/test/repo/issues/1#comment",
            },
            "repository": {"full_name": "test/repo"},
            "sender": {"login": "commenter"},
        }

        async def mock_json():
            return payload

        request.json = mock_json()

        response = await adapter.webhook_callback(request)
        assert response == {"status": "ok"}

        # Verify event was queued
        assert not event_queue.empty()
        event = event_queue.get_nowait()
        assert event.event_type == "issue_comment"
        assert "新 Issue 评论" in event.message_str
        assert "Test comment" in event.message_str

    @pytest.mark.asyncio
    async def test_pull_request_event(self, adapter, event_queue):
        """Test GitHub pull request opened event"""
        request = MagicMock()
        request.headers.get.return_value = "pull_request"
        payload = {
            "action": "opened",
            "pull_request": {
                "title": "Test PR",
                "body": "This is a test PR",
                "html_url": "https://github.com/test/repo/pull/1",
            },
            "repository": {"full_name": "test/repo"},
            "sender": {"login": "prauthor"},
        }

        async def mock_json():
            return payload

        request.json = mock_json()

        response = await adapter.webhook_callback(request)
        assert response == {"status": "ok"}

        # Verify event was queued
        assert not event_queue.empty()
        event = event_queue.get_nowait()
        assert event.event_type == "pull_request"
        assert "新 Pull Request" in event.message_str
        assert "Test PR" in event.message_str

    @pytest.mark.asyncio
    async def test_unsupported_event(self, adapter, event_queue):
        """Test unsupported GitHub event type"""
        request = MagicMock()
        request.headers.get.return_value = "push"

        async def mock_json():
            return {"action": "created"}

        request.json = mock_json()

        response = await adapter.webhook_callback(request)
        assert response == {"status": "ok"}

        # Verify no event was queued for unsupported events
        assert event_queue.empty()

    @pytest.mark.asyncio
    async def test_issue_closed_ignored(self, adapter, event_queue):
        """Test that issue closed action is ignored"""
        request = MagicMock()
        request.headers.get.return_value = "issues"
        payload = {
            "action": "closed",  # Should be ignored
            "issue": {"title": "Test Issue"},
            "repository": {"full_name": "test/repo"},
            "sender": {"login": "testuser"},
        }

        async def mock_json():
            return payload

        request.json = mock_json()

        response = await adapter.webhook_callback(request)
        assert response == {"status": "ok"}

        # Verify no event was queued
        assert event_queue.empty()
