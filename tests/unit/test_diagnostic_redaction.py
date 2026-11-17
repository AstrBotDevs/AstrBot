"""Credential and stream-boundary regressions for diagnostic exports."""

import io
import json
import subprocess
import sys
from datetime import datetime

import pytest

from astrbot.dashboard.services.diagnostic_service import DiagnosticRedactor


@pytest.mark.parametrize("flag", [True, False])
def test_status_flags_and_configuration_shape_survive_redaction(flag):
    original = {
        "password_storage_upgraded": flag,
        "password_change_required": flag,
        "max_tokens": 4096,
        "tokenizer": "demo",
        "recovery_code_hash": "private-recovery-hash",
        "app_key": "private-app-key",
        "provider": {"key": ["configured-private-credential", ""]},
    }
    redactor = DiagnosticRedactor()
    redactor.collect(original)
    exported = redactor.redact(original)
    assert exported["password_storage_upgraded"] is flag
    assert exported["password_change_required"] is flag
    assert exported["max_tokens"] == 4096
    assert exported["tokenizer"] == "demo"
    assert exported["recovery_code_hash"] == "[REDACTED]"
    assert exported["app_key"] == "[REDACTED]"
    assert exported["provider"]["key"] == ["[REDACTED]", ""]
    assert original["provider"]["key"][0] == "configured-private-credential"


def test_redacts_known_escaped_and_unconfigured_credentials():
    secret = 'secret with "quotes" and /spaces+'
    redactor = DiagnosticRedactor()
    redactor.collect({"api_key": secret})
    text = (
        secret + "\n" + json.dumps(secret) + "\n"
        "https://user:private@example.com/?key=unknown-query-key&x=1\n"
        "Bearer unknown-header-token\nCookie: a=private; b=other\n"
        "sk-abcdefghijklmnopqrstuvwxyz\n"
        "-----BEGIN OPENSSH PRIVATE KEY-----\nprivate-key-body\n-----END OPENSSH PRIVATE KEY-----"
    )
    result = redactor.text(text)
    for private in (
        secret,
        "quotes",
        "user:private",
        "unknown-query-key",
        "unknown-header-token",
        "a=private",
        "b=other",
        "sk-abc",
        "private-key-body",
    ):
        assert private not in result
    assert "&x=1" in result


@pytest.mark.parametrize(
    "key",
    ["api_key", "custom_token_value", "X-Authorization", "X-Cookie", "x.key", "key"],
)
def test_sensitive_assignment_names_remain_redacted(key):
    assert DiagnosticRedactor().text(f'"{key}": "private-value"') == (
        f'"{key}": [REDACTED]'
    )


@pytest.mark.parametrize(
    "key",
    ["encoding_aes_key", "wecomaibot_encoding_aes_key", "aes_key", "aeskey", "encodingAesKey"],
)
@pytest.mark.parametrize("enabled", [True, False])
def test_aes_keys_are_redacted_in_configuration_and_logs(key, enabled):
    secret = "example-aes-value/+="
    config = {"platform": [{key: secret}]}
    redactor = DiagnosticRedactor(enabled=enabled)
    redactor.collect(config)
    expected = "[REDACTED]" if enabled else secret
    assert redactor.redact(config) == {"platform": [{key: expected}]}
    assert redactor.text(f"configured value: {secret}") == f"configured value: {expected}"
    assert DiagnosticRedactor(enabled=enabled).text(f'"{key}": "{secret}"') == (
        f'"{key}": [REDACTED]' if enabled else f'"{key}": "{secret}"'
    )
    assert config["platform"][0][key] == secret


def test_nested_assignments_and_mixed_case_credentials_remain_redacted():
    content = (
        'message="api_key=private-nested-value" normal=visible\n'
        "AUTHORIZATION=private-authorization\n"
        "Bearer\tprivate-bearer\n"
        "recovery-code=private-recovery\n"
        "Baſic\tprivate-basic\n"
        "ſecret=private-secret\n"
        "cookıe: private-cookie\n"
    )
    result = DiagnosticRedactor().text(content)
    assert "private-" not in result
    assert "normal=visible" in result


def test_collecting_credentials_after_redaction_refreshes_the_cache():
    redactor = DiagnosticRedactor()
    redactor.collect({"api_key": "first-private-value"})
    assert redactor.text("first-private-value") == "[REDACTED]"
    redactor.collect({"api_key": "second-private-value"})
    assert redactor.text("first-private-value second-private-value") == (
        "[REDACTED] [REDACTED]"
    )


def test_long_log_tokens_do_not_stall_redaction():
    """Run adversarial lines outside pytest so a regex regression cannot hang it."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from astrbot.dashboard.services.diagnostic_service import DiagnosticRedactor\n"
            "redactor = DiagnosticRedactor()\n"
            "for value in ('a' * 100_000, 'token' * 20_000, 'token' * 20_000 + '='):\n"
            "    assert redactor.text(value) == value\n"
            "assert redactor.text('a' * 100_000 + ' token=private-value') == 'a' * 100_000 + ' token=[REDACTED]'\n"
            "assert redactor.text('token' * 20_000 + '=private-value') == 'token' * 20_000 + '=[REDACTED]'\n",
        ],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_stream_drops_oversized_lines_without_leaking_suffixes(monkeypatch):
    monkeypatch.setattr(
        "astrbot.dashboard.services.diagnostic_service.MAX_LOG_LINE_BYTES", 32
    )
    redactor = DiagnosticRedactor()
    content = b"a" * 100 + b"private-tail\nnormal log\n"
    output = io.BytesIO()
    assert redactor.copy_log(io.BytesIO(content), output, len(content)) is True
    assert output.getvalue() == b"normal log\n"


def test_stream_redacts_private_key_blocks_and_keeps_unterminated_final_line():
    content = b"normal\n-----BEGIN PRIVATE KEY-----\nsecret-body\n-----END PRIVATE KEY-----\nlast line"
    output = io.BytesIO()
    redactor = DiagnosticRedactor()
    assert redactor.copy_log(io.BytesIO(content), output, len(content)) is False
    assert output.getvalue() == b"normal\n[REDACTED]\nlast line"


def test_stream_preserves_order_and_privacy_across_batches():
    prefix = "ordinary 中文\n".encode() * 6000
    content = (
        prefix
        + b"-----BEGIN PRIVATE KEY-----\n"
        + b"private-key-body\n" * 6000
        + b"-----END PRIVATE KEY-----\n"
        + b"api_key=private-value\npeer=8.8.8.8\nlast line"
    )
    output = io.BytesIO()
    assert DiagnosticRedactor().copy_log(io.BytesIO(content), output, len(content)) is False
    assert output.getvalue() == (
        prefix + b"[REDACTED]\napi_key=[REDACTED]\npeer=[PUBLIC_IP_1]\nlast line"
    )


def test_stream_does_not_emit_a_credential_fragment_at_size_boundary():
    source = io.BytesIO(b"normal\nBearer private-token-without-newline")
    output = io.BytesIO()
    assert DiagnosticRedactor().copy_log(source, output, 16) is True
    assert output.getvalue() == b"normal\n"


@pytest.mark.parametrize("enabled", [True, False])
def test_stream_time_range_keeps_boundaries_and_traceback_continuations(enabled):
    before = b"[2026-10-21 10:59:59.999] before\nold traceback\n"
    selected = (
        b"[2026-10-21 11:00:00.000] first\nTraceback:\n  selected frame\n"
        b"[2026-10-21 11:00:01.000] last\n"
    )
    after = b"[2026-10-21 11:00:01.001] after\nnew traceback\n"
    content = b"undated preamble\n" + before + selected + after
    target = io.BytesIO()
    assert DiagnosticRedactor(enabled=enabled).copy_log(
        io.BytesIO(content),
        target,
        len(content),
        start_time=int(datetime(2026, 10, 21, 11).timestamp()),
        end_time=int(datetime(2026, 10, 21, 11, 0, 1).timestamp()),
    ) is False
    assert target.getvalue() == selected


@pytest.mark.parametrize("enabled", [True, False])
@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [(10, 20, [0, 1]), (20, None, [1, 2]), (None, 10, [0])],
)
def test_stream_time_range_filters_json_records(enabled, start, end, expected):
    lines = [
        json.dumps({"time_unix_nano": "10000000000", "data": "first"}) + "\n",
        json.dumps({"time": 20, "data": "second"}) + "\n",
        json.dumps({"start_time_unix_nano": "30000000000", "data": "third"}) + "\n",
    ]
    content = ("".join(lines) + '{"data": "undated"}\n').encode()
    target = io.BytesIO()
    DiagnosticRedactor(enabled=enabled).copy_log(
        io.BytesIO(content), target, len(content), start_time=start, end_time=end
    )
    assert target.getvalue() == "".join(lines[index] for index in expected).encode()


@pytest.mark.parametrize(
    "line",
    [
        b"[2026-10-21T03:00:00Z] selected\n",
        b"2026-10-21T11:00:00+08:00 selected\n",
        b"[2026-10-21 03:00:00,000+00:00] selected\n",
    ],
)
def test_stream_time_range_respects_explicit_timezone_offsets(line):
    stamp = int(datetime.fromisoformat("2026-10-21T03:00:00+00:00").timestamp())
    target = io.BytesIO()
    DiagnosticRedactor().copy_log(
        io.BytesIO(line), target, len(line), start_time=stamp, end_time=stamp
    )
    assert target.getvalue() == line


def test_raw_time_range_preserves_long_lines_and_non_utf8_bytes(monkeypatch):
    monkeypatch.setattr(
        "astrbot.dashboard.services.diagnostic_service.MAX_LOG_LINE_BYTES", 32
    )
    selected = b"[2026-10-21 11:00:00] " + b"a" * 100 + b"\xff\r\n"
    content = selected + b"[2026-10-21 11:00:01] excluded\n"
    stamp = int(datetime(2026, 10, 21, 11).timestamp())
    target = io.BytesIO()
    assert DiagnosticRedactor(enabled=False).copy_log(
        io.BytesIO(content), target, len(content), start_time=stamp, end_time=stamp
    ) is False
    assert target.getvalue() == selected


def test_stream_time_filter_does_not_expose_private_keys_with_dated_body_lines():
    content = (
        b"[2026-10-21 10:00:00] before\n-----BEGIN PRIVATE KEY-----\n"
        b"[2026-10-21 11:00:00] private-key-body\n-----END PRIVATE KEY-----\n"
        b"[2026-10-21 11:00:00] selected\n"
    )
    target = io.BytesIO()
    DiagnosticRedactor().copy_log(
        io.BytesIO(content),
        target,
        len(content),
        start_time=int(datetime(2026, 10, 21, 11).timestamp()),
    )
    assert target.getvalue() == b"[2026-10-21 11:00:00] selected\n"


def test_disabled_redaction_preserves_structured_values_and_original_log_bytes():
    redactor = DiagnosticRedactor(enabled=False)
    value = {
        "password": "original-secret",
        "password_storage_upgraded": True,
        "host": "8.8.8.8",
    }
    redactor.collect(value)
    assert redactor.redact(value) == value
    assert redactor.text("Bearer original-secret") == "Bearer original-secret"
    content = b"\x1b[32m8.8.8.8 [2606:4700:4700::1111]:443\r\n-----BEGIN PRIVATE KEY-----\noriginal-secret\n\xff"
    output = io.BytesIO()
    assert redactor.copy_log(io.BytesIO(content), output, len(content)) is False
    assert output.getvalue() == content


def test_public_ip_aliases_are_shared_across_config_logs_and_trace_spellings():
    redactor = DiagnosticRedactor()
    config = redactor.redact(
        {
            "api_base": "http://8.8.8.8:8080/v1",
            "ipv6": "https://[2606:4700:4700::1111]:443/v1",
        }
    )
    assert config == {
        "api_base": "http://[PUBLIC_IP_1]:8080/v1",
        "ipv6": "https://[PUBLIC_IP_2]:443/v1",
    }
    assert (
        redactor.text("client:8.8.8.8, peer=[::ffff:8.8.8.8]:80.")
        == "client:[PUBLIC_IP_1], peer=[PUBLIC_IP_1]:80."
    )
    assert redactor.redact({"peer": "2606:4700:4700:0:0:0:0:1111"}) == {
        "peer": "[PUBLIC_IP_2]"
    }
    output = io.BytesIO()
    content = b"peer=2606:4700:4700::1111. next=1.1.1.1:53\n"
    redactor.copy_log(io.BytesIO(content), output, len(content))
    assert output.getvalue() == b"peer=[PUBLIC_IP_2]. next=[PUBLIC_IP_3]:53\n"
    assert DiagnosticRedactor().text("1.1.1.1") == "[PUBLIC_IP_1]"


@pytest.mark.parametrize(
    "value",
    [
        "0.0.0.0",
        "127.0.0.1:6185",
        "10.0.0.1:8080",
        "172.16.1.1",
        "192.168.1.1",
        "169.254.1.2",
        "100.64.1.2",
        "224.0.0.1",
        "::",
        "::1",
        "[::1]:6185",
        "[fe80::1%eth0]:8080",
        "fc00::1",
        "fd12::1",
        "ff02::1",
        "::ffff:192.168.1.1",
        "version=v1.2.3.4",
        "bad=999.1.1.1",
        "bad=1.2.3.4.5",
        "12:34:56",
        "dead:beef:hello",
    ],
)
def test_local_non_global_and_non_ip_text_remains_unchanged(value):
    assert DiagnosticRedactor().text(value) == value
