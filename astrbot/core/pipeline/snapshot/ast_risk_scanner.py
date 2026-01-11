from __future__ import annotations

import ast
from typing import Any


class _RiskScanner(ast.NodeVisitor):
    def __init__(self) -> None:
        self.calls: set[str] = set()
        self.assigns: set[str] = set()
        self.aug_assigns: set[str] = set()
        self.yields_result: bool = False

        self.effects: list[dict[str, Any]] = []
        self._effect_keys: set[tuple[Any, ...]] = set()

        # inferred from top-level handler signature
        self.event_vars: set[str] = set()
        self.req_vars: set[str] = set()
        self.llm_response_vars: set[str] = set()
        self._llm_response_vars_inferred: set[str] = set()

        self.result_vars: set[str] = set()
        self.chain_vars: set[str] = set()

        self.stop_event_confidence: str | None = None
        self.stop_event_confidence_reason: str | None = None
        self.stop_event_sites: list[dict[str, Any]] = []

        self._guard_stack: list[str] = []
        self._fn_depth: int = 0

        self.persona_prompt_overwrite: bool = False
        self.persona_prompt_append: bool = False

    @staticmethod
    def _const_str(node: ast.AST) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Str):
            val = getattr(node, "s", None)
            return val if isinstance(val, str) else None
        return None

    @classmethod
    def _slice_str(cls, node: ast.AST) -> str | None:
        if isinstance(node, ast.Index):
            inner = getattr(node, "value", None)
            return cls._slice_str(inner) if inner is not None else None
        return cls._const_str(node)

    @staticmethod
    def _is_persona_base(node: ast.AST) -> bool:
        if isinstance(node, ast.Name):
            name = node.id
            if name == "persona":
                return True
            lowered = name.lower()
            if "persona" in lowered or "personality" in lowered:
                return True
        if isinstance(node, ast.Attribute) and node.attr == "persona":
            return True
        return False

    @classmethod
    def _is_persona_prompt_attr(cls, node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Attribute)
            and node.attr == "prompt"
            and cls._is_persona_base(node.value)
        )

    @classmethod
    def _is_persona_prompt_subscript(cls, node: ast.AST) -> bool:
        if not isinstance(node, ast.Subscript):
            return False
        if not cls._is_persona_base(node.value):
            return False
        key = cls._slice_str(node.slice)
        return key == "prompt"

    @staticmethod
    def _confidence_rank(level: str) -> int:
        return {"low": 0, "medium": 1, "high": 2}.get(level, -1)

    def _record_stop_event(
        self, *, confidence: str, reason: str, node: ast.AST
    ) -> None:
        self.stop_event_sites.append(
            {
                "confidence": confidence,
                "reason": reason,
                "lineno": getattr(node, "lineno", None),
                "col": getattr(node, "col_offset", None),
            }
        )
        cur = self.stop_event_confidence or "low"
        if self._confidence_rank(confidence) >= self._confidence_rank(cur):
            self.stop_event_confidence = confidence
            self.stop_event_confidence_reason = reason

    def _add_effect(
        self, *, target: str, op: str, confidence: str, evidence: str, node: ast.AST
    ) -> None:
        lineno = getattr(node, "lineno", None)
        col = getattr(node, "col_offset", None)
        key = (target, op, confidence, evidence, lineno, col)
        if key in self._effect_keys:
            return
        self._effect_keys.add(key)
        self.effects.append(
            {
                "target": target,
                "op": op,
                "confidence": confidence,
                "evidence": evidence,
                "lineno": lineno,
                "col": col,
            }
        )

    def _record_top_level_args(self, args: ast.arguments) -> None:
        names: list[str] = []
        for a in list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs):
            n = getattr(a, "arg", None)
            if isinstance(n, str) and n:
                names.append(n)
        for name in names:
            if name == "self":
                continue
            lowered = name.lower()
            if name == "event" or lowered.endswith("event"):
                self.event_vars.add(name)
            if (
                name in {"req", "request", "provider_request"}
                or lowered.endswith("_req")
                or ("providerrequest" in lowered)
            ):
                self.req_vars.add(name)
            if "llm_response" in lowered or "llmresponse" in lowered:
                self.llm_response_vars.add(name)
            elif name in {"response", "resp", "llm_resp"}:
                self.llm_response_vars.add(name)
                self._llm_response_vars_inferred.add(name)

    @staticmethod
    def _name_id(node: ast.AST) -> str | None:
        return node.id if isinstance(node, ast.Name) else None

    def _is_get_result_call(self, node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get_result"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in self.event_vars
        )

    def _is_result_ref(self, node: ast.AST) -> bool:
        return isinstance(node, ast.Name) and node.id in self.result_vars

    def _is_chain_attr(self, node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Attribute)
            and node.attr == "chain"
            and (
                self._is_get_result_call(node.value) or self._is_result_ref(node.value)
            )
        )

    def _handle_result_var_assign(self, tgt: ast.AST, value: ast.AST) -> None:
        if not isinstance(tgt, ast.Name) or not isinstance(tgt.id, str) or not tgt.id:
            return
        if self._is_get_result_call(value):
            self.result_vars.add(tgt.id)
        elif isinstance(value, ast.Name) and value.id in self.result_vars:
            self.result_vars.add(tgt.id)

    def _is_result_chain_expr(self, node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Attribute)
            and node.attr == "chain"
            and (
                self._is_get_result_call(node.value) or self._is_result_ref(node.value)
            )
        )

    def _handle_chain_var_assign(self, tgt: ast.AST, value: ast.AST) -> None:
        if not isinstance(tgt, ast.Name) or not isinstance(tgt.id, str) or not tgt.id:
            return
        if self._is_result_chain_expr(value):
            self.chain_vars.add(tgt.id)
        elif isinstance(value, ast.Name) and value.id in self.chain_vars:
            self.chain_vars.add(tgt.id)

    def _handle_attr_write(
        self, target: ast.Attribute, value: ast.AST, node: ast.AST
    ) -> None:
        base_name = self._name_id(target.value)

        if target.attr in {"prompt", "system_prompt"} and base_name in self.req_vars:
            self._add_effect(
                target=f"provider_request.{target.attr}",
                op="overwrite",
                confidence="high",
                evidence=f"req.{target.attr}_assign",
                node=node,
            )
            return

        if target.attr == "contexts" and base_name in self.req_vars:
            op = (
                "clear"
                if isinstance(value, ast.List) and not getattr(value, "elts", [])
                else "overwrite"
            )
            self._add_effect(
                target="provider_request.contexts",
                op=op,
                confidence="high",
                evidence="req.contexts_assign",
                node=node,
            )
            return

        if target.attr == "extra_user_content_parts" and base_name in self.req_vars:
            op = (
                "clear"
                if isinstance(value, ast.List) and not getattr(value, "elts", [])
                else "overwrite"
            )
            self._add_effect(
                target="provider_request.extra_user_content_parts",
                op=op,
                confidence="high",
                evidence="req.extra_user_content_parts_assign",
                node=node,
            )
            return

        if target.attr == "func_tool" and base_name in self.req_vars:
            self._add_effect(
                target="provider_request.func_tool",
                op="overwrite",
                confidence="high",
                evidence="req.func_tool_assign",
                node=node,
            )
            return

        if (
            isinstance(target.value, ast.Attribute)
            and target.value.attr == "func_tool"
            and self._name_id(target.value.value) in self.req_vars
        ):
            self._add_effect(
                target="provider_request.func_tool",
                op="mutate_list",
                confidence="medium",
                evidence="req.func_tool_attr_assign",
                node=node,
            )
            return

        if base_name in self.llm_response_vars and target.attr in {
            "completion_text",
            "result_chain",
            "tools_call_name",
            "tools_call_args",
        }:
            eff_target = f"llm_response.{target.attr}"
            op = "overwrite"
            if (
                target.attr in {"tools_call_name", "tools_call_args"}
                and isinstance(value, ast.List)
                and not getattr(value, "elts", [])
            ):
                op = "clear"
            confidence = (
                "medium" if base_name in self._llm_response_vars_inferred else "high"
            )
            evidence_suffix = (
                "inferred" if base_name in self._llm_response_vars_inferred else "param"
            )
            self._add_effect(
                target=eff_target,
                op=op,
                confidence=confidence,
                evidence=f"llm_response.{target.attr}_assign:{evidence_suffix}",
                node=node,
            )
            return

        if target.attr == "message_str":
            if base_name in self.event_vars:
                self._add_effect(
                    target="event.message_str",
                    op="overwrite",
                    confidence="high",
                    evidence="event.message_str_assign",
                    node=node,
                )
                return
            if (
                isinstance(target.value, ast.Attribute)
                and target.value.attr == "message_obj"
                and self._name_id(target.value.value) in self.event_vars
            ):
                self._add_effect(
                    target="event.message_str",
                    op="overwrite",
                    confidence="high",
                    evidence="event.message_obj.message_str_assign",
                    node=node,
                )
                return

        if target.attr == "chain" and (
            self._is_get_result_call(target.value) or self._is_result_ref(target.value)
        ):
            op = (
                "clear"
                if isinstance(value, ast.List) and not getattr(value, "elts", [])
                else "overwrite"
            )
            self._add_effect(
                target="result.chain",
                op=op,
                confidence="high",
                evidence="result.chain_assign",
                node=node,
            )

    def _handle_subscript_write(self, sub: ast.Subscript, node: ast.AST) -> None:
        val = sub.value
        if self._is_chain_attr(val):
            self._add_effect(
                target="result.chain",
                op="mutate_list",
                confidence="high",
                evidence="result.chain_subscript_assign",
                node=node,
            )
            return
        if isinstance(val, ast.Name) and val.id in self.chain_vars:
            self._add_effect(
                target="result.chain",
                op="mutate_list",
                confidence="high",
                evidence="result.chain_alias_subscript_assign",
                node=node,
            )

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        if self._fn_depth == 0:
            self._record_top_level_args(node.args)
        self._fn_depth += 1
        self.generic_visit(node)
        self._fn_depth -= 1

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        if self._fn_depth == 0:
            self._record_top_level_args(node.args)
        self._fn_depth += 1
        self.generic_visit(node)
        self._fn_depth -= 1

    def visit_Lambda(self, node: ast.Lambda) -> Any:
        self._fn_depth += 1
        self.generic_visit(node)
        self._fn_depth -= 1

    def visit_If(self, node: ast.If) -> Any:
        self._guard_stack.append("if")
        for item in node.body:
            self.visit(item)
        for item in node.orelse:
            self.visit(item)
        self._guard_stack.pop()

    def visit_Try(self, node: ast.Try) -> Any:
        self._guard_stack.append("try")
        for item in node.body:
            self.visit(item)
        for item in node.handlers:
            self.visit(item)
        for item in node.orelse:
            self.visit(item)
        for item in node.finalbody:
            self.visit(item)
        self._guard_stack.pop()

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> Any:
        self._guard_stack.append("except")
        for item in node.body:
            self.visit(item)
        self._guard_stack.pop()

    def visit_Call(self, node: ast.Call) -> Any:
        call_name: str | None = None
        if isinstance(node.func, ast.Attribute):
            call_name = node.func.attr
        elif isinstance(node.func, ast.Name):
            call_name = node.func.id
        if call_name:
            self.calls.add(call_name)

        if call_name == "stop_event":
            if self._fn_depth >= 2:
                self._record_stop_event(
                    confidence="low", reason="nested_callable", node=node
                )
            elif self._guard_stack:
                self._record_stop_event(
                    confidence="medium",
                    reason=f"inside_{self._guard_stack[-1]}",
                    node=node,
                )
            else:
                self._record_stop_event(
                    confidence="high", reason="unconditional", node=node
                )
            self._add_effect(
                target="stop",
                op="call",
                confidence=self.stop_event_confidence or "low",
                evidence=f"event.stop_event_call:{self.stop_event_confidence_reason or 'unknown'}",
                node=node,
            )

        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "send"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in self.event_vars
        ):
            self._add_effect(
                target="send",
                op="call",
                confidence="high",
                evidence="event.send_call",
                node=node,
            )

        if isinstance(node.func, ast.Attribute):
            method = node.func.attr
            recv = node.func.value

            list_ops_append = {"append", "insert"}
            list_ops_mutate = {"extend", "pop", "remove", "sort", "reverse"}
            list_ops_clear = {"clear"}
            list_ops = list_ops_append | list_ops_mutate | list_ops_clear

            if self._is_chain_attr(recv) and method in list_ops:
                if method in list_ops_clear:
                    op = "clear"
                elif method in list_ops_append:
                    op = "append"
                else:
                    op = "mutate_list"
                self._add_effect(
                    target="result.chain",
                    op=op,
                    confidence="high",
                    evidence=f"result.chain_call.{method}",
                    node=node,
                )

            if (
                isinstance(recv, ast.Name)
                and recv.id in self.chain_vars
                and method in list_ops
            ):
                if method in list_ops_clear:
                    op = "clear"
                elif method in list_ops_append:
                    op = "append"
                else:
                    op = "mutate_list"
                self._add_effect(
                    target="result.chain",
                    op=op,
                    confidence="high",
                    evidence=f"result.chain_alias_call.{method}",
                    node=node,
                )

            if (
                isinstance(recv, ast.Attribute)
                and isinstance(recv.value, ast.Name)
                and recv.value.id in self.req_vars
            ):
                if (
                    recv.attr in {"contexts", "extra_user_content_parts"}
                    and method in list_ops
                ):
                    if method in list_ops_clear:
                        op = "clear"
                    elif method in list_ops_append:
                        op = "append"
                    else:
                        op = "mutate_list"
                    self._add_effect(
                        target=f"provider_request.{recv.attr}",
                        op=op,
                        confidence="high",
                        evidence=f"req.{recv.attr}_call.{method}",
                        node=node,
                    )
                if recv.attr == "func_tool":
                    self._add_effect(
                        target="provider_request.func_tool",
                        op="call",
                        confidence="low",
                        evidence=f"req.func_tool_call.{method}",
                        node=node,
                    )

            if (
                isinstance(recv, ast.Attribute)
                and isinstance(recv.value, ast.Name)
                and recv.value.id in self.llm_response_vars
            ):
                if (
                    recv.attr in {"tools_call_name", "tools_call_args"}
                    and method in list_ops
                ):
                    if method in list_ops_clear:
                        op = "clear"
                    elif method in list_ops_append:
                        op = "append"
                    else:
                        op = "mutate_list"
                    self._add_effect(
                        target=f"llm_response.{recv.attr}",
                        op=op,
                        confidence="high",
                        evidence=f"llm_response.{recv.attr}_call.{method}",
                        node=node,
                    )

        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> Any:
        for tgt in node.targets:
            self._handle_result_var_assign(tgt, node.value)
            self._handle_chain_var_assign(tgt, node.value)

            if isinstance(tgt, ast.Attribute):
                self.assigns.add(tgt.attr)
                if self._is_persona_prompt_attr(tgt):
                    self.persona_prompt_overwrite = True
                self._handle_attr_write(tgt, node.value, node)
            elif isinstance(tgt, ast.Subscript):
                if self._is_persona_prompt_subscript(tgt):
                    self.persona_prompt_overwrite = True
                self._handle_subscript_write(tgt, node)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> Any:
        if isinstance(node.target, ast.Attribute):
            self.aug_assigns.add(node.target.attr)
            if self._is_persona_prompt_attr(node.target):
                self.persona_prompt_append = True

            if node.target.attr == "message_str":
                base_name = self._name_id(node.target.value)
                if base_name in self.event_vars:
                    self._add_effect(
                        target="event.message_str",
                        op="append",
                        confidence="high",
                        evidence="event.message_str_augassign",
                        node=node,
                    )
                elif (
                    isinstance(node.target.value, ast.Attribute)
                    and node.target.value.attr == "message_obj"
                    and self._name_id(node.target.value.value) in self.event_vars
                ):
                    self._add_effect(
                        target="event.message_str",
                        op="append",
                        confidence="high",
                        evidence="event.message_obj.message_str_augassign",
                        node=node,
                    )

            base_name = self._name_id(node.target.value)
            if base_name in self.req_vars and node.target.attr in {
                "prompt",
                "system_prompt",
            }:
                self._add_effect(
                    target=f"provider_request.{node.target.attr}",
                    op="append",
                    confidence="high",
                    evidence=f"req.{node.target.attr}_augassign",
                    node=node,
                )

            if node.target.attr == "chain" and (
                self._is_get_result_call(node.target.value)
                or self._is_result_ref(node.target.value)
            ):
                self._add_effect(
                    target="result.chain",
                    op="mutate_list",
                    confidence="high",
                    evidence="result.chain_augassign",
                    node=node,
                )

        elif isinstance(node.target, ast.Subscript):
            if self._is_persona_prompt_subscript(node.target):
                self.persona_prompt_append = True
            self._handle_subscript_write(node.target, node)

        self.generic_visit(node)

    def visit_Yield(self, node: ast.Yield) -> Any:
        if isinstance(node.value, ast.Call):
            fn = node.value.func
            if isinstance(fn, ast.Name) and fn.id in {
                "MessageEventResult",
                "CommandResult",
            }:
                self.yields_result = True
            if isinstance(fn, ast.Attribute) and fn.attr in {
                "MessageEventResult",
                "CommandResult",
            }:
                self.yields_result = True
        self.generic_visit(node)
