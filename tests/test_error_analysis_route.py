from astrbot.dashboard.routes.error_analysis import (
    parse_json_from_model_output,
    redact_sensitive_text,
)


def test_parse_json_from_model_output_plain_json():
    payload, raw = parse_json_from_model_output('{"summary":"ok","confidence":0.7}')

    assert payload is not None
    assert payload["summary"] == "ok"
    assert payload["confidence"] == 0.7
    assert raw == '{"summary":"ok","confidence":0.7}'


def test_parse_json_from_model_output_markdown_block():
    content = """```json
{
  "summary": "from fenced",
  "severity": "high"
}
```"""
    payload, _ = parse_json_from_model_output(content)

    assert payload is not None
    assert payload["summary"] == "from fenced"
    assert payload["severity"] == "high"


def test_parse_json_from_model_output_invalid():
    payload, raw = parse_json_from_model_output("not-json")

    assert payload is None
    assert raw == "not-json"


def test_redact_sensitive_text_masks_known_patterns():
    text = (
        "Authorization: Bearer very_secret_token\n"
        "api_key=abc123456\n"
        "password=hunter2\n"
        "sk-abcdefghijklmnop"
    )

    redacted = redact_sensitive_text(text)

    assert "very_secret_token" not in redacted
    assert "abc123456" not in redacted
    assert "hunter2" not in redacted
    assert "sk-abcdefghijklmnop" not in redacted
    assert "Bearer ****" in redacted
    assert "api_key=****" in redacted
    assert "password=****" in redacted
    assert "sk-****" in redacted
