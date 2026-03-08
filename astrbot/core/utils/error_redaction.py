import re

_SECRET_KEYS = (
    r"(?:api_?key|access_?token|auth_?token|refresh_?token|session_?id|secret|password)"
)

_JSON_FIELD_PATTERN = re.compile(
    rf"(?i)(?P<prefix>(?P<kq>['\"]){_SECRET_KEYS}(?P=kq)\s*:\s*)(?P<vq>['\"])(?P<value>[^'\"]+)(?P=vq)"
)
_AUTH_JSON_FIELD_PATTERN = re.compile(
    r"(?i)(?P<prefix>(?P<kq>['\"])authorization(?P=kq)\s*:\s*)(?P<vq>['\"])bearer\s+[^'\"]+(?P=vq)"
)
_QUERY_FIELD_PATTERN = re.compile(
    rf"(?i)(?P<prefix>{_SECRET_KEYS}\s*=\s*)(?P<value>[^&'\" ]+)"
)
_QUERY_PARAM_PATTERN = re.compile(
    r"(?i)(?P<prefix>[?&](?:api_?key|key|access_?token|auth_?token)=)(?P<value>[^&'\" ]+)"
)
_AUTH_HEADER_PATTERN = re.compile(
    r"(?i)(?P<prefix>\bauthorization\s*:\s*bearer\s+)(?P<token>[A-Za-z0-9._\-]+)"
)
_BEARER_PATTERN = re.compile(r"(?i)(?P<prefix>\bbearer\s+)(?P<token>[A-Za-z0-9._\-]+)")
_SK_PATTERN = re.compile(r"\bsk-[A-Za-z0-9]{16,}\b")


def _redact_json_field(match: re.Match[str]) -> str:
    quote = match.group("vq")
    return f"{match.group('prefix')}{quote}[REDACTED]{quote}"


def _redact_auth_json_field(match: re.Match[str]) -> str:
    quote = match.group("vq")
    return f"{match.group('prefix')}{quote}Bearer [REDACTED]{quote}"


def _redact_prefixed_value(match: re.Match[str]) -> str:
    return f"{match.group('prefix')}[REDACTED]"


def _redact_bearer_token(match: re.Match[str]) -> str:
    return f"{match.group('prefix')}[REDACTED]"


def _redact_json_like(text: str) -> str:
    text = _JSON_FIELD_PATTERN.sub(_redact_json_field, text)
    return _AUTH_JSON_FIELD_PATTERN.sub(_redact_auth_json_field, text)


def _redact_query_like(text: str) -> str:
    text = _QUERY_FIELD_PATTERN.sub(_redact_prefixed_value, text)
    return _QUERY_PARAM_PATTERN.sub(_redact_prefixed_value, text)


def _redact_tokens(text: str) -> str:
    text = _AUTH_HEADER_PATTERN.sub(_redact_bearer_token, text)
    text = _BEARER_PATTERN.sub(_redact_bearer_token, text)
    return _SK_PATTERN.sub("[REDACTED]", text)


def redact_sensitive_text(text: str) -> str:
    text = _redact_json_like(text)
    text = _redact_query_like(text)
    text = _redact_tokens(text)
    return text


def safe_error(
    prefix: str,
    error: Exception | BaseException | str,
    *,
    redact: bool = True,
) -> str:
    try:
        text = str(error)
    except Exception:
        try:
            text = repr(error)
        except Exception:
            text = "<unprintable error>"
    if redact:
        text = redact_sensitive_text(text)
    return prefix + text
