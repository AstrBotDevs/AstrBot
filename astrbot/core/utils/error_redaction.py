import re

_SECRET_PATTERNS = [
    re.compile(
        r"(?i)\"(api_?key|access_?token|auth_?token|refresh_?token|session_?id|secret|password)\"\s*:\s*\"[^\"]+\""
    ),
    re.compile(r"(?i)\"authorization\"\s*:\s*\"bearer\s+[^\"]+\""),
    re.compile(
        r"(?i)'(api_?key|access_?token|auth_?token|refresh_?token|session_?id|secret|password)'\s*:\s*'[^']+'"
    ),
    re.compile(r"(?i)'authorization'\s*:\s*'bearer\s+[^']+'"),
    re.compile(
        r"(?i)\b(api_?key|access_?token|auth_?token|refresh_?token|session_?id|secret|password)\s*=\s*[^&'\" ]+"
    ),
    re.compile(r"(?i)([?&](?:api_?key|key|access_?token|auth_?token))=[^&'\" ]+"),
    re.compile(r"(?i)\bauthorization\s*:\s*bearer\s+[A-Za-z0-9._\-]+"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]+"),
    re.compile(r"\bsk-[A-Za-z0-9]{16,}\b"),
]


def redact_sensitive_text(text: str) -> str:
    redacted = text
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def safe_error(prefix: str, error: Exception | BaseException | str) -> str:
    return prefix + redact_sensitive_text(str(error))
