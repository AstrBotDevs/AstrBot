from __future__ import annotations

from collections import defaultdict
from typing import Any

from astrbot.core.agent.mcp_client import MCPTool
from astrbot.core.pipeline.snapshot.stages import STAGES_ORDER
from astrbot.core.pipeline.snapshot.utils import stable_id
from astrbot.core.provider.register import llm_tools
from astrbot.core.star.star import StarMetadata, star_map
from astrbot.core.star.star_handler import EventType


def _plugin_ref(meta: StarMetadata | None, fallback_name: str) -> dict[str, Any]:
    if meta and meta.name:
        return {
            "name": meta.name,
            "display_name": meta.display_name,
            "reserved": bool(meta.reserved),
            "activated": bool(meta.activated),
            "version": meta.version,
            "repo": meta.repo,
        }
    return {
        "name": fallback_name,
        "display_name": None,
        "reserved": True,
        "activated": True,
        "version": None,
        "repo": None,
    }


def _tool_origin_ref(tool: Any) -> tuple[dict[str, Any], str]:
    """
    Returns: (plugin_ref, module_path_or_origin)
    - 对本地/插件工具：优先使用 handler_module_path 映射插件
    - 对 MCPTool：使用 mcp_server_name 作为来源
    """
    mp = getattr(tool, "handler_module_path", None)
    if isinstance(mp, str) and mp:
        return _plugin_ref(star_map.get(mp), mp), mp
    if isinstance(tool, MCPTool):
        origin = f"mcp:{tool.mcp_server_name}"
        return _plugin_ref(None, origin), origin
    origin = "unknown_tool_origin"
    return _plugin_ref(None, origin), origin


def detect_command_conflicts(
    command_desc: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_cmd: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for d in command_desc:
        if not d.get("enabled"):
            continue
        cmd = str(d.get("cmd") or "").strip()
        if cmd:
            by_cmd[cmd].append(d)

    conflicts: list[dict[str, Any]] = []
    for cmd, group in by_cmd.items():
        if len(group) <= 1:
            continue
        involved = [
            {
                "plugin": item["plugin"],
                "handler": item["handler"],
                "stage": item["stage"],
                "event_type": item["event_type"],
                "priority": int(item["priority"]),
                "enabled": True,
            }
            for item in group
        ]
        conflicts.append(
            {
                "id": stable_id("command_name_conflict", cmd, str(len(group))),
                "type": "command_name_conflict",
                "severity": "warn",
                "title": f"指令名冲突: {cmd}",
                "description": f"存在 {len(group)} 个启用的指令使用相同的有效指令名 '{cmd}'。",
                "involved": involved,
                "suggestion": "请重命名其中一个指令，或禁用冲突指令。",
            }
        )

    # alias 冲突：alias 与其他指令主名/alias 重叠
    alias_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for d in command_desc:
        if not d.get("enabled"):
            continue
        for name in [d.get("cmd")] + list(d.get("aliases") or []):
            if not name:
                continue
            alias_map[str(name).strip()].append(d)

    for name, group in alias_map.items():
        if len(group) <= 1:
            continue
        involved = [
            {
                "plugin": item["plugin"],
                "handler": item["handler"],
                "stage": item["stage"],
                "event_type": item["event_type"],
                "priority": int(item["priority"]),
                "enabled": True,
            }
            for item in group
        ]
        conflicts.append(
            {
                "id": stable_id("command_alias_conflict", name, str(len(group))),
                "type": "command_alias_conflict",
                "severity": "warn",
                "title": f"指令别名重叠: {name}",
                "description": f"指令主名/别名 '{name}' 被多个启用指令同时占用，可能导致触发歧义。",
                "involved": involved,
                "suggestion": "请修改别名或重命名其中一个指令。",
            }
        )

    return conflicts


def detect_tool_name_conflicts(
    active_plugins: list[StarMetadata],
) -> list[dict[str, Any]]:
    active_modules = {p.module_path for p in active_plugins if p.module_path}

    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for tool in llm_tools.func_list:
        name = getattr(tool, "name", None)
        if not name:
            continue

        plugin_ref, origin = _tool_origin_ref(tool)
        # 仅展示本次快照 scope 内的工具：插件工具必须属于 active_modules；MCP 工具不受此限制
        if origin in active_modules or origin.startswith("mcp:"):
            by_name[str(name)].append(
                {
                    "plugin": plugin_ref,
                    "handler": {
                        "handler_full_name": "",
                        "handler_name": str(name),
                        "handler_module_path": origin,
                    },
                    "stage": "ProcessStage",
                    "event_type": EventType.OnCallingFuncToolEvent.name,
                    "priority": 0,
                    "enabled": True,
                }
            )

    conflicts: list[dict[str, Any]] = []
    for name, group in by_name.items():
        if len(group) <= 1:
            continue
        conflicts.append(
            {
                "id": stable_id("tool_name_conflict", name),
                "type": "tool_name_conflict",
                "severity": "warn",
                "title": f"工具名冲突: {name}",
                "description": "检测到多个工具使用相同名称，可能导致覆盖或调用歧义。",
                "involved": group,
                "suggestion": "请为工具使用唯一名称。",
            }
        )
    return conflicts


def detect_priority_ties(participants: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # 同一 stage/event_type 下 priority 相同且存在 stop/覆盖/发送风险 -> priority_tie_conflict
    groups: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for p in participants:
        stage = str(p.get("_stage") or "")
        et = str(p.get("meta", {}).get("event_type") or "")
        pr = int(p.get("meta", {}).get("priority") or 0)
        groups[(stage, et, pr)].append(p)

    conflicts: list[dict[str, Any]] = []
    for (stage, et, pr), items in groups.items():
        if len(items) <= 1:
            continue
        risky = []
        for p in items:
            risk_types = {r.get("type") for r in (p.get("risks") or [])}
            if risk_types & {
                "may_stop_event",
                "duplicate_send_risk",
                "may_mutate_prompt",
                "may_mutate_system_prompt",
                "may_send_directly",
            }:
                risky.append(p)
        if not risky:
            continue

        involved = [
            {
                "plugin": p["plugin"],
                "handler": p["handler"],
                "stage": stage,
                "event_type": et,
                "priority": pr,
                "enabled": bool(p.get("meta", {}).get("enabled")),
            }
            for p in items
        ]
        conflicts.append(
            {
                "id": stable_id("priority_tie_conflict", stage, et, str(pr)),
                "type": "priority_tie_conflict",
                "severity": "warn",
                "title": f"优先级并列且存在风险: {stage}/{et}/P{pr}",
                "description": "同一事件类型下多个 handler priority 相同，且包含 stop/覆盖/发送等风险，执行顺序可能不稳定。",
                "involved": involved,
                "suggestion": "请调整 priority，或避免在并列 priority 下执行 stop/覆盖/发送等高影响操作。",
            }
        )
    return conflicts


def detect_duplicate_send(participants: list[dict[str, Any]]) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    for p in participants:
        stage = str(p.get("_stage") or "")
        et = str(p.get("meta", {}).get("event_type") or "")

        # AdapterMessageEvent 在 WakingCheckStage 只展示触发条件，不代表执行点
        if stage == "WakingCheckStage" and et == EventType.AdapterMessageEvent.name:
            continue

        risk_types = {r.get("type") for r in (p.get("risks") or [])}
        if "duplicate_send_risk" not in risk_types:
            continue

        pr = int(p.get("meta", {}).get("priority") or 0)
        conflicts.append(
            {
                "id": stable_id("duplicate_send_conflict", p["id"]),
                "type": "duplicate_send_conflict",
                "severity": "warn",
                "title": "可能重复发送",
                "description": "检测到 handler 同时可能直接 send 且也可能 set_result/yield result，可能导致消息重复发送。",
                "involved": [
                    {
                        "plugin": p["plugin"],
                        "handler": p["handler"],
                        "stage": stage,
                        "event_type": et,
                        "priority": pr,
                        "enabled": bool(p.get("meta", {}).get("enabled")),
                    }
                ],
                "suggestion": "请避免同时使用 event.send 与 set_result/yield result，或在 send 后清理 result。",
            }
        )
    return conflicts


def build_llm_prompt_preview(
    participants: list[dict[str, Any]],
    llm_mutations_by_handler_full_name: dict[str, dict[str, str]],
    persona_prompt_modifiers: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    injected_by: list[dict[str, Any]] = []

    for p in participants:
        stage = str(p.get("_stage") or "")
        et = str(p.get("meta", {}).get("event_type") or "")

        # prompt/system_prompt are only meaningful at the LLM request stage,
        # but persona_prompt mutations may happen earlier in ProcessStage (e.g. AdapterMessageEvent).
        if stage != "ProcessStage":
            continue

        handler_full_name = p.get("handler", {}).get("handler_full_name") or ""
        mutations = llm_mutations_by_handler_full_name.get(handler_full_name) or {}

        # prompt + system_prompt: keep existing strict scope
        if et == EventType.OnLLMRequestEvent.name:
            for field in ("prompt", "system_prompt"):
                m = mutations.get(field)
                if m in {"append", "overwrite"}:
                    injected_by.append(
                        {
                            "plugin": p["plugin"],
                            "handler": p["handler"],
                            "priority": int(p.get("meta", {}).get("priority") or 0),
                            "mutation": "append" if m == "append" else "overwrite",
                            "field": field,
                            "source_type": "llm_request",
                        }
                    )

        # persona_prompt: allow all ProcessStage events
        m = mutations.get("persona_prompt")
        if m in {"append", "overwrite"}:
            injected_by.append(
                {
                    "plugin": p["plugin"],
                    "handler": p["handler"],
                    "priority": int(p.get("meta", {}).get("priority") or 0),
                    "mutation": "append" if m == "append" else "overwrite",
                    "field": "persona_prompt",
                    "source_type": "persona",
                }
            )

    for item in persona_prompt_modifiers or []:
        if not isinstance(item, dict):
            continue
        injected_by.append(item)

    if not injected_by:
        return None

    # 静态快照不模拟具体消息，因此不生成最终文本，仅展示注入链路
    return {
        "prompt": "",
        "system_prompt": "",
        "contexts": {
            "present": False,
            "source": "unknown",
            "note": "静态快照不模拟运行时 contexts，仅展示注入链路。",
        },
        "injected_by": injected_by,
    }


def detect_prompt_overwrite_conflicts(
    llm_preview: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not llm_preview:
        return []
    injected = llm_preview.get("injected_by") or []

    conflicts: list[dict[str, Any]] = []
    for field, conflict_type in (
        ("system_prompt", "system_prompt_overwrite_conflict"),
        ("prompt", "prompt_overwrite_conflict"),
    ):
        overwriters = [
            x
            for x in injected
            if x.get("field") == field and x.get("mutation") == "overwrite"
        ]
        appenders = [
            x
            for x in injected
            if x.get("field") == field and x.get("mutation") == "append"
        ]
        if len(overwriters) <= 1 and not (overwriters and appenders):
            continue

        involved = [
            {
                "plugin": x.get("plugin") or {},
                "handler": x.get("handler") or {},
                "stage": "ProcessStage",
                "event_type": EventType.OnLLMRequestEvent.name,
                "priority": int(x.get("priority") or 0),
                "enabled": True,
            }
            for x in overwriters + appenders
        ]
        severity = "error" if len(overwriters) > 1 else "warn"
        conflicts.append(
            {
                "id": stable_id(
                    conflict_type, str(len(overwriters)), str(len(appenders))
                ),
                "type": conflict_type,
                "severity": severity,
                "title": f"提示词覆盖冲突: {field}",
                "description": "检测到多个 handler 可能覆盖/拼接同一字段，可能导致提示词内容不可预测。",
                "involved": involved,
                "suggestion": "请避免多个插件对同一字段做 overwrite，或统一约定仅追加。",
            }
        )
    return conflicts


def _detect_result_chain_mutation_risk(
    participants: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    冲突类型：result_chain_mutation_risk

    基于静态 snapshot 的 participants[].effects 进行聚合，不执行插件代码。
    聚合维度：同 stage + 同 event_type 下，存在多个参与者对 result.chain 做高/中影响操作。
    """
    # effects schema: see `astrbot/core/pipeline/snapshot/ast_risk_scanner.py`
    high_impact_ops = {"clear", "overwrite"}
    mid_impact_ops = {"mutate_list", "append"}

    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

    for p in participants:
        if not bool(p.get("meta", {}).get("enabled")):
            continue

        stage = str(p.get("_stage") or "")
        et = str(p.get("meta", {}).get("event_type") or "")

        effects = p.get("effects") or []
        if not isinstance(effects, list) or not effects:
            continue

        chain_effects = [
            e
            for e in effects
            if isinstance(e, dict)
            and e.get("target") == "result.chain"
            and str(e.get("op") or "") in (high_impact_ops | mid_impact_ops)
        ]
        if not chain_effects:
            continue

        ops = {str(e.get("op") or "") for e in chain_effects}
        impact: str | None = None
        if ops & high_impact_ops:
            impact = "high"
        elif ops & mid_impact_ops:
            impact = "mid"

        if impact is None:
            continue

        groups[(stage, et)].append(
            {
                "participant": p,
                "impact": impact,
                "ops": sorted(ops),
                "effects": chain_effects,
            }
        )

    conflicts: list[dict[str, Any]] = []
    for (stage, et), items in groups.items():
        if len(items) <= 1:
            continue

        high_items = [x for x in items if x["impact"] == "high"]
        mid_items = [x for x in items if x["impact"] == "mid"]

        severity: str | None = None
        if len(high_items) >= 2 or (len(high_items) >= 1 and len(mid_items) >= 1):
            severity = "error"
        elif len(mid_items) >= 2:
            severity = "warn"

        if severity is None:
            continue

        involved_items = sorted(
            items,
            key=lambda x: (
                -int(x["participant"].get("meta", {}).get("priority") or 0),
                str(x["participant"].get("handler", {}).get("handler_full_name") or ""),
            ),
        )

        involved = [
            {
                "participant_id": x["participant"].get("id") or "",
                "plugin": x["participant"].get("plugin") or {},
                "handler": x["participant"].get("handler") or {},
                "stage": stage,
                "event_type": et,
                "priority": int(x["participant"].get("meta", {}).get("priority") or 0),
                "enabled": True,
                "effects": x.get("effects") or [],
            }
            for x in involved_items
        ]

        high_ops = sorted({op for x in high_items for op in (x.get("ops") or [])})
        mid_ops = sorted({op for x in mid_items for op in (x.get("ops") or [])})
        op_summary_parts: list[str] = []
        if high_ops:
            op_summary_parts.append(f"高影响操作({', '.join(high_ops)})")
        if mid_ops:
            op_summary_parts.append(f"中影响操作({', '.join(mid_ops)})")
        op_summary = (
            " / ".join(op_summary_parts)
            if op_summary_parts
            else "对 result.chain 的修改"
        )

        title = f"result.chain 改写风险: {stage}/{et}"
        if severity == "error":
            description = (
                f"同一 stage/event_type 内检测到多个参与者可能同时对 result.chain 执行 {op_summary}。"
                "这会导致最终 RespondStage 实际发送的消息链内容不可预测（顺序依赖/互相覆盖/被清空）。"
            )
        else:
            description = (
                f"同一 stage/event_type 内检测到多个参与者可能对 result.chain 执行 {op_summary}。"
                "由于执行顺序依赖，可能出现覆盖或结果不稳定。"
            )

        handler_ids = sorted(
            {
                str(x["participant"].get("id") or "")
                for x in items
                if str(x["participant"].get("id") or "")
            }
        )
        conflicts.append(
            {
                "id": stable_id(
                    "result_chain_mutation_risk",
                    stage,
                    et,
                    severity,
                    ",".join(handler_ids),
                ),
                "type": "result_chain_mutation_risk",
                "severity": severity,
                "title": title,
                "description": description,
                "involved": involved,
                "references": [{"kind": "stage", "id": "RespondStage"}],
                "suggestion": "建议：调整冲突插件/handler 的 priority 以固定顺序；或禁用其中一个；插件实现侧尽量避免 clear/overwrite result.chain，优先采用 append/extend 等可组合方式。",
            }
        )

    return conflicts


def detect_stop_interception(
    participants: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_stage_event: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for p in participants:
        stage = str(p.get("_stage") or "")
        et = str(p.get("meta", {}).get("event_type") or "")
        by_stage_event[(stage, et)].append(p)

    for key in list(by_stage_event.keys()):
        by_stage_event[key] = sorted(
            by_stage_event[key],
            key=lambda p: (
                -int(p.get("meta", {}).get("priority") or 0),
                str(p.get("handler", {}).get("handler_full_name") or ""),
            ),
        )

    conflicts: list[dict[str, Any]] = []
    for p in participants:
        stage = str(p.get("_stage") or "")
        et = str(p.get("meta", {}).get("event_type") or "")

        # AdapterMessageEvent 在 WakingCheckStage 只展示触发条件，不代表执行点
        if stage == "WakingCheckStage" and et == EventType.AdapterMessageEvent.name:
            continue

        risk_types = {r.get("type") for r in (p.get("risks") or [])}
        if "may_stop_event" not in risk_types:
            continue

        stop_risk = (
            next(
                (
                    r
                    for r in (p.get("risks") or [])
                    if r.get("type") == "may_stop_event"
                ),
                None,
            )
            or {}
        )
        confidence = stop_risk.get("confidence")
        confidence_reason = stop_risk.get("confidence_reason")

        chain = by_stage_event.get((stage, et)) or []
        idx = next((i for i, x in enumerate(chain) if x.get("id") == p.get("id")), None)
        subsequent = chain[idx + 1 :] if isinstance(idx, int) else []
        subsequent_handler_ids = [x.get("id") for x in subsequent if x.get("id")]

        downstream_stages: list[str] = []
        if stage in STAGES_ORDER:
            start = STAGES_ORDER.index(stage)
            downstream_stages = STAGES_ORDER[start + 1 :]

        references = [{"kind": "handler", "id": p.get("id") or ""}]
        references.extend(
            {"kind": "handler", "id": hid} for hid in subsequent_handler_ids
        )
        references.extend({"kind": "stage", "id": sid} for sid in downstream_stages)

        description_parts: list[str] = []
        description_parts.append("检测到 handler 可能 stop_event。")
        if subsequent_handler_ids:
            description_parts.append(
                "同 stage/event_type 内的后续 handler 可能被拦截。"
            )
        if downstream_stages:
            description_parts.append("下游 stages 也可能不执行。")
        description_parts.append("静态分析无法证明 stop 一定发生，也无法确定发生时机。")

        conflicts.append(
            {
                "id": stable_id("stop_interception_conflict", p.get("id") or ""),
                "type": "stop_interception_conflict",
                "severity": "warn",
                "title": "Stop 可能拦截后续处理",
                "description": " ".join(description_parts),
                "involved": [
                    {
                        "plugin": p["plugin"],
                        "handler": p["handler"],
                        "stage": stage,
                        "event_type": et,
                        "priority": int(p.get("meta", {}).get("priority") or 0),
                        "enabled": bool(p.get("meta", {}).get("enabled")),
                    }
                ],
                "references": references,
                "impact": {
                    "same_stage_following_handlers": subsequent_handler_ids,
                    "downstream_stages": downstream_stages,
                },
                "confidence": confidence,
                "confidence_reason": confidence_reason,
                "note": "confidence 为静态 AST 推断：high=直线路径调用，medium=位于 if/try/except 等分支内，low=更不确定（如嵌套可调用/无法证明执行）。",
                "suggestion": "如需 stop，请确保不影响关键后续阶段，或通过更明确的条件控制 stop。",
            }
        )

    conflicts.extend(_detect_result_chain_mutation_risk(participants))
    return conflicts


__all__ = [
    "build_llm_prompt_preview",
    "detect_command_conflicts",
    "detect_duplicate_send",
    "detect_priority_ties",
    "detect_prompt_overwrite_conflicts",
    "detect_stop_interception",
    "detect_tool_name_conflicts",
]
