import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])


def emit_result(requires_python=None, error=None, message=None):
    payload = {"requires_python": requires_python, "error": error}
    if message:
        payload["message"] = message
    print(json.dumps(payload))


try:
    import tomllib
except Exception:
    try:
        import tomli as tomllib
    except Exception:
        emit_result(
            error="toml_parser_unavailable",
            message="tomllib/tomli is unavailable for parsing pyproject.toml.",
        )
        raise SystemExit(0)

try:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
except Exception as exc:
    emit_result(error="parse_failed", message=f"Failed to parse pyproject.toml: {exc}")
    raise SystemExit(0)

project = data.get("project") if isinstance(data, dict) else None
requires_python = project.get("requires-python") if isinstance(project, dict) else None
emit_result(requires_python=requires_python)
