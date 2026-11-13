from __future__ import annotations

import asyncio
import json
import math
from collections.abc import Mapping
from typing import Any, TypeGuard

import httpx

from astrbot import logger

from ..entities import (
    DecisionAnswer,
    DecisionBooleanAnswer,
    DecisionBooleanQuestion,
    DecisionChoiceAnswer,
    DecisionChoiceQuestion,
    DecisionError,
    DecisionQuestion,
    DecisionScoreAnswer,
    DecisionScoreQuestion,
    DecisionState,
    ProviderType,
)
from ..provider import DecisionProvider
from ..register import register_provider_adapter
from .request_retry import retry_provider_request

_DEFAULT_API_BASE = "https://api.openai.com/v1"
_DEFAULT_TIMEOUT = 5.0
_DEFAULT_TOTAL_TIMEOUT = 10.0
_DEFAULT_MAX_CONCURRENCY = 4
# Probabilities arrive as JSON floats; allow rounding drift when checking that
# a distribution sums to one.
_PROBABILITY_SUM_TOLERANCE = 1e-3


def _is_finite_number(value: Any) -> TypeGuard[float]:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _is_unit_number(value: Any) -> TypeGuard[float]:
    return _is_finite_number(value) and 0 <= value <= 1


@register_provider_adapter(
    "openai_decision",
    "OpenAI Decisions API provider",
    provider_type=ProviderType.DECISION,
)
class OpenAIDecisionProvider(DecisionProvider):
    """Decision provider backed by the OpenAI Decisions API (``POST /decisions``).

    The adapter is independent of chat providers: it never joins the main agent
    flow and only answers questions sent through ``DecisionService``.
    """

    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(provider_config, provider_settings)
        base_url = httpx.URL(
            str(provider_config.get("api_base") or "").strip() or _DEFAULT_API_BASE
        )
        endpoint_path, separator, query = base_url.raw_path.partition(b"?")
        endpoint_path = endpoint_path.rstrip(b"/")
        if not endpoint_path.endswith(b"/decisions"):
            endpoint_path += b"/decisions"
        self.endpoint = str(
            base_url.copy_with(raw_path=endpoint_path + separator + query)
        )
        self.model = str(provider_config.get("model") or "").strip()
        if not self.model:
            raise ValueError("OpenAI decision provider requires model")
        self.api_key = provider_config.get("key", "")
        if not isinstance(self.api_key, str):
            raise ValueError("OpenAI decision API key must be a string")
        headers = httpx.Headers(self.request_headers)
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        self.proxy = str(provider_config.get("proxy") or "").strip() or None
        self.timeout = float(provider_config.get("timeout", _DEFAULT_TIMEOUT))
        if not math.isfinite(self.timeout) or self.timeout <= 0:
            raise ValueError("timeout must be finite and greater than 0")
        self.total_timeout = float(
            provider_config.get("total_timeout", _DEFAULT_TOTAL_TIMEOUT)
        )
        if not math.isfinite(self.total_timeout) or self.total_timeout <= 0:
            raise ValueError("total_timeout must be finite and greater than 0")
        self.max_concurrency = int(
            provider_config.get("max_concurrency", _DEFAULT_MAX_CONCURRENCY)
        )
        if self.max_concurrency <= 0:
            raise ValueError("max_concurrency must be greater than 0")
        self.request_semaphore = asyncio.Semaphore(self.max_concurrency)
        self.client = httpx.AsyncClient(
            timeout=self.timeout,
            proxy=self.proxy,
            transport=transport,
            headers=headers,
        )
        self.set_model(self.model)

    async def ask(
        self,
        questions: Mapping[str, DecisionQuestion],
        state: DecisionState | None = None,
        *,
        request_max_retries: int = 0,
    ) -> Mapping[str, DecisionAnswer]:
        """Answer multiple questions through one OpenAI Decisions request.

        String state is sent as text input. Dict state, and list state made of
        objects, is sent as an ``input_json`` part so that keys such as
        ``role`` or ``image_url`` stay plain business data. Other lists are
        serialized as JSON text input.

        Args:
            questions: Question heads keyed by caller-defined identifiers.
            state: Context evaluated by the model.
            request_max_retries: Number of retries after the initial request.

        Returns:
            Validated answers keyed by the same identifiers as ``questions``.

        Raises:
            ValueError: A question or the state cannot be expressed by the API.
            DecisionError: The request fails, the model refuses a question, or
                the response violates the decision contract.
        """
        if not 1 <= len(questions) <= 400:
            raise ValueError("OpenAI decision requests require 1 to 400 questions")

        # Question names are generated from the iteration order so they are
        # stable, unique and independent of caller-provided head strings.
        heads_by_name: dict[str, str] = {}
        payload_questions: list[dict[str, Any]] = []
        for index, (head, question) in enumerate(questions.items()):
            name = f"q{index}"
            heads_by_name[name] = head
            if not isinstance(
                question,
                (
                    DecisionBooleanQuestion,
                    DecisionChoiceQuestion,
                    DecisionScoreQuestion,
                ),
            ):
                raise ValueError(
                    f"question {head} has unsupported type {type(question).__name__}"
                )
            if not isinstance(question.instructions, str):
                raise ValueError(f"question {head} instructions must be a string")
            instructions = question.instructions.strip()
            if not instructions:
                raise ValueError(f"question {head} must not be empty")
            if isinstance(question, DecisionChoiceQuestion):
                if not isinstance(question.criteria, Mapping):
                    raise ValueError(f"question {head} criteria must be a mapping")
                if not 2 <= len(question.criteria) <= 255:
                    raise ValueError(
                        f"question {head} requires 2 to 255 criteria entries"
                    )
                payload_questions.append(
                    {
                        "type": "choice",
                        "name": name,
                        "instructions": instructions,
                        "choices": [
                            {"value": str(option_id), "description": str(description)}
                            for option_id, description in question.criteria.items()
                        ],
                    }
                )
            elif isinstance(question, DecisionScoreQuestion):
                if (
                    not isinstance(question.criteria, list)
                    or not 2 <= len(question.criteria) <= 10
                    or not all(
                        isinstance(level, str) and level.strip()
                        for level in question.criteria
                    )
                ):
                    raise ValueError(
                        f"question {head} requires 2 to 10 non-empty criteria entries"
                    )
                # Labels are the 0-based level indices, matching the legend keys.
                payload_questions.append(
                    {
                        "type": "score",
                        "name": name,
                        "instructions": instructions,
                        "levels": [
                            {"label": str(level_index), "description": level}
                            for level_index, level in enumerate(question.criteria)
                        ],
                    }
                )
            else:
                payload_questions.append(
                    {"type": "predicate", "name": name, "instructions": instructions}
                )

        if state is not None and not isinstance(state, (str, dict, list)):
            raise ValueError(
                "OpenAI decision state must be a string, a dict, or a list"
            )
        try:
            if state is None or isinstance(state, str):
                request_input: Any = state or ""
            elif isinstance(state, dict) or all(
                isinstance(item, dict) for item in state
            ):
                request_input = [
                    {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_json", "data": state}],
                    }
                ]
            else:
                request_input = json.dumps(state, ensure_ascii=False, allow_nan=False)
            request_body = json.dumps(
                {
                    "model": self.model,
                    "input": request_input,
                    "questions": payload_questions,
                },
                ensure_ascii=False,
                allow_nan=False,
            ).encode()
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"OpenAI decision state is not JSON serializable: {exc}"
            ) from exc

        async def _post() -> Any:
            response = await self.client.post(
                self.endpoint,
                content=request_body,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            return response.json()

        async def _request() -> Any:
            async with self.request_semaphore:
                return await retry_provider_request(
                    "OpenAI Decision",
                    _post,
                    max_attempts=request_max_retries + 1,
                    log_error_details=False,
                )

        try:
            body = await asyncio.wait_for(_request(), timeout=self.total_timeout)
        except TimeoutError:
            logger.warning(
                f"[OpenAI Decision] Total request timed out after "
                f"{self.total_timeout:g}s"
            )
            raise DecisionError(
                f"OpenAI decision total request timed out after {self.total_timeout:g}s"
            ) from None
        except httpx.TimeoutException as exc:
            logger.warning(f"[OpenAI Decision] Request failed ({type(exc).__name__})")
            raise DecisionError(
                f"OpenAI decision attempt timed out after {self.timeout:g}s"
            ) from None
        except httpx.HTTPStatusError as exc:
            logger.error(f"[OpenAI Decision] HTTP {exc.response.status_code}")
            raise DecisionError(
                f"OpenAI decision endpoint returned HTTP {exc.response.status_code}"
            ) from None
        except httpx.RequestError as exc:
            logger.warning(f"[OpenAI Decision] Request failed ({type(exc).__name__})")
            raise DecisionError(
                "OpenAI decision request failed: unable to connect "
                "(check network or proxy)"
            ) from None
        except (json.JSONDecodeError, UnicodeDecodeError):
            logger.error("[OpenAI Decision] Invalid JSON or text encoding")
            raise DecisionError(
                "OpenAI decision endpoint returned invalid JSON or text encoding"
            ) from None

        raw_answers = body.get("answers") if isinstance(body, Mapping) else None
        if not isinstance(raw_answers, list):
            logger.warning("[OpenAI Decision] Invalid response")
            raise DecisionError("OpenAI decision endpoint returned an invalid response")

        # Answers are matched by name, never by position.
        answers_by_name: dict[str, Mapping[str, Any]] = {}
        for raw_answer in raw_answers:
            name = raw_answer.get("name") if isinstance(raw_answer, Mapping) else None
            if (
                not isinstance(name, str)
                or name not in heads_by_name
                or name in answers_by_name
            ):
                logger.warning("[OpenAI Decision] Unknown or duplicate answer name")
                raise DecisionError(
                    "OpenAI decision endpoint returned an unknown or duplicate "
                    "answer name"
                )
            answers_by_name[name] = raw_answer

        def invalid_answer(kind: str, head: str) -> DecisionError:
            logger.warning(f"[OpenAI Decision] Invalid {kind} answer for {head}")
            return DecisionError(
                f"OpenAI decision endpoint returned an invalid {kind} answer for {head}"
            )

        answers: dict[str, DecisionAnswer] = {}
        for name, head in heads_by_name.items():
            question = questions[head]
            raw_answer = answers_by_name.get(name)
            if raw_answer is None:
                logger.warning(f"[OpenAI Decision] Missing answer for {head}")
                raise DecisionError(
                    f"OpenAI decision endpoint returned no answer for {head}"
                )
            answer_type = raw_answer.get("type")
            if answer_type == "refusal":
                logger.warning(f"[OpenAI Decision] Model refused question {head}")
                raise DecisionError(f"OpenAI decision model refused question {head}")

            if isinstance(question, DecisionScoreQuestion):
                score = raw_answer.get("score")
                confidence = raw_answer.get("confidence")
                raw_probabilities = raw_answer.get("probabilities")
                if not (
                    answer_type == "score"
                    and _is_finite_number(score)
                    and 0 <= score <= len(question.criteria) - 1
                    and _is_unit_number(confidence)
                    and isinstance(raw_probabilities, list)
                ):
                    raise invalid_answer("score", head)
                legend = {
                    str(level_index): level
                    for level_index, level in enumerate(question.criteria)
                }
                probabilities: dict[str, float] = {}
                for entry in raw_probabilities:
                    if not isinstance(entry, Mapping):
                        raise invalid_answer("score", head)
                    value = entry.get("value")
                    probability = entry.get("probability")
                    level_key = str(value)
                    if not (
                        isinstance(value, int)
                        and not isinstance(value, bool)
                        and level_key in legend
                        and level_key not in probabilities
                        and entry.get("label") == level_key
                        and _is_unit_number(probability)
                    ):
                        raise invalid_answer("score", head)
                    probabilities[level_key] = float(probability)
                if set(probabilities) != set(legend) or not math.isclose(
                    sum(probabilities.values()),
                    1.0,
                    abs_tol=_PROBABILITY_SUM_TOLERANCE,
                ):
                    raise invalid_answer("score", head)
                weighted_score = sum(
                    int(level) * probability
                    for level, probability in probabilities.items()
                )
                # Scale the probability rounding tolerance to the score range.
                if not math.isclose(
                    score,
                    weighted_score,
                    rel_tol=0.0,
                    abs_tol=_PROBABILITY_SUM_TOLERANCE * (len(question.criteria) - 1),
                ):
                    raise invalid_answer("score", head)
                answers[head] = DecisionScoreAnswer(
                    score=float(score),
                    legend=legend,
                    probabilities=probabilities,
                    confidence=float(confidence),
                )
                continue

            if isinstance(question, DecisionChoiceQuestion):
                choice = raw_answer.get("choice")
                confidence = raw_answer.get("confidence")
                raw_probabilities = raw_answer.get("probabilities")
                option_ids = {str(option_id) for option_id in question.criteria}
                if not (
                    answer_type == "choice"
                    and isinstance(choice, str)
                    and choice in option_ids
                    and _is_unit_number(confidence)
                    and isinstance(raw_probabilities, list)
                ):
                    raise invalid_answer("choice", head)
                probabilities = {}
                for entry in raw_probabilities:
                    if not isinstance(entry, Mapping):
                        raise invalid_answer("choice", head)
                    value = entry.get("value")
                    probability = entry.get("probability")
                    if not (
                        isinstance(value, str)
                        and value in option_ids
                        and value not in probabilities
                        and _is_unit_number(probability)
                    ):
                        raise invalid_answer("choice", head)
                    probabilities[value] = float(probability)
                if set(probabilities) != option_ids or not math.isclose(
                    sum(probabilities.values()),
                    1.0,
                    abs_tol=_PROBABILITY_SUM_TOLERANCE,
                ):
                    raise invalid_answer("choice", head)
                answers[head] = DecisionChoiceAnswer(
                    choice=choice,
                    probability=probabilities[choice],
                    probabilities=probabilities,
                    confidence=float(confidence),
                )
                continue

            probability = raw_answer.get("probability")
            if not (answer_type == "predicate" and _is_unit_number(probability)):
                raise invalid_answer("boolean", head)
            answers[head] = DecisionBooleanAnswer(probability=float(probability))

        return answers

    async def terminate(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()
