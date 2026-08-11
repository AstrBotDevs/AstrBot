"""Generate formatted Pydantic v2 models from normalized NapCat JSON Schema."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema-path", type=Path)
    parser.add_argument("--output-path", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    schema_path = (
        args.schema_path
        or repo_root
        / ".tmp"
        / "napcat-schema"
        / "ob11-all-event.normalized.schema.json"
    ).resolve()
    output_path = (
        args.output_path
        or repo_root / ".tmp" / "napcat-schema" / "ob11_event_models.py"
    ).resolve()
    if schema_path == output_path:
        raise SystemExit("SchemaPath and OutputPath must be different.")
    if shutil.which("uv") is None or shutil.which("uvx") is None:
        raise SystemExit("Required commands not found: uv and uvx")
    if not schema_path.is_file():
        raise SystemExit(f"Schema file not found: {schema_path}")
    try:
        json.loads(schema_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"Schema file is not valid JSON: {schema_path}\n{exc}"
        ) from exc

    output_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "uvx",
            "--python",
            "3.14",
            "--from",
            "datamodel-code-generator",
            "datamodel-codegen",
            "--input",
            str(schema_path),
            "--input-file-type",
            "jsonschema",
            "--output",
            str(output_path),
            "--output-model-type",
            "pydantic_v2.BaseModel",
            "--target-python-version",
            "3.14",
            "--formatters",
            "builtin",
            "--disable-timestamp",
            "--extra-fields",
            "forbid",
            "--use-schema-description",
            "--field-constraints",
            "--use-generic-base-class",
        ],
        check=True,
        cwd=repo_root,
    )
    if not output_path.is_file():
        raise SystemExit(f"Python models file was not created: {output_path}")
    subprocess.run(
        ["uv", "run", "ruff", "check", "--fix", str(output_path)], check=True
    )
    subprocess.run(["uv", "run", "ruff", "format", str(output_path)], check=True)
    print(f"Generated Python models:\n  {output_path}")


if __name__ == "__main__":
    main()
