from __future__ import annotations

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
    ProviderType,
)
from ..provider import DecisionProvider
from ..register import register_provider_adapter
from .request_retry import retry_provider_request

_PROBABILITY_TOLERANCE = 0.02


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
        keys = provider_config.get("key") or []
        self.api_key = (
            keys
            if isinstance(keys, str)
            else next((str(key) for key in keys if key), "")
        )
        headers = dict(self.request_headers)
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        self.proxy = str(provider_config.get("proxy") or "").strip() or None
        self.timeout = float(provider_config.get("timeout", 20))
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
        state: Any = None,
        *,
        request_max_retries: int | None = None,
    ) -> Mapping[str, DecisionAnswer]:
        """Answer multiple questions through one System One request.

        Args:
            questions: Question heads keyed by caller-defined identifiers.
            state: Context forwarded to the model as the request state.
            request_max_retries: Maximum attempts for retryable request errors.

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

        try:
            body = await retry_provider_request(
                "System One Decision",
                _post,
                max_attempts=request_max_retries,
            )
        except httpx.TimeoutException as exc:
            log_connection_failure("System One Decision", exc, self.proxy)
            raise DecisionError(
                f"System One request timed out after {self.timeout:g}s"
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
        except json.JSONDecodeError as exc:
            logger.error(
                f"[System One Decision] Invalid JSON response from "
                f"{self.base_url}: {exc}"
            )
            raise DecisionError("System One endpoint returned invalid JSON") from exc
        raw_answers = body.get("answers") if isinstance(body, Mapping) else None
        if not isinstance(raw_answers, Mapping):
            raise DecisionError("System One endpoint returned an invalid response")

        answers: dict[str, DecisionAnswer] = {}
        for head, question in questions.items():
            raw_answer = raw_answers.get(head)
            if not isinstance(raw_answer, Mapping):
                raise DecisionError(
                    f"System One endpoint returned no answer for {head}"
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
                    and abs(sum(probabilities.values()) - 1) < _PROBABILITY_TOLERANCE
                    and probabilities[choice] >= max(probabilities.values()) - 1e-6
                ):
                    raise DecisionError(
                        f"System One endpoint returned an invalid answer for {head}"
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
                raise DecisionError(
                    f"System One endpoint returned an invalid answer for {head}"
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
