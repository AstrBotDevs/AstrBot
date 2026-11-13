from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from urllib.parse import quote
from uuid import NAMESPACE_URL, uuid5

from astrbot import __version__, logger

DEFAULT_USER_AGENT = f"astrbot/{__version__}"
CONVERSATION_ID_HEADER = "x-astrbot-conversation-id"

_VARIABLES = "conversation_id|umo|request_id|model|provider_id|version"
# Only known placeholders are replaced. Any other text, including other braces,
# is sent exactly as configured.
_VARIABLE_RE = re.compile(rf"\{{({_VARIABLES})\}}")
# Hash and UUID transforms may only contain literal text and known variables.
_TRANSFORM_RE = re.compile(
    rf"\{{(sha256|uuid5):((?:[^{{}}]|\{{(?:{_VARIABLES})\}})+)\}}"
)
_REQUEST_TIME_VARIABLES = frozenset({"conversation_id", "umo", "request_id", "model"})
# Printable ASCII except "%" is kept in variable values. Anything else, such as a
# Chinese platform ID or a line break, is percent-encoded as UTF-8.
_HEADER_SAFE_CHARACTERS = "".join(
    chr(code) for code in range(0x20, 0x7F) if chr(code) != "%"
)
# Authentication headers carry API keys, which are never a template variable.
# They are always sent exactly as configured.
_FIXED_HEADERS = frozenset(
    {"authorization", "proxy-authorization", "x-api-key", "api-key", "x-goog-api-key"}
)


@dataclass(frozen=True)
class RequestHeaderContext:
    """Values available to provider custom header templates."""

    conversation_id: str = ""
    umo: str = ""
    request_id: str = ""
    model: str = ""
    provider_id: str = ""
    version: str = ""


def render_header_template(template: str, ctx: RequestHeaderContext) -> str | None:
    """Replace known variables in one custom header value.

    Args:
        template: Header value that may contain known variables.
        ctx: Values available to the variables.

    Returns:
        The rendered value, or None when a referenced variable is empty.
        Values outside hash and UUID transforms are percent-encoded outside printable ASCII.
    """
    values = {
        "conversation_id": ctx.conversation_id or ctx.request_id,
        "umo": ctx.umo,
        "request_id": ctx.request_id,
        "model": ctx.model,
        "provider_id": ctx.provider_id,
        "version": ctx.version,
    }
    missing = False

    def value_of(match: re.Match[str], *, transformed: bool) -> str:
        nonlocal missing
        value = str(values[match.group(1)] or "")
        missing = missing or not value
        # Transforms yield valid header text, so only raw values are encoded.
        return value if transformed else quote(value, safe=_HEADER_SAFE_CHARACTERS)

    def transform(match: re.Match[str]) -> str:
        value = _VARIABLE_RE.sub(
            lambda variable: value_of(variable, transformed=True), match.group(2)
        )
        if match.group(1) == "sha256":
            return hashlib.sha256(value.encode("utf-8")).hexdigest()
        return str(uuid5(NAMESPACE_URL, "astrbot:provider-header:" + value))

    rendered = _TRANSFORM_RE.sub(transform, template)
    rendered = _VARIABLE_RE.sub(
        lambda variable: value_of(variable, transformed=False), rendered
    )
    return None if missing else rendered


def render_request_headers(
    custom_headers: dict,
    ctx: RequestHeaderContext,
) -> dict[str, str]:
    """Render request-time custom headers for one chat request.

    Args:
        custom_headers: Header name to value template mapping.
        ctx: Request values available to the templates.

    Returns:
        Rendered header mapping. Headers whose template cannot be rendered are
        omitted.
    """
    headers: dict[str, str] = {}
    for name, template in custom_headers.items():
        rendered = render_header_template(str(template), ctx)
        if rendered is not None:
            headers[str(name)] = rendered
    return headers


def split_provider_headers(
    custom_headers: object,
    ctx: RequestHeaderContext,
    *,
    request_scoped: bool,
) -> tuple[dict[str, str], dict[str, str]]:
    """Split configured custom headers into static headers and request templates.

    Args:
        custom_headers: Header name to value mapping from provider config.
        ctx: Values available when the provider instance is created.
        request_scoped: Whether the provider can inject headers per request.

    Returns:
        A ``(static_headers, request_templates)`` tuple. Static headers hold
        final values; request templates keep their configured value.
    """
    static_headers: dict[str, str] = {}
    request_templates: dict[str, str] = {}
    if not isinstance(custom_headers, dict):
        return static_headers, request_templates

    for raw_name, raw_value in custom_headers.items():
        name, value = str(raw_name), str(raw_value)
        if name.casefold() == CONVERSATION_ID_HEADER:
            # The runtime conversation header always wins over configuration.
            continue
        variables = set(_VARIABLE_RE.findall(value))
        if name.casefold() in _FIXED_HEADERS or not (
            variables or _TRANSFORM_RE.search(value)
        ):
            static_headers[name] = value
            continue
        if request_scoped and variables & _REQUEST_TIME_VARIABLES:
            request_templates[name] = value
            continue
        rendered = render_header_template(value, ctx)
        if rendered is None:
            logger.warning(
                "Provider %s omitted custom header %s: its variables have no "
                "usable value for this provider",
                ctx.provider_id or "unknown",
                name,
            )
            continue
        static_headers[name] = rendered
    return static_headers, request_templates


def match_header_names(
    headers: Mapping[str, str], default_names: Iterable[str]
) -> dict[str, str]:
    """Rename headers to the exact spelling of a default that differs only in case.

    SDKs merge default and custom headers case-sensitively, so a header such as
    ``user-agent`` would otherwise be sent next to the default ``User-Agent``.

    Args:
        headers: Header mapping to rename.
        default_names: Names of headers the SDK already sends.

    Returns:
        A new header mapping whose names match the default spelling.
    """
    names = {name.casefold(): name for name in default_names}
    return {names.get(name.casefold(), name): value for name, value in headers.items()}


def build_provider_headers(custom_headers: object = None) -> dict[str, str]:
    """Build provider headers with an overridable AstrBot user agent.

    Args:
        custom_headers: Optional, already rendered header mapping.

    Returns:
        A new header dictionary with string values and one User-Agent header.
    """
    headers = {"User-Agent": DEFAULT_USER_AGENT}
    if isinstance(custom_headers, dict):
        for name, value in custom_headers.items():
            name, value = str(name), str(value)
            if name.lower() == "user-agent":
                if value.strip():
                    headers["User-Agent"] = value
            else:
                headers[name] = value
    return headers


def build_conversation_headers(conversation_id: str | None) -> dict[str, str]:
    """Build request headers for a provider conversation.

    Args:
        conversation_id: AstrBot conversation ID to associate with the request.

    Returns:
        A header mapping containing the conversation ID, or an empty mapping when
        no conversation ID is available.
    """
    if not conversation_id:
        return {}
    return {CONVERSATION_ID_HEADER: str(conversation_id)}
