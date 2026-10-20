"""Credential and stream-boundary regressions for diagnostic exports."""

import io
import json

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


def test_stream_does_not_emit_a_credential_fragment_at_size_boundary():
    source = io.BytesIO(b"normal\nBearer private-token-without-newline")
    output = io.BytesIO()
    assert DiagnosticRedactor().copy_log(source, output, 16) is True
    assert output.getvalue() == b"normal\n"


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
