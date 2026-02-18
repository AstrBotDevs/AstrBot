import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])

try:
    import tomllib
except Exception:
    try:
        import tomli as tomllib
    except Exception:
        print(json.dumps({"requires_python": None}))
        raise SystemExit(0)

try:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
except Exception:
    print(json.dumps({"requires_python": None}))
    raise SystemExit(0)

project = data.get("project") if isinstance(data, dict) else None
requires_python = project.get("requires-python") if isinstance(project, dict) else None
print(json.dumps({"requires_python": requires_python}))
