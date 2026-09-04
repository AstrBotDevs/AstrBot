"""Regression tests for dashboard JWT audience and type separation."""

from datetime import datetime, timedelta, timezone

import pytest

from astrbot.dashboard.auth_tokens import (
    DashboardTokenError,
    decode_dashboard_session_token,
    decode_plugin_asset_token,
    issue_dashboard_session_token,
    issue_plugin_asset_token,
)


def test_dashboard_session_round_trip():
    """A typed dashboard token authenticates only with its own signing key."""
    token = issue_dashboard_session_token(
        username="astrbot",
        secret="dashboard-secret-for-tests-123456",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        auth_source="password",
    )

    assert (
        decode_dashboard_session_token(
            token, secret="dashboard-secret-for-tests-123456"
        )
        == "astrbot"
    )


def test_plugin_asset_cannot_authenticate_dashboard_session():
    """Asset tokens cannot be confused with full dashboard sessions."""
    token = issue_plugin_asset_token(
        username="astrbot",
        plugin_name="example",
        page_name="index",
        locale="en-US",
        secret="asset-secret-for-tests-123456789",
    )

    with pytest.raises(DashboardTokenError):
        decode_dashboard_session_token(token, secret="asset-secret-for-tests-123456789")


def test_dashboard_session_cannot_authenticate_plugin_asset():
    """Dashboard sessions cannot be used as page-scoped asset credentials."""
    token = issue_dashboard_session_token(
        username="astrbot",
        secret="dashboard-secret-for-tests-123456",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        auth_source="password",
    )

    with pytest.raises(DashboardTokenError):
        decode_plugin_asset_token(token, secret="dashboard-secret-for-tests-123456")
