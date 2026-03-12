from astrbot.core.agent.tool import FunctionTool, ToolSet


def test_google_schema_adds_default_items_for_array_parameters_without_items():
    tool = FunctionTool(
        name="lookup_sources",
        description="Look up sources by UUID.",
        parameters={
            "type": "object",
            "properties": {
                "source_uuids": {
                    "type": "array",
                    "description": "Source UUIDs to fetch.",
                }
            },
        },
    )

    schema = ToolSet(tools=[tool]).google_schema()
    source_uuids = schema["function_declarations"][0]["parameters"]["properties"][
        "source_uuids"
    ]

    assert source_uuids["type"] == "array"
    assert source_uuids["items"] == {"type": "string"}


def test_google_schema_preserves_explicit_array_item_schema():
    tool = FunctionTool(
        name="lookup_numbers",
        description="Look up integer values.",
        parameters={
            "type": "object",
            "properties": {
                "numbers": {
                    "type": "array",
                    "items": {"type": "integer", "format": "int32"},
                }
            },
        },
    )

    schema = ToolSet(tools=[tool]).google_schema()
    numbers = schema["function_declarations"][0]["parameters"]["properties"]["numbers"]

    assert numbers["type"] == "array"
    assert numbers["items"] == {"type": "integer", "format": "int32"}
