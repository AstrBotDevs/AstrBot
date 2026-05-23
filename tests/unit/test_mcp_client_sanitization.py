from astrbot.core.agent.mcp_client import _sanitize_mcp_arguments


def test_sanitize_mcp_arguments_drops_empty_optional_object_fields():
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "area": {"type": "string"},
            "floor": {"type": "string"},
            "domain": {"type": "array", "items": {"type": "string"}},
            "device_class": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["name"],
    }

    value = {
        "name": "demo",
        "area": "",
        "floor": "",
        "domain": ["light"],
        "device_class": [],
    }

    assert _sanitize_mcp_arguments(value, schema) == {
        "name": "demo",
        "domain": ["light"],
    }


def test_sanitize_mcp_arguments_preserves_required_empty_values():
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "metadata": {
                "type": "object",
                "properties": {
                    "note": {"type": "string"},
                },
            },
        },
        "required": ["name", "tags", "metadata"],
    }

    value = {
        "name": "",
        "tags": [],
        "metadata": {},
    }

    assert _sanitize_mcp_arguments(value, schema) == value


def test_sanitize_mcp_arguments_preserves_list_positions():
    schema = {"type": "array", "items": {"type": "string"}}

    value = ["alpha", "", "omega"]

    assert _sanitize_mcp_arguments(value, schema) == ["alpha", "", "omega"]
