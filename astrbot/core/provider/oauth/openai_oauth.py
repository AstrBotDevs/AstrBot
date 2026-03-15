import base64
import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

OPENAI_OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
OPENAI_OAUTH_AUTHORIZE_URL = "https://auth.openai.com/oauth/authorize"
OPENAI_OAUTH_TOKEN_URL = "https://auth.openai.com/oauth/token"
OPENAI_OAUTH_REDIRECT_URI = "http://localhost:1455/auth/callback"
OPENAI_OAUTH_SCOPE = "openid profile email offline_access"
OPENAI_OAUTH_TIMEOUT = 20.0
OPENAI_OAUTH_ACCOUNT_CLAIM_PATH = "https://api.openai.com/auth"


def create_pkce_flow() -> dict[str, str]:
    state = secrets.token_hex(16)
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).decode().rstrip("=")
    return {
        "state": state,
        "verifier": verifier,
        "challenge": challenge,
        "authorize_url": build_authorize_url(state, challenge),
    }


def build_authorize_url(state: str, challenge: str) -> str:
    query = urlencode(
        {
            "response_type": "code",
            "client_id": OPENAI_OAUTH_CLIENT_ID,
            "redirect_uri": OPENAI_OAUTH_REDIRECT_URI,
            "scope": OPENAI_OAUTH_SCOPE,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
            "id_token_add_organizations": "true",
            "codex_cli_simplified_flow": "true",
            "originator": "codex_cli_rs",
        }
    )
    return f"{OPENAI_OAUTH_AUTHORIZE_URL}?{query}"


def parse_authorization_input(raw: str) -> tuple[str, str]:
    value = (raw or "").strip()
    if not value:
        raise ValueError("empty input")
    if "code=" in value:
        parsed = urlparse(value)
        if parsed.query:
            query = parse_qs(parsed.query)
            return query.get("code", [""])[0].strip(), query.get("state", [""])[0].strip()
        query = parse_qs(value)
        return query.get("code", [""])[0].strip(), query.get("state", [""])[0].strip()
    if "#" in value:
        code, state = value.split("#", 1)
        return code.strip(), state.strip()
    return value, ""


def parse_oauth_credential_json(raw: str) -> dict[str, Any] | None:
    value = (raw or "").strip()
    if not value.startswith("{"):
        return None
    try:
        data = json.loads(value)
    except Exception as exc:
        raise ValueError(f"OAuth JSON 凭据解析失败: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("OAuth JSON 凭据必须是对象")
    access_token = str(data.get("access_token") or "").strip()
    if not access_token:
        raise ValueError("OAuth JSON 凭据缺少 access_token")
    refresh_token = str(data.get("refresh_token") or "").strip()
    expires_at = _normalize_expires_at(
        data.get("expired") or data.get("expires_at") or data.get("expires"),
    )
    account_id = str(data.get("account_id") or "").strip() or extract_account_id_from_jwt(access_token)
    email = str(data.get("email") or "").strip() or extract_email_from_jwt(access_token)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": expires_at,
        "email": email,
        "account_id": account_id,
        "raw": data,
    }


async def exchange_authorization_code(
    code: str,
    verifier: str,
    proxy_url: str = "",
) -> dict[str, Any]:
    payload = {
        "grant_type": "authorization_code",
        "client_id": OPENAI_OAUTH_CLIENT_ID,
        "code": code.strip(),
        "code_verifier": verifier.strip(),
        "redirect_uri": OPENAI_OAUTH_REDIRECT_URI,
    }
    return await _request_token(payload, proxy_url)


async def refresh_access_token(
    refresh_token: str,
    proxy_url: str = "",
) -> dict[str, Any]:
    payload = {
        "grant_type": "refresh_token",
        "client_id": OPENAI_OAUTH_CLIENT_ID,
        "refresh_token": refresh_token.strip(),
    }
    return await _request_token(payload, proxy_url)


async def _request_token(payload: dict[str, str], proxy_url: str = "") -> dict[str, Any]:
    async with httpx.AsyncClient(proxy=proxy_url or None, timeout=OPENAI_OAUTH_TIMEOUT) as client:
        response = await client.post(
            OPENAI_OAUTH_TOKEN_URL,
            data=payload,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
    data = response.json()
    if response.status_code < 200 or response.status_code >= 300:
        raise ValueError(f"oauth token request failed: status={response.status_code}, body={data}")
    access_token = (data.get("access_token") or "").strip()
    refresh_token = (data.get("refresh_token") or "").strip()
    expires_in = int(data.get("expires_in") or 0)
    if not access_token or not refresh_token or expires_in <= 0:
        raise ValueError("oauth token response missing required fields")
    expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": expires_at.isoformat(),
        "email": extract_email_from_jwt(access_token),
        "account_id": extract_account_id_from_jwt(access_token),
        "raw": data,
    }


def extract_email_from_jwt(token: str) -> str:
    claims = decode_jwt_claims(token)
    email = claims.get("email")
    return email.strip() if isinstance(email, str) else ""


def extract_account_id_from_jwt(token: str) -> str:
    claims = decode_jwt_claims(token)
    raw = claims.get(OPENAI_OAUTH_ACCOUNT_CLAIM_PATH)
    if not isinstance(raw, dict):
        return ""
    account_id = raw.get("chatgpt_account_id")
    return account_id.strip() if isinstance(account_id, str) else ""


def decode_jwt_claims(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1]
    padding = "=" * (-len(payload) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload + padding)
        obj = json.loads(decoded.decode())
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _normalize_expires_at(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), UTC).isoformat()
        except Exception:
            return ""
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return ""
        try:
            if stripped.endswith("Z"):
                stripped = stripped[:-1] + "+00:00"
            return datetime.fromisoformat(stripped).isoformat()
        except Exception:
            return value.strip()
    return ""
