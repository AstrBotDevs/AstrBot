import re

_SECRET_KEYS = (
    r"(api_?key|access_?token|auth_?token|refresh_?token|session_?id|secret|password)"
)

_JSON_FIELD_PATTERN = re.compile(
    rf"(?i)(['\"])({_SECRET_KEYS})\1\s*:\s*(['\"])[^'\"]+\3"
)
_AUTH_JSON_FIELD_PATTERN = re.compile(
    r"(?i)(['\"])authorization\1\s*:\s*(['\"])bearer\s+[^'\"]+\2"
)
_QUERY_FIELD_PATTERN = re.compile(rf"(?i)\b{_SECRET_KEYS}\s*=\s*[^&'\" ]+")
_QUERY_PARAM_PATTERN = re.compile(
    r"(?i)([?&](?:api_?key|key|access_?token|auth_?token))=[^&'\" ]+"
)
_AUTH_HEADER_PATTERN = re.compile(
    r"(?i)\bauthorization\s*:\s*bearer\s+[A-Za-z0-9._\-]+"
)
_BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]+")
_SK_PATTERN = re.compile(r"\bsk-[A-Za-z0-9]{16,}\b")


def _redact_json_like(text: str) -> str:
    text = _JSON_FIELD_PATTERN.sub("[REDACTED]", text)
    return _AUTH_JSON_FIELD_PATTERN.sub("[REDACTED]", text)


def _redact_query_like(text: str) -> str:
    text = _QUERY_FIELD_PATTERN.sub("[REDACTED]", text)
    return _QUERY_PARAM_PATTERN.sub("[REDACTED]", text)


def _redact_tokens(text: str) -> str:
    text = _AUTH_HEADER_PATTERN.sub("[REDACTED]", text)
    text = _BEARER_PATTERN.sub("[REDACTED]", text)
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
    text = str(error)
    if redact:
        text = redact_sensitive_text(text)
    return prefix + text
