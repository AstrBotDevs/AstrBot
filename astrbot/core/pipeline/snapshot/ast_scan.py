from __future__ import annotations

import ast
import inspect
import sys
import textwrap
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from .ast_risk_scanner import _RiskScanner

# Effect enums (explicit targets/ops/confidence)
EFFECT_TARGETS: set[str] = {
    "provider_request.prompt",
    "provider_request.system_prompt",
    "provider_request.contexts",
    "provider_request.extra_user_content_parts",
    "provider_request.func_tool",
    "llm_response.completion_text",
    "llm_response.result_chain",
    "llm_response.tools_call_name",
    "llm_response.tools_call_args",
    "result.chain",
    "event.message_str",
    "send",
    "stop",
}
EFFECT_OPS: set[str] = {"append", "overwrite", "clear", "mutate_list", "call"}
EFFECT_CONFIDENCE: set[str] = {"high", "medium", "low"}


@dataclass(frozen=True)
class StaticScanResult:
    """兼容旧 `scan_static_risks()` 的返回值（可解包为 2 项），并新增 effects。"""

    risks: list[dict[str, Any]]
    llm_mutations: dict[str, Any]
    effects: list[dict[str, Any]]

    def __iter__(self) -> Iterator[Any]:
        # backward compatible: `risks, llm_mutations = scan_static_risks(...)`
        yield self.risks
        yield self.llm_mutations

    def __len__(self) -> int:
        return 2

    def __getitem__(self, idx: int) -> Any:
        if idx == 0:
            return self.risks
        if idx == 1:
            return self.llm_mutations
        raise IndexError(idx)


class _SelfCallScanner(ast.NodeVisitor):
    def __init__(self) -> None:
        self.calls: set[str] = set()

    def visit_Call(self, node: ast.Call) -> Any:
        fn = node.func
        if (
            isinstance(fn, ast.Attribute)
            and isinstance(fn.value, ast.Name)
            and fn.value.id == "self"
            and isinstance(fn.attr, str)
            and fn.attr
        ):
            self.calls.add(fn.attr)
        self.generic_visit(node)


class _NameCallScanner(ast.NodeVisitor):
    def __init__(self) -> None:
        self.calls: set[str] = set()

    def visit_Call(self, node: ast.Call) -> Any:
        fn = node.func
        if isinstance(fn, ast.Name) and isinstance(fn.id, str) and fn.id:
            self.calls.add(fn.id)
        self.generic_visit(node)


def _format_parse_error(err: BaseException) -> str:
    if isinstance(err, SyntaxError):
        msg = getattr(err, "msg", "") or str(err)
        parts: list[str] = [f"{err.__class__.__name__}: {msg}"]
        lineno = getattr(err, "lineno", None)
        offset = getattr(err, "offset", None)
        text = getattr(err, "text", None)

        if lineno is not None:
            parts.append(f"line={lineno}")
        if offset is not None:
            parts.append(f"col={offset}")
        if text:
            parts.append(f"text={str(text).strip()[:200]}")
        return ", ".join(parts)

    return f"{err.__class__.__name__}: {err}"


def _parse_source_compat(src: str) -> ast.AST:
    source = textwrap.dedent(src)

    try:
        return ast.parse(source)
    except SyntaxError as first_err:
        # 兼容：部分 handler 的源码片段可能整体带缩进（例如被提取自嵌套作用域），
        # 在没有外层结构时会触发 IndentationError。这里用 if True: 包裹后再解析。
        if isinstance(first_err, IndentationError):
            wrapped = "if True:\n" + textwrap.indent(source, "    ")
            try:
                return ast.parse(wrapped)
            except SyntaxError:
                pass

        # 仅当运行时支持 feature_version 时，尝试向后兼容解析（用于新运行时解析旧语法差异）
        try:
            sig = inspect.signature(ast.parse)
        except Exception:
            raise first_err

        if "feature_version" not in sig.parameters:
            raise first_err

        current_minor = int(getattr(sys.version_info, "minor", 0) or 0)
        for minor in range(max(current_minor - 1, 7), 7, -1):
            try:
                return ast.parse(source, feature_version=minor)
            except SyntaxError:
                continue

        raise first_err


__all__ = [
    "EFFECT_TARGETS",
    "EFFECT_OPS",
    "EFFECT_CONFIDENCE",
    "StaticScanResult",
    "_RiskScanner",
    "_SelfCallScanner",
    "_NameCallScanner",
    "_format_parse_error",
    "_parse_source_compat",
]
