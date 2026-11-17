import hashlib
from urllib.parse import unquote
from uuid import NAMESPACE_URL, uuid5

import pytest

from astrbot import __version__
from astrbot.core.provider.headers import (
    RequestHeaderContext,
    render_header_template,
    render_request_headers,
    split_provider_headers,
)

FULL_CONTEXT = RequestHeaderContext(
    conversation_id="conversation-1",
    umo="aiocqhttp:GroupMessage:100",
    request_id="request-1",
    model="gpt-test",
    provider_id="provider-1",
    version=__version__,
)


def test_render_header_template_values():
    template = (
        "literal|{conversation_id}|{umo}|{request_id}|{model}|{provider_id}|"
        "{version}|前缀"
    )
    expected = (
        "literal|conversation-1|aiocqhttp:GroupMessage:100|request-1|gpt-test|"
        f"provider-1|{__version__}|前缀"
    )

    assert render_header_template(template, FULL_CONTEXT) == expected


@pytest.mark.parametrize(
    ("template", "expected"),
    [
        (
            '{unknown}|{conversation_id|{"app":"x"}',
            '{unknown}|{conversation_id|{"app":"x"}',
        ),
        ("{{model}}", "{gpt-test}"),
    ],
)
def test_render_header_template_keeps_unknown_text_as_is(template, expected):
    assert render_header_template(template, FULL_CONTEXT) == expected


def test_render_header_template_transforms_values():
    assert render_header_template("{sha256:{conversation_id}}", FULL_CONTEXT) == (
        hashlib.sha256(b"conversation-1").hexdigest()
    )
    assert render_header_template("{sha256:static}", FULL_CONTEXT) == (
        hashlib.sha256(b"static").hexdigest()
    )
    assert render_header_template("{sha256:pre-{model}}", FULL_CONTEXT) == (
        hashlib.sha256(b"pre-gpt-test").hexdigest()
    )
    assert render_header_template("{uuid5:{conversation_id}}", FULL_CONTEXT) == str(
        uuid5(NAMESPACE_URL, "astrbot:provider-header:conversation-1")
    )
    assert render_header_template("{uuid5:pre-{model}}", FULL_CONTEXT) == str(
        uuid5(NAMESPACE_URL, "astrbot:provider-header:pre-gpt-test")
    )


@pytest.mark.parametrize(
    "template", ["{umo}", "{model}", "{sha256:{umo}}", "{uuid5:{umo}}"]
)
def test_render_header_template_omits_missing_values(template):
    assert render_header_template(template, RequestHeaderContext()) is None


def test_render_header_template_falls_back_to_request_id():
    ctx = RequestHeaderContext(request_id="request-1")
    assert render_header_template("{conversation_id}", ctx) == "request-1"
    assert render_request_headers({"X-Session": "{conversation_id}"}, ctx) == {
        "X-Session": "request-1"
    }


def test_render_header_template_percent_encodes_unhashed_values():
    umo = "平台:GroupMessage:1\r\n100%"
    expected = "%E5%B9%B3%E5%8F%B0:GroupMessage:1%0D%0A100%25"
    ctx = RequestHeaderContext(umo=umo)

    assert render_header_template("x-{umo}", ctx) == f"x-{expected}"
    assert unquote(expected) == umo
    assert render_header_template("{sha256:{umo}}", ctx) == (
        hashlib.sha256(umo.encode()).hexdigest()
    )

    assert render_header_template("{uuid5:{umo}}", ctx) == str(
        uuid5(NAMESPACE_URL, "astrbot:provider-header:" + umo)
    )


def test_split_provider_headers_keeps_request_templates_out_of_static_headers():
    static, templates = split_provider_headers(
        {
            "X-Static": "value",
            "X-Json": '{"app":"x"}',
            "X-Braces": "{{value}}",
            "X-Sha": "{sha256:value}",
            "X-Uuid": "{uuid5:value}",
            "X-Provider": "{provider_id}",
            "X-Session": "{sha256:{conversation_id}}",
            "X-Session-Uuid": "{uuid5:{conversation_id}}",
            "X-Astrbot-Conversation-Id": "spoofed",
        },
        RequestHeaderContext(provider_id="provider-1", model="gpt-test"),
        request_scoped=True,
    )
    assert static == {
        "X-Static": "value",
        "X-Json": '{"app":"x"}',
        "X-Braces": "{{value}}",
        "X-Sha": hashlib.sha256(b"value").hexdigest(),
        "X-Uuid": str(uuid5(NAMESPACE_URL, "astrbot:provider-header:value")),
        "X-Provider": "provider-1",
    }
    assert templates == {
        "X-Session": "{sha256:{conversation_id}}",
        "X-Session-Uuid": "{uuid5:{conversation_id}}",
    }


def test_split_provider_headers_sends_auth_headers_as_configured():
    custom_headers = dict.fromkeys(
        (
            "Authorization",
            "proxy-authorization",
            "X-Api-Key",
            "api-key",
            "x-goog-api-key",
            "X-Auth-Token",
        ),
        "Bearer sk-{umo}{unknown}}{{",
    )

    static_headers, templates = split_provider_headers(
        custom_headers, FULL_CONTEXT, request_scoped=True
    )

    assert static_headers == custom_headers
    assert templates == {}
