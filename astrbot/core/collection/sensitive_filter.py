from __future__ import annotations

import re
from typing import Any


class SensitiveFilter:
    """Filter sensitive values from nested config structures.

    Sensitive fields are removed instead of being replaced.
    """

    SENSITIVE_KEYWORDS = [
        "key",
        "secret",
        "token",
        "password",
        "credential",
        "api_key",
        "access_token",
        "private_key",
        "auth",
        "group_id",
        "group",
        "qq_group",
        "guild",
        "channel",
        "user_id",
        "user",
        "qq",
        "uin",
        "openid",
        "uid",
        "endpoint",
        "base_url",
        "api_base",
        "url",
        "uri",
        "webhook",
        "callback",
        "host",
        "domain",
    ]

    SENSITIVE_KEY_PATTERNS = [
        re.compile(r".*_key$", re.IGNORECASE),
        re.compile(r".*_secret$", re.IGNORECASE),
        re.compile(r".*_token$", re.IGNORECASE),
        re.compile(r".*_password$", re.IGNORECASE),
        re.compile(r".*_credential$", re.IGNORECASE),
        re.compile(r".*_access_token$", re.IGNORECASE),
        re.compile(r".*_private_key$", re.IGNORECASE),
        re.compile(r".*_group(_id)?$", re.IGNORECASE),
        re.compile(r".*_guild(_id)?$", re.IGNORECASE),
        re.compile(r".*_channel(_id)?$", re.IGNORECASE),
        re.compile(r".*_user(_id)?$", re.IGNORECASE),
        re.compile(r".*_qq$", re.IGNORECASE),
        re.compile(r".*_uin$", re.IGNORECASE),
        re.compile(r".*_openid$", re.IGNORECASE),
        re.compile(r".*_endpoint$", re.IGNORECASE),
        re.compile(r".*_base_url$", re.IGNORECASE),
        re.compile(r".*_api_base$", re.IGNORECASE),
        re.compile(r".*_url$", re.IGNORECASE),
        re.compile(r".*_uri$", re.IGNORECASE),
        re.compile(r".*_webhook(_url)?$", re.IGNORECASE),
        re.compile(r".*_callback(_url)?$", re.IGNORECASE),
        re.compile(r".*_host$", re.IGNORECASE),
        re.compile(r".*_domain$", re.IGNORECASE),
    ]

    SENSITIVE_VALUE_PATTERNS = [
        re.compile(r"^sk-.*", re.IGNORECASE),
        re.compile(r"^bearer\s+.+", re.IGNORECASE),
        re.compile(r"^https?://.+", re.IGNORECASE),
        re.compile(r"^wss?://.+", re.IGNORECASE),
    ]

    @classmethod
    def is_sensitive_key(cls, key: str) -> bool:
        key_lower = key.lower()
        if any(k in key_lower for k in cls.SENSITIVE_KEYWORDS):
            return True
        return any(p.fullmatch(key) is not None for p in cls.SENSITIVE_KEY_PATTERNS)

    @classmethod
    def is_sensitive_value(cls, value: Any) -> bool:
        if not isinstance(value, str):
            return False
        s = value.strip()
        return any(p.match(s) is not None for p in cls.SENSITIVE_VALUE_PATTERNS)

    @classmethod
    def filter_data(cls, data: Any, *, depth: int = 0, max_depth: int = 20) -> Any:
        if depth > max_depth:
            return data

        if isinstance(data, dict):
            filtered: dict[str, Any] = {}
            for k, v in data.items():
                key = str(k)
                if cls.is_sensitive_key(key):
                    continue
                if cls.is_sensitive_value(v):
                    continue
                filtered[key] = cls.filter_data(v, depth=depth + 1, max_depth=max_depth)
            return filtered

        if isinstance(data, list):
            return [
                cls.filter_data(v, depth=depth + 1, max_depth=max_depth) for v in data
            ]

        if cls.is_sensitive_value(data):
            return None

        return data
