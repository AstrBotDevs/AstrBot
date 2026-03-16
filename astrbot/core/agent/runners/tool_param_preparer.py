import re
import typing as T
from dataclasses import dataclass

from astrbot import logger


@dataclass(slots=True)
class PreparedToolCall:
    valid_params: dict[str, T.Any]
    ignored_params: set[str]
    error: str | None = None


class ToolParamPreparer:
    @staticmethod
    def _normalize_tool_param_name_for_matching(name: str) -> str:
        normalized = name.replace("-", "_")
        normalized = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", normalized)
        normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", normalized)
        return normalized.lower()

    @staticmethod
    def _is_missing_like(value: T.Any) -> bool:
        if value is None:
            return True
        if isinstance(value, str):
            return not value.strip()
        return False

    @staticmethod
    def _schema_type_tokens(schema: dict[str, T.Any] | None) -> set[str]:
        if not isinstance(schema, dict):
            return set()
        type_val = schema.get("type")
        if isinstance(type_val, str):
            return {type_val}
        if isinstance(type_val, list):
            return {str(t) for t in type_val if isinstance(t, str)}
        return set()

    @classmethod
    def _coerce_tool_value_by_schema(
        cls,
        *,
        value: T.Any,
        schema: dict[str, T.Any] | None,
    ) -> T.Any:
        tokens = cls._schema_type_tokens(schema)
        if not tokens:
            return value

        if "boolean" in tokens:
            if isinstance(value, bool):
                return value
            if isinstance(value, int | float):
                return bool(value)
            if isinstance(value, str):
                lowered = value.strip().lower()
                if lowered in {"true", "1", "yes", "y", "on"}:
                    return True
                if lowered in {"false", "0", "no", "n", "off", ""}:
                    return False

        if "integer" in tokens:
            if isinstance(value, bool):
                return int(value)
            if isinstance(value, int):
                return value
            if isinstance(value, float) and value.is_integer():
                return int(value)
            if isinstance(value, str):
                stripped = value.strip()
                if re.fullmatch(r"[+-]?\d+", stripped):
                    try:
                        return int(stripped)
                    except ValueError:
                        pass

        if "number" in tokens:
            if isinstance(value, int | float) and not isinstance(value, bool):
                return value
            if isinstance(value, str):
                stripped = value.strip()
                if stripped:
                    try:
                        return float(stripped)
                    except ValueError:
                        pass

        if "string" in tokens and not isinstance(value, str):
            if isinstance(value, bool | int | float):
                return str(value)

        return value

    @classmethod
    def _coerce_tool_params_by_schema(
        cls,
        *,
        params: dict[str, T.Any],
        params_schema: dict[str, T.Any] | None,
    ) -> tuple[dict[str, T.Any], dict[str, tuple[T.Any, T.Any]]]:
        if not isinstance(params_schema, dict):
            return params, {}
        properties = params_schema.get("properties")
        if not isinstance(properties, dict):
            return params, {}

        coerced_params = dict(params)
        changed: dict[str, tuple[T.Any, T.Any]] = {}
        for key, value in params.items():
            schema = properties.get(key)
            if not isinstance(schema, dict):
                continue
            coerced = cls._coerce_tool_value_by_schema(value=value, schema=schema)
            if coerced is not value and coerced != value:
                changed[key] = (value, coerced)
                coerced_params[key] = coerced
        return coerced_params, changed

    @classmethod
    def _find_missing_required_tool_params(
        cls,
        *,
        tool: T.Any,
        provided_params: dict[str, T.Any],
    ) -> list[str]:
        params_schema = getattr(tool, "parameters", None)
        if not isinstance(params_schema, dict):
            return []
        required = params_schema.get("required")
        if not isinstance(required, list):
            return []

        missing: list[str] = []
        for field_name in required:
            if not isinstance(field_name, str):
                continue
            if field_name not in provided_params:
                missing.append(field_name)
                continue
            value = provided_params.get(field_name)
            if cls._is_missing_like(value):
                missing.append(field_name)
        return missing

    @classmethod
    def _validate_anyof_oneof_contract(
        cls,
        *,
        tool: T.Any,
        provided_params: dict[str, T.Any],
    ) -> str | None:
        params_schema = getattr(tool, "parameters", None)
        if not isinstance(params_schema, dict):
            return None

        def _extract_required_groups(key: str) -> list[list[str]]:
            groups_raw = params_schema.get(key)
            if not isinstance(groups_raw, list):
                return []
            groups: list[list[str]] = []
            for item in groups_raw:
                if not isinstance(item, dict):
                    continue
                req = item.get("required")
                if not isinstance(req, list):
                    continue
                normalized = [f for f in req if isinstance(f, str) and f]
                if normalized:
                    groups.append(normalized)
            return groups

        def _is_group_satisfied(group: list[str]) -> bool:
            for field in group:
                if field not in provided_params:
                    return False
                if cls._is_missing_like(provided_params.get(field)):
                    return False
            return True

        anyof_groups = _extract_required_groups("anyOf")
        if anyof_groups and not any(_is_group_satisfied(g) for g in anyof_groups):
            group_text = " or ".join("[" + ", ".join(group) + "]" for group in anyof_groups)
            return (
                "error: Argument contract violation (anyOf). "
                f"At least one argument group is required: {group_text}."
            )

        oneof_groups = _extract_required_groups("oneOf")
        if oneof_groups:
            satisfied = sum(1 for g in oneof_groups if _is_group_satisfied(g))
            if satisfied != 1:
                group_text = " | ".join("[" + ", ".join(group) + "]" for group in oneof_groups)
                return (
                    "error: Argument contract violation (oneOf). "
                    "Exactly one argument group must be provided. "
                    f"Available groups: {group_text}."
                )

        return None

    @classmethod
    def _build_normalized_expected_param_map(
        cls,
        *,
        expected_param_order: tuple[str, ...],
    ) -> dict[str, str]:
        normalized_expected: dict[str, str] = {}
        for expected in expected_param_order:
            normalized_key = cls._normalize_tool_param_name_for_matching(expected)
            normalized_expected.setdefault(normalized_key, expected)
        return normalized_expected

    def _map_raw_to_valid_params(
        self,
        *,
        tool_name: str,
        raw_args: dict[str, T.Any],
        expected_params: set[str],
        normalized_expected_params: dict[str, str],
    ) -> tuple[dict[str, T.Any], dict[str, str]]:
        valid_params: dict[str, T.Any] = {}
        alias_mapped_params: dict[str, str] = {}

        if not expected_params:
            return dict(raw_args), alias_mapped_params

        for raw_key, value in raw_args.items():
            if raw_key in expected_params:
                # Exact schema key always takes precedence.
                valid_params[raw_key] = value
                continue

            normalized_key = self._normalize_tool_param_name_for_matching(raw_key)
            canonical_key = normalized_expected_params.get(normalized_key)
            if canonical_key and canonical_key not in valid_params:
                valid_params[canonical_key] = value
                alias_mapped_params[raw_key] = canonical_key

        if alias_mapped_params:
            logger.info("工具 %s 参数名称已自动映射: %s", tool_name, alias_mapped_params)

        return valid_params, alias_mapped_params

    def _compute_ignored_params(
        self,
        *,
        expected_params: set[str],
        raw_args: dict[str, T.Any],
        valid_params: dict[str, T.Any],
        tool_name: str,
    ) -> set[str]:
        if not expected_params:
            return set()

        normalized_valid_keys = {
            self._normalize_tool_param_name_for_matching(key) for key in valid_params
        }
        ignored = set(raw_args.keys()) - set(valid_params.keys())
        ignored = {
            key
            for key in ignored
            if self._normalize_tool_param_name_for_matching(key)
            not in normalized_valid_keys
        }

        if ignored:
            logger.warning("工具 %s 忽略非期望参数: %s", tool_name, ignored)
        return ignored

    def _validate_contract(
        self,
        *,
        tool: T.Any,
        tool_name: str,
        raw_args: dict[str, T.Any],
        provided_params: dict[str, T.Any],
    ) -> str | None:
        missing_required = self._find_missing_required_tool_params(
            tool=tool,
            provided_params=provided_params,
        )
        if missing_required:
            missing_text = ", ".join(missing_required)
            logger.warning(
                "工具 %s 缺少必填参数: %s。原始参数: %s",
                tool_name,
                missing_text,
                raw_args,
            )
            return (
                "error: Missing required tool arguments: "
                f"{missing_text}. "
                "Please call this tool again with all required arguments."
            )

        contract_error = self._validate_anyof_oneof_contract(
            tool=tool,
            provided_params=provided_params,
        )
        if contract_error:
            logger.warning("工具 %s 参数契约校验失败: %s", tool_name, contract_error)
            return contract_error
        return None

    def prepare(
        self,
        *,
        tool: T.Any,
        tool_name: str,
        raw_args: dict[str, T.Any],
    ) -> PreparedToolCall:
        if not tool.handler:
            return PreparedToolCall(valid_params=raw_args, ignored_params=set())

        params_schema = tool.parameters if isinstance(tool.parameters, dict) else None
        properties = (params_schema or {}).get("properties") or {}
        expected_param_order = tuple(properties.keys())
        expected_params = set(expected_param_order)
        normalized_expected_params = self._build_normalized_expected_param_map(
            expected_param_order=expected_param_order
        )

        valid_params, _ = self._map_raw_to_valid_params(
            tool_name=tool_name,
            raw_args=raw_args,
            expected_params=expected_params,
            normalized_expected_params=normalized_expected_params,
        )

        valid_params, changed_types = self._coerce_tool_params_by_schema(
            params=valid_params,
            params_schema=params_schema,
        )
        if changed_types:
            logger.info(
                "工具 %s 参数类型已自动纠正: %s",
                tool_name,
                {k: {"from": repr(v[0]), "to": repr(v[1])} for k, v in changed_types.items()},
            )

        ignored_params = self._compute_ignored_params(
            expected_params=expected_params,
            raw_args=raw_args,
            valid_params=valid_params,
            tool_name=tool_name,
        )

        if expected_params and raw_args and not valid_params:
            return PreparedToolCall(
                valid_params={},
                ignored_params=ignored_params,
                error=(
                    "error: No compatible arguments for this tool. "
                    f"Provided arguments={sorted(raw_args.keys())}. "
                    "This may indicate a wrong tool selection; "
                    "please re-check tool name and argument schema."
                ),
            )

        contract_error = self._validate_contract(
            tool=tool,
            tool_name=tool_name,
            raw_args=raw_args,
            provided_params=valid_params,
        )
        if contract_error:
            return PreparedToolCall(
                valid_params={},
                ignored_params=ignored_params,
                error=contract_error,
            )

        return PreparedToolCall(
            valid_params=valid_params,
            ignored_params=ignored_params,
            error=None,
        )
