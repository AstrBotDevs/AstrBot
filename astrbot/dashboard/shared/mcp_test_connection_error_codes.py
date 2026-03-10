import json
from pathlib import Path

_ERROR_CODES_PATH = Path(__file__).with_name("mcp_test_connection_error_codes.json")
_ERROR_CODES = json.loads(_ERROR_CODES_PATH.read_text(encoding="utf-8"))

MCP_STDIO_COMMAND_NOT_FOUND = _ERROR_CODES["MCP_STDIO_COMMAND_NOT_FOUND"]
MCP_TEST_CONNECTION_FAILED = _ERROR_CODES["MCP_TEST_CONNECTION_FAILED"]
