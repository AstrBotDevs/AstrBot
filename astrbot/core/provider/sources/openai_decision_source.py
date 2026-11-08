"""Native OpenAI-compatible Decisions transport, independent of chat APIs."""

from __future__ import annotations

import asyncio
import copy
import json
import math
import random
from collections.abc import Mapping
from dataclasses import replace
from types import MappingProxyType
from typing import Any

import httpx

from ..entities import (
    DecisionAnswer,
    DecisionBooleanAnswer,
    DecisionBooleanQuestion,
    DecisionChoiceAnswer,
    DecisionChoiceQuestion,
    DecisionContent,
    DecisionError,
    DecisionInput,
    DecisionQuestion,
    DecisionRefusalAnswer,
    DecisionResult,
    DecisionScoreAnswer,
    DecisionScoreQuestion,
    DecisionState,
    DecisionUsage,
    ProviderType,
)
from ..provider import DecisionProvider
from ..register import register_provider_adapter
from .request_retry import retry_provider_request


class _DecisionTransportError(DecisionError, ConnectionError):
    """A safe network error recognized by the shared retry policy."""


def _content(parts: Any, *, allowed: set[str], question: bool = False) -> None:
    """Validate native content without modifying or logging caller data.

    Args:
        parts: Native text or content array.
        allowed: Content types accepted at this location.
        question: Whether prompt cache breakpoints must be rejected.

    Raises:
        ValueError: The content cannot be represented by the Decisions protocol.
    """
    if isinstance(parts, str):
        return
    if not isinstance(parts, list) or (question and not parts):
        raise ValueError("Decision content must be text or a content array")
    for part in parts:
        if not isinstance(part, dict) or part.get("type") not in allowed:
            raise ValueError("Unsupported decision content type")
        kind = part["type"]
        if "prompt_cache_breakpoint" in part:
            breakpoint = part["prompt_cache_breakpoint"]
            if question or kind not in {"input_text", "input_image"}:
                raise ValueError("Cache breakpoints are not allowed in this content")
            if breakpoint is not None and (
                not isinstance(breakpoint, dict)
                or set(breakpoint) - {"mode"}
                or breakpoint.get("mode", "explicit") != "explicit"
            ):
                raise ValueError("Invalid explicit cache breakpoint")
        if kind in {"input_text", "output_text", "refusal"}:
            field = "refusal" if kind == "refusal" else "text"
            if not isinstance(part.get(field), str):
                raise ValueError("Decision text content requires a string")
        elif kind == "input_image":
            image = part.get("image_url")
            if not isinstance(image, str) or not image.startswith(
                ("http://", "https://", "data:image/")
            ):
                raise ValueError("Decision images require an HTTP(S) or image data URL")
            if part.get("detail") not in {None, "auto", "low", "high", "original"}:
                raise ValueError("Invalid decision image detail")
        elif kind == "input_json":
            data = part.get("data")
            if not isinstance(data, dict) and not (
                isinstance(data, list) and all(isinstance(v, dict) for v in data)
            ):
                raise ValueError(
                    "Decision JSON content requires an object or object array"
                )
            try:
                encoded = json.dumps(
                    data, ensure_ascii=False, allow_nan=False, separators=(",", ":")
                )
            except (TypeError, ValueError, RecursionError):
                raise ValueError(
                    "Decision JSON content must contain valid JSON"
                ) from None
            if len(encoded.encode("utf-8")) > 256 * 1024:
                raise ValueError("Decision JSON content exceeds 256 KiB")
            stack = [(data, 1)]
            values = 0
            while stack:
                value, depth = stack.pop()
                values += 1
                if values > 10000 or depth > 32:
                    raise ValueError("Decision JSON content exceeds structural limits")
                if isinstance(value, (dict, list)):
                    children = value.values() if isinstance(value, dict) else value
                    stack.extend(
                        (child, depth + isinstance(child, (dict, list)))
                        for child in children
                    )


def _usage(body: Any) -> DecisionUsage | None:
    """Decode optional counts while rejecting malformed reported usage.

    Args:
        body: Decoded endpoint response, including error responses.

    Returns:
        Reported usage, preserving missing counts and actual zero values.

    Raises:
        DecisionError: A reported count is not a nonnegative integer.
    """
    raw = body.get("usage") if isinstance(body, dict) else None
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise DecisionError("Decisions endpoint returned invalid usage")
    fields = {
        key: raw.get(key) for key in ("input_tokens", "output_tokens", "total_tokens")
    }
    for nested, names in (
        ("input_tokens_details", ("cached_tokens", "cache_write_tokens")),
        ("output_tokens_details", ("reasoning_tokens",)),
    ):
        details = raw.get(nested)
        if details is not None and not isinstance(details, dict):
            raise DecisionError("Decisions endpoint returned invalid usage details")
        fields.update({key: details.get(key) if details else None for key in names})
    if any(
        value is not None and (type(value) is not int or value < 0)
        for value in fields.values()
    ):
        raise DecisionError("Decisions endpoint returned invalid usage counts")
    return DecisionUsage(**fields)


@register_provider_adapter(
    "openai_decision",
    "OpenAI-compatible Decisions API",
    provider_type=ProviderType.DECISION,
)
class OpenAIDecisionProvider(DecisionProvider):
    """Native decisions with configurable endpoints and request-local metadata."""

    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(
            copy.deepcopy(provider_config), copy.deepcopy(provider_settings)
        )
        config = self.provider_config
        self.base_url = str(
            config.get("api_base") or "https://api.openai.com/v1"
        ).rstrip("/")
        try:
            url = httpx.URL(self.base_url)
        except (httpx.InvalidURL, ValueError):
            raise ValueError("Decision api_base must be an HTTP(S) URL") from None
        if (
            url.scheme not in {"http", "https"}
            or not url.host
            or url.query
            or url.fragment
            or url.userinfo
        ):
            raise ValueError(
                "Decision api_base must be an HTTP(S) URL without credentials or query"
            )
        keys = config.get("key", "")
        if isinstance(keys, str):
            keys = [keys]
        if not isinstance(keys, list) or any(not isinstance(k, str) for k in keys):
            raise ValueError("Decision API key must be a string or a list of strings")
        self.keys = tuple(k for k in keys if k)
        self.timeout = float(config.get("timeout", 30))
        self.total_timeout = float(config.get("total_timeout", 60))
        self.max_concurrency = int(config.get("max_concurrency", 4))
        if (
            not all(
                math.isfinite(v) and v > 0 for v in (self.timeout, self.total_timeout)
            )
            or self.max_concurrency < 1
        ):
            raise ValueError("Decision timeouts and max_concurrency must be positive")
        extra = config.get("custom_extra_body") or {}
        if not isinstance(extra, dict):
            raise ValueError("Decision custom_extra_body must be an object")
        if set(extra) & {"model", "input", "questions", "stream"}:
            raise ValueError(
                "Decision custom_extra_body cannot override native request fields"
            )
        self.extra_body = copy.deepcopy(extra)
        self.request_semaphore = asyncio.Semaphore(self.max_concurrency)
        self.client = httpx.AsyncClient(
            timeout=self.timeout,
            proxy=str(config.get("proxy") or "").strip() or None,
            transport=transport,
        )
        self._closed = False
        self.set_model(str(config.get("model") or "").strip())

    async def _request(
        self,
        method: str,
        path: str,
        payload: dict | None,
        retries: int,
        attempts: list[DecisionUsage | None],
    ) -> tuple[Any, httpx.Response]:
        """Send a bounded request with safe retry errors.

        Args:
            method: HTTP method.
            path: Native endpoint path relative to the configured API base.
            payload: Request JSON, or None for model discovery.
            retries: Number of additional attempts.
            attempts: Request-local usage observations for attempted requests.

        Returns:
            Decoded JSON and response metadata.

        Raises:
            DecisionError: Transport, deadline, status, or JSON errors.
        """
        if self._closed:
            raise DecisionError("Decisions provider is closed")
        if type(retries) is not int or retries < 0:
            raise ValueError("request_max_retries must be a nonnegative integer")
        model = payload["model"] if payload is not None else self.get_model()

        async def send() -> tuple[Any, httpx.Response]:
            if self._closed:
                raise DecisionError("Decisions provider is closed")
            headers = httpx.Headers(self.request_headers)
            if self.keys:
                headers["Authorization"] = f"Bearer {random.choice(self.keys)}"
            attempts.append(None)
            try:
                response = await self.client.request(
                    method,
                    f"{self.base_url}/{path}",
                    json=payload,
                    headers=headers,
                )
            except httpx.TimeoutException:
                raise _DecisionTransportError("Decisions attempt timed out") from None
            except httpx.RequestError:
                raise _DecisionTransportError("Decisions transport failed") from None
            try:
                body = response.json()
            except (ValueError, UnicodeDecodeError):
                if response.is_error:
                    raise DecisionError(
                        f"Decisions endpoint returned HTTP {response.status_code}",
                        status_code=response.status_code,
                    ) from None
                raise DecisionError(
                    "Decisions endpoint returned invalid JSON"
                ) from None
            usage = _usage(body)
            attempts[-1] = usage
            if not response.is_success:
                raise DecisionError(
                    f"Decisions endpoint returned HTTP {response.status_code}",
                    status_code=response.status_code,
                    usage=usage,
                )
            return body, response

        async def bounded() -> tuple[Any, httpx.Response]:
            async with self.request_semaphore:
                return await retry_provider_request(
                    "OpenAI Decisions", send, max_attempts=retries + 1
                )

        try:
            return await asyncio.wait_for(bounded(), timeout=self.total_timeout)
        except TimeoutError:
            raise DecisionError(
                "Decisions total request timed out",
                attempt_usages=tuple(attempts),
                model=model,
            ) from None
        except DecisionError as error:
            error.attempt_usages = tuple(attempts)
            error.model = model
            raise

    async def get_models(self) -> list[str]:
        body, _ = await self._request("GET", "models", None, 0, [])
        if not isinstance(body, dict) or not isinstance(body.get("data"), list):
            raise DecisionError("Decisions model directory returned invalid data")
        return sorted(
            {
                entry["id"]
                for entry in body["data"]
                if isinstance(entry, dict)
                and isinstance(entry.get("id"), str)
                and entry["id"].strip()
            }
        )

    async def ask(
        self,
        questions: Mapping[str, DecisionQuestion],
        state: DecisionState | None = None,
        *,
        request_max_retries: int = 0,
    ) -> DecisionResult:
        """Evaluate native predicates, choices, and scores in one request.

        Args:
            questions: Named questions with textual or explicit multimodal instructions.
            state: Text, business JSON, or explicitly wrapped native input items.
            request_max_retries: Additional transport or retryable HTTP attempts.

        Returns:
            Read-only validated answers and request-specific token usage.

        Raises:
            ValueError: Input or questions violate the native protocol.
            DecisionError: Request fails or the response cannot be validated.
        """
        if self._closed:
            raise DecisionError("Decisions provider is closed")
        model = self.get_model()
        if not model:
            raise ValueError("Decisions ask requires a model")
        if not isinstance(questions, Mapping) or not 1 <= len(questions) <= 400:
            raise ValueError("Decisions requires 1 to 400 questions")
        questions = dict(questions)
        payload_questions = []
        for name, question in questions.items():
            if not isinstance(name, str):
                raise ValueError("Decision question names must be strings")
            if not isinstance(
                question,
                (
                    DecisionBooleanQuestion,
                    DecisionChoiceQuestion,
                    DecisionScoreQuestion,
                ),
            ):
                raise ValueError("Unsupported decision question")
            instructions = question.instructions
            if isinstance(instructions, DecisionContent):
                instructions = copy.deepcopy(instructions.parts)
                _content(
                    instructions,
                    allowed={"input_text", "input_image", "input_json"},
                    question=True,
                )
            elif not isinstance(instructions, str):
                raise ValueError(
                    "Decision instructions must be text or DecisionContent"
                )
            item = {"name": name, "instructions": instructions}
            if isinstance(question, DecisionChoiceQuestion):
                if (
                    not isinstance(question.criteria, Mapping)
                    or not 2 <= len(question.criteria) <= 255
                    or any(
                        type(key) not in {str, bool} or not isinstance(value, str)
                        for key, value in question.criteria.items()
                    )
                ):
                    raise ValueError(
                        "Decision choices require 2 to 255 string or boolean values with text descriptions"
                    )
                question = replace(question, criteria=dict(question.criteria))
                questions[name] = question
                item.update(
                    type="choice",
                    choices=[
                        {"value": key, "description": value}
                        for key, value in question.criteria.items()
                    ],
                )
            elif isinstance(question, DecisionScoreQuestion):
                if (
                    not isinstance(question.criteria, list)
                    or not 2 <= len(question.criteria) <= 10
                    or any(not isinstance(v, str) for v in question.criteria)
                ):
                    raise ValueError("Decision scores require 2 to 10 text levels")
                question = replace(question, criteria=list(question.criteria))
                questions[name] = question
                item.update(
                    type="score",
                    levels=[{"label": value} for value in question.criteria],
                )
            else:
                item["type"] = "predicate"
            payload_questions.append(item)

        if isinstance(state, DecisionInput):
            native_input = copy.deepcopy(state.items)
            if not isinstance(native_input, (str, list)):
                raise ValueError("DecisionInput requires text or native items")
        elif state is None or isinstance(state, str):
            native_input = "" if state is None else state
        elif isinstance(state, (dict, list)):
            data = copy.deepcopy(state)
            if isinstance(data, list) and any(
                not isinstance(value, dict) for value in data
            ):
                data = {"state": data}
            native_input = [
                {"role": "user", "content": [{"type": "input_json", "data": data}]}
            ]
        else:
            raise ValueError("Unsupported decision state")
        if isinstance(native_input, list):
            calls: dict[str, str] = {}
            outputs: set[str] = set()
            for item in native_input:
                if not isinstance(item, dict):
                    raise ValueError("Native decision input items must be objects")
                kind = item.get("type", "message")
                if kind == "message":
                    role = item.get("role", "user")
                    allowed = {"input_text"}
                    if role == "user":
                        allowed |= {"input_image", "input_json"}
                    elif role == "assistant":
                        allowed = {"output_text", "refusal"}
                    elif role not in {"system", "developer"}:
                        raise ValueError("Unsupported decision message role")
                    _content(item.get("content"), allowed=allowed)
                elif kind in {"function_call", "custom_tool_call"}:
                    call_id = item.get("call_id")
                    if (
                        not isinstance(call_id, str)
                        or not call_id
                        or call_id in calls
                        or not isinstance(item.get("name"), str)
                    ):
                        raise ValueError("Invalid or duplicate decision tool call")
                    if not isinstance(
                        item.get("arguments" if kind == "function_call" else "input"),
                        str,
                    ):
                        raise ValueError("Decision tool call requires string input")
                    calls[call_id] = f"{kind}_output"
                elif kind in {"function_call_output", "custom_tool_call_output"}:
                    call_id = item.get("call_id")
                    if (
                        not isinstance(call_id, str)
                        or calls.get(call_id) != kind
                        or call_id in outputs
                    ):
                        raise ValueError(
                            "Decision tool output requires a matching preceding call"
                        )
                    outputs.add(call_id)
                    _content(item.get("output"), allowed={"input_text", "input_image"})
                else:
                    raise ValueError("Unsupported native decision input item")
        payload = {
            **copy.deepcopy(self.extra_body),
            "model": model,
            "input": native_input,
            "questions": payload_questions,
        }
        try:
            json.dumps(payload, allow_nan=False)
        except (TypeError, ValueError, RecursionError):
            raise ValueError("Decision payload must contain valid JSON") from None
        attempts: list[DecisionUsage | None] = []
        body, response = await self._request(
            "POST", "decisions", payload, request_max_retries, attempts
        )
        usage = attempts[-1] if attempts else None
        try:
            answers = self._parse_answers(body, questions)
        except DecisionError as error:
            error.usage = usage
            error.attempt_usages = tuple(attempts)
            error.model = model
            raise
        return DecisionResult(
            answers,
            body["model"],
            usage,
            response.headers.get("x-request-id"),
            tuple(attempts),
        )

    def _parse_answers(
        self, body: Any, questions: Mapping[str, DecisionQuestion]
    ) -> dict[str, DecisionAnswer]:
        """Validate complete named distributions before exposing any answers.

        Args:
            body: Decoded native response.
            questions: Snapshot of the requested questions.

        Returns:
            Normalized answers, including individual refusals.

        Raises:
            DecisionError: Names, types, or finite probability distributions are invalid.
        """
        if (
            not isinstance(body, dict)
            or not isinstance(body.get("model"), str)
            or not isinstance(body.get("answers"), list)
        ):
            raise DecisionError("Decisions endpoint returned an invalid response")
        raw_answers = body["answers"]
        if len(raw_answers) != len(questions):
            raise DecisionError("Decisions endpoint returned an incomplete answer set")
        answers = {}
        for raw in raw_answers:
            if (
                not isinstance(raw, dict)
                or not isinstance(raw.get("name"), str)
                or raw["name"] not in questions
                or raw["name"] in answers
            ):
                raise DecisionError("Decisions endpoint returned invalid answer names")
            name = raw["name"]
            question = questions[name]
            if raw.get("type") == "refusal":
                answers[name] = DecisionRefusalAnswer()
                continue
            expected = (
                "predicate"
                if isinstance(question, DecisionBooleanQuestion)
                else "choice"
                if isinstance(question, DecisionChoiceQuestion)
                else "score"
            )
            if raw.get("type") != expected:
                raise DecisionError(
                    "Decisions endpoint returned an unexpected answer type"
                )
            if expected == "predicate":
                probability = raw.get("probability")
                if type(probability) not in {int, float} or not 0 <= probability <= 1:
                    raise DecisionError(
                        "Decisions endpoint returned an invalid probability"
                    )
                answers[name] = DecisionBooleanAnswer(float(probability))
                continue
            confidence = raw.get("confidence")
            distribution = raw.get("probabilities")
            if (
                type(confidence) not in {int, float}
                or not 0 <= confidence <= 1
                or not isinstance(distribution, list)
            ):
                raise DecisionError(
                    "Decisions endpoint returned invalid confidence or probabilities"
                )
            probabilities = {}
            expected_values = (
                set(question.criteria)
                if expected == "choice"
                else set(range(len(question.criteria)))
            )
            for entry in distribution:
                if not isinstance(entry, dict):
                    raise DecisionError(
                        "Decisions endpoint returned an invalid distribution"
                    )
                value, probability = entry.get("value"), entry.get("probability")
                if (
                    type(value) not in ({str, bool} if expected == "choice" else {int})
                    or value not in expected_values
                    or value in probabilities
                    or type(probability) not in {int, float}
                    or not 0 <= probability <= 1
                ):
                    raise DecisionError(
                        "Decisions endpoint returned an invalid distribution"
                    )
                if (
                    expected == "score"
                    and entry.get("label") != question.criteria[value]
                ):
                    raise DecisionError(
                        "Decisions endpoint returned an invalid score label"
                    )
                probabilities[value] = float(probability)
            if set(probabilities) != expected_values or not math.isclose(
                sum(probabilities.values()), 1, abs_tol=1e-5
            ):
                raise DecisionError(
                    "Decisions endpoint returned an incomplete probability distribution"
                )
            if expected == "choice":
                choice = raw.get("choice")
                if type(choice) not in {str, bool} or choice not in probabilities:
                    raise DecisionError("Decisions endpoint returned an invalid choice")
                answers[name] = DecisionChoiceAnswer(
                    choice,
                    probabilities[choice],
                    MappingProxyType(probabilities),
                    float(confidence),
                )
            else:
                score = raw.get("score")
                weighted = sum(
                    value * probability for value, probability in probabilities.items()
                )
                if (
                    type(score) not in {int, float}
                    or not 0 <= score <= len(question.criteria) - 1
                    or not math.isclose(score, weighted, abs_tol=1e-5)
                ):
                    raise DecisionError(
                        "Decisions endpoint returned an invalid weighted score"
                    )
                answers[name] = DecisionScoreAnswer(
                    float(score),
                    MappingProxyType(
                        {str(i): value for i, value in enumerate(question.criteria)}
                    ),
                    MappingProxyType(
                        {str(i): value for i, value in probabilities.items()}
                    ),
                    float(confidence),
                )
        return answers

    async def terminate(self) -> None:
        if not self._closed:
            self._closed = True
            await self.client.aclose()
