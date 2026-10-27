from __future__ import annotations

import asyncio
import json
import math
from collections.abc import Mapping
from typing import Any

import httpx

from astrbot import logger
from astrbot.core.utils.network_utils import log_connection_failure

from ..entities import (
    DecisionAnswer,
    DecisionChoiceQuestion,
    DecisionError,
    DecisionQuestion,
    DecisionState,
    ProviderType,
)
from ..provider import DecisionProvider
from ..register import register_provider_adapter
from .request_retry import retry_provider_request

_DEFAULT_PROBABILITY_TOLERANCE = 0.05
_DEFAULT_TOTAL_TIMEOUT = 5.0
_DEFAULT_MAX_CONCURRENCY = 4
_RESPONSE_SUMMARY_CHARS = 500


def _summarize_response(value: Any) -> str:
    summary = json.dumps(value, ensure_ascii=False, default=str)
    if len(summary) <= _RESPONSE_SUMMARY_CHARS:
        return summary
    return f"{summary[: _RESPONSE_SUMMARY_CHARS - 3]}..."


@register_provider_adapter(
    "system_one_decision",
    "System One / Jev decision provider",
    provider_type=ProviderType.DECISION,
)
class SystemOneDecisionProvider(DecisionProvider):
    """System One compatible provider for structured decisions."""

    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(provider_config, provider_settings)
        raw_base_url = str(provider_config.get("api_base") or "").strip()
        exact_endpoint = raw_base_url.endswith("/")
        base_url = raw_base_url.rstrip("/")
        if not base_url:
            raise ValueError("System One decision provider requires api_base")
        self.base_url = (
            base_url
            if exact_endpoint or base_url.endswith("/systemone")
            else f"{base_url}/systemone"
        )
        self.model = str(provider_config.get("model") or "jev-latest")
        self.api_key = provider_config.get("key", "")
        if not isinstance(self.api_key, str):
            raise ValueError("System One API key must be a string")
        headers = dict(self.request_headers)
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        self.proxy = str(provider_config.get("proxy") or "").strip() or None
        self.timeout = float(provider_config.get("timeout", 2))
        self.total_timeout = float(
            provider_config.get("total_timeout", _DEFAULT_TOTAL_TIMEOUT)
        )
        if self.total_timeout <= 0:
            raise ValueError("total_timeout must be greater than 0")
        self.max_concurrency = int(
            provider_config.get("max_concurrency", _DEFAULT_MAX_CONCURRENCY)
        )
        if self.max_concurrency <= 0:
            raise ValueError("max_concurrency must be greater than 0")
        self.request_semaphore = asyncio.Semaphore(self.max_concurrency)
        self.probability_tolerance = float(
            provider_config.get(
                "probability_tolerance",
                _DEFAULT_PROBABILITY_TOLERANCE,
            )
        )
        if not 0 <= self.probability_tolerance <= 1:
            raise ValueError("probability_tolerance must be between 0 and 1")
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
        """Answer multiple questions through one System One request.

        Args:
            questions: Question heads keyed by caller-defined identifiers.
            state: Context forwarded to the model as the request state.
            request_max_retries: Number of retries after the initial request.

        Returns:
            Validated answers keyed by the same identifiers as ``questions``.

        Raises:
            ValueError: A question is empty or has fewer than two choices.
            DecisionError: The request fails or the response violates the
                decision contract.
        """
        if not questions:
            raise ValueError("questions must not be empty")

        payload_questions: dict[str, dict[str, Any]] = {}
        for head, question in questions.items():
            instructions = question.instructions.strip()
            if not instructions:
                raise ValueError(f"question {head} must not be empty")
            if isinstance(question, DecisionChoiceQuestion):
                if len(question.options) < 2:
                    raise ValueError(f"question {head} requires at least two options")
                payload_questions[head] = {
                    "type": "choice",
                    "instructions": instructions,
                    "criteria": dict(question.options),
                }
            else:
                payload_questions[head] = {
                    "type": "noul",
                    "instructions": instructions,
                }

        async def _post() -> Any:
            response = await self.client.post(
                self.base_url,
                json={
                    "model": self.model,
                    "state": {} if state is None else state,
                    "questions": payload_questions,
                },
            )
            response.raise_for_status()
            return response.json()

        async def _request() -> Any:
            async with self.request_semaphore:
                return await retry_provider_request(
                    "System One Decision",
                    _post,
                    max_attempts=request_max_retries + 1,
                )

        try:
            body = await asyncio.wait_for(_request(), timeout=self.total_timeout)
        except TimeoutError as exc:
            logger.warning(
                f"[System One Decision] Total request timed out after "
                f"{self.total_timeout:g}s"
            )
            raise DecisionError(
                f"System One total request timed out after {self.total_timeout:g}s"
            ) from exc
        except httpx.TimeoutException as exc:
            log_connection_failure("System One Decision", exc, self.proxy)
            raise DecisionError(
                f"System One attempt timed out after {self.timeout:g}s"
            ) from exc
        except httpx.HTTPStatusError as exc:
            logger.error(
                f"[System One Decision] HTTP {exc.response.status_code} from "
                f"{self.base_url}"
            )
            raise DecisionError(
                f"System One endpoint returned HTTP {exc.response.status_code}"
            ) from exc
        except httpx.RequestError as exc:
            log_connection_failure("System One Decision", exc, self.proxy)
            raise DecisionError(
                "System One request failed: unable to connect (check network or proxy)"
            ) from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            logger.error(
                f"[System One Decision] Invalid JSON or text encoding from "
                f"{self.base_url}: {exc}"
            )
            raise DecisionError(
                "System One endpoint returned invalid JSON or text encoding"
            ) from exc
        raw_answers = body.get("answers") if isinstance(body, Mapping) else None
        if not isinstance(raw_answers, Mapping):
            summary = _summarize_response(body)
            logger.warning(f"[System One Decision] Invalid response: {summary}")
            raise DecisionError(
                f"System One endpoint returned an invalid response: {summary}"
            )

        answers: dict[str, DecisionAnswer] = {}
        for head, question in questions.items():
            raw_answer = raw_answers.get(head)
            if not isinstance(raw_answer, Mapping):
                summary = _summarize_response(raw_answers)
                logger.warning(
                    f"[System One Decision] Missing answer for {head}: {summary}"
                )
                raise DecisionError(
                    f"System One endpoint returned no answer for {head}: {summary}"
                )

            if isinstance(question, DecisionChoiceQuestion):
                choice = raw_answer.get("choice")
                probabilities = raw_answer.get("probabilities")
                confidence = raw_answer.get("confidence")
                valid_numbers = isinstance(confidence, (int, float)) and not isinstance(
                    confidence, bool
                )
                if isinstance(probabilities, Mapping) and valid_numbers:
                    numbers = [*probabilities.values(), confidence]
                    valid_numbers = all(
                        isinstance(value, (int, float))
                        and not isinstance(value, bool)
                        and math.isfinite(value)
                        and 0 <= value <= 1
                        for value in numbers
                    )
                if not (
                    isinstance(choice, str)
                    and isinstance(probabilities, Mapping)
                    and valid_numbers
                    and set(probabilities) == set(question.options)
                    and choice in question.options
                    and abs(sum(probabilities.values()) - 1)
                    <= self.probability_tolerance
                    and probabilities[choice]
                    >= max(probabilities.values()) - self.probability_tolerance
                ):
                    summary = _summarize_response(raw_answer)
                    logger.warning(
                        f"[System One Decision] Invalid choice answer for "
                        f"{head}: {summary}"
                    )
                    raise DecisionError(
                        f"System One endpoint returned an invalid choice answer "
                        f"for {head}: {summary}"
                    )
                answers[head] = DecisionAnswer(
                    choice=choice,
                    probability=float(probabilities[choice]),
                    probabilities={
                        option_id: float(probability)
                        for option_id, probability in probabilities.items()
                    },
                    confidence=float(confidence),
                )
                continue

            probability = raw_answer.get("noul")
            if not (
                isinstance(probability, (int, float))
                and not isinstance(probability, bool)
                and math.isfinite(probability)
                and 0 <= probability <= 1
            ):
                summary = _summarize_response(raw_answer)
                logger.warning(
                    f"[System One Decision] Invalid boolean answer for "
                    f"{head}: {summary}"
                )
                raise DecisionError(
                    f"System One endpoint returned an invalid boolean answer "
                    f"for {head}: {summary}"
                )
            answers[head] = DecisionAnswer(
                choice=None,
                probability=float(probability),
                probabilities={},
                confidence=None,
            )

        return answers

    async def terminate(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()
