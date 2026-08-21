#!/usr/bin/env python3
"""Fail if measured Python function coverage is below the required floor."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path


def _functions(path: Path) -> list[ast.AST]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except OSError, SyntaxError:
        return []
    functions: list[ast.AST] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        decorator_names = []
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Name):
                decorator_names.append(decorator.id)
            elif isinstance(decorator, ast.Attribute):
                decorator_names.append(decorator.attr)
        if "overload" in decorator_names:
            continue
        body = node.body
        if len(body) == 1:
            statement = body[0]
            if isinstance(statement, ast.Pass):
                continue
            if (
                isinstance(statement, ast.Expr)
                and isinstance(statement.value, ast.Constant)
                and statement.value.value is Ellipsis
            ):
                continue
        functions.append(node)
    return functions


def measure(coverage_path: Path) -> tuple[int, int]:
    payload = json.loads(coverage_path.read_text(encoding="utf-8"))
    covered = 0
    total = 0
    for file_path, info in payload.get("files", {}).items():
        path = Path(file_path)
        if not path.exists():
            continue
        executed = set(info.get("executed_lines") or [])
        for function in _functions(path):
            total += 1
            span = set(
                range(function.lineno, (function.end_lineno or function.lineno) + 1)
            )
            if span & executed:
                covered += 1
    return covered, total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coverage-file", type=Path, required=True)
    parser.add_argument("--min", type=float, default=99.0)
    args = parser.parse_args()
    covered, total = measure(args.coverage_file)
    if total == 0:
        print("no functions measured")
        return 1
    percent = 100.0 * covered / total
    print(f"function coverage: {covered}/{total} = {percent:.2f}%")
    if percent + 1e-9 < args.min:
        print(f"required function coverage {args.min:.2f}% not met")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
