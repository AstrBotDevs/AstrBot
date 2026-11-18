import jsonschema
import pytest

from astrbot.core.agent.tool import FunctionTool


def test_tool_parameters_report_the_same_schema_error_after_mutation():
    parameters = {"properties": {"query": {"type": "string"}}, "required": ["query"]}
    tool = FunctionTool(name="search", description="", parameters=parameters)

    # Multiple errors exercise jsonschema's choice of which one to report.
    tool.parameters["properties"]["query"]["type"] = "unknown"
    tool.parameters["required"] = 17
    with pytest.raises(jsonschema.ValidationError) as expected:
        jsonschema.validate(
            tool.parameters, jsonschema.Draft202012Validator.META_SCHEMA
        )
    with pytest.raises(jsonschema.ValidationError) as actual:
        FunctionTool(name=tool.name, description="", parameters=tool.parameters)

    assert actual.value.message == expected.value.message
    assert actual.value.path == expected.value.path
    assert actual.value.schema_path == expected.value.schema_path
