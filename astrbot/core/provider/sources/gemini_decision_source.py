from __future__ import annotations

import asyncio
import base64
import json
import math
import unicodedata
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
    DecisionInput,
    DecisionMedia,
    DecisionQuestion,
    DecisionScoreAnswer,
    DecisionScoreQuestion,
    DecisionState,
    ProviderType,
)
from ..provider import DecisionProvider
from ..register import register_provider_adapter
from .request_retry import retry_provider_request

_DEFAULT_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
_DEFAULT_TIMEOUT = 5.0
_DEFAULT_TOTAL_TIMEOUT = 10.0
_DEFAULT_MAX_CONCURRENCY = 4
# Probabilities arrive as JSON floats; allow rounding drift when checking that
# a distribution sums to one.
_PROBABILITY_SUM_TOLERANCE = 1e-3
_MEDIA_MIME_TYPES = {
    "image": {
        "image/png",
        "image/jpeg",
        "image/webp",
        "image/heic",
        "image/heif",
        "image/gif",
        "image/bmp",
        "image/tiff",
    },
    "audio": {
        "audio/wav",
        "audio/mp3",
        "audio/mpeg",
        "audio/aiff",
        "audio/aac",
        "audio/ogg",
        "audio/flac",
        "audio/m4a",
        "audio/opus",
        "audio/webm",
        "audio/l16",
        "audio/alaw",
        "audio/mulaw",
    },
    "video": {
        "video/mp4",
        "video/mpeg",
        "video/mov",
        "video/avi",
        "video/webm",
        "video/wmv",
        "video/x-flv",
        "video/3gpp",
    },
    "document": {"application/pdf"},
}


def _is_finite_number(value: Any) -> TypeGuard[float]:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and (isinstance(value, int) or math.isfinite(value))
    )


def _is_unit_number(value: Any) -> TypeGuard[float]:
    return _is_finite_number(value) and 0 <= value <= 1


def _build_input(state: DecisionState | None) -> str | list[dict[str, Any]]:
    """Convert explicit media or business context to Gemini input.

    Args:
        state: Text, business JSON, or explicit text/media content.

    Returns:
        Non-empty text or ordered Gemini content blocks.

    Raises:
        ValueError: The input is unsupported, malformed, or not JSON serializable.
    """
    if state is None or isinstance(state, str):
        # Gemini rejects empty text; represent absent context as JSON text.
        return state or "{}"
    if isinstance(state, (dict, list)):
        try:
            return json.dumps(state, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError):
            raise ValueError("Gemini decision state is not JSON serializable") from None
    if not isinstance(state, DecisionInput):
        raise ValueError(
            "Gemini decision state must be a string, a dict, a list, or DecisionInput"
        )
    if not isinstance(state.content, list) or not state.content:
        raise ValueError("DecisionInput requires a non-empty content list")
    content: list[dict[str, Any]] = []
    for part in state.content:
        if isinstance(part, str):
            if not part:
                raise ValueError("DecisionInput text must not be empty")
            content.append({"type": "text", "text": part})
            continue
        if not isinstance(part, DecisionMedia):
            raise ValueError("DecisionInput requires text or DecisionMedia")
        if (
            not isinstance(part.type, str)
            or part.type not in _MEDIA_MIME_TYPES
            or not isinstance(part.mime_type, str)
            or part.mime_type not in _MEDIA_MIME_TYPES[part.type]
        ):
            raise ValueError("Unsupported Gemini decision media MIME type")
        if (part.data is None) == (part.uri is None):
            raise ValueError("DecisionMedia requires exactly one of data or uri")
        block: dict[str, Any] = {"type": part.type, "mime_type": part.mime_type}
        if part.data is not None:
            if not isinstance(part.data, str) or not part.data:
                raise ValueError("DecisionMedia data must be non-empty base64")
            try:
                base64.b64decode(part.data, validate=True)
            except ValueError:
                raise ValueError("DecisionMedia data must be valid base64") from None
            block["data"] = part.data
        else:
            if not isinstance(part.uri, str) or not part.uri:
                raise ValueError("DecisionMedia uri must be a non-empty HTTPS URI")
            try:
                uri = httpx.URL(part.uri)
            except httpx.InvalidURL:
                raise ValueError(
                    "DecisionMedia uri must be a valid HTTPS URI"
                ) from None
            if uri.scheme != "https" or not uri.host:
                raise ValueError("Gemini decision media requires an HTTPS URI")
            block["uri"] = part.uri
        if part.resolution is not None:
            if (
                part.type not in ("image", "video")
                or part.resolution not in ("low", "medium", "high", "ultra_high")
                or (part.type == "video" and part.resolution == "ultra_high")
            ):
                raise ValueError("Unsupported Gemini decision media resolution")
            block["resolution"] = part.resolution
        content.append(block)
    return content


@register_provider_adapter(
    "gemini_decision",
    "Gemini Decisions API provider",
    provider_type=ProviderType.DECISION,
)
class GeminiDecisionProvider(DecisionProvider):
    """Decision provider backed by the Gemini Decisions API (``POST /decisions``).

    The adapter is independent of chat providers: it never joins the main agent
    flow and only answers questions sent through ``DecisionService``.
    """

    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Initialize the independent decision HTTP client.

        Args:
            provider_config: Model, credentials, endpoint, and request limits.
            provider_settings: Shared provider settings.
            transport: Optional HTTP transport for testing.

        Raises:
            ValueError: The model, key, or request limits are invalid.
        """
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
            raise ValueError("Gemini decision provider requires model")
        self.api_key = provider_config.get("key", "")
        if not isinstance(self.api_key, str):
            raise ValueError("Gemini decision API key must be a string")
        headers = httpx.Headers(self.request_headers)
        if self.api_key:
            headers["x-goog-api-key"] = self.api_key
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
        """Evaluate questions against text, business JSON, or explicit media.

        Dict and list state is serialized as JSON text, never interpreted as
        Gemini content blocks, message history, or media references.

        Args:
            questions: Questions keyed by caller-defined identifiers.
            state: Shared text, business JSON, or explicit DecisionInput content.
            request_max_retries: Number of retries after the initial request.

        Returns:
            Validated answers keyed by the original question identifiers.

        Raises:
            ValueError: A question or state cannot be expressed by this adapter.
            DecisionError: The request fails, input is blocked, or the response
                violates the decision contract.
        """
        if not 1 <= len(questions) <= 1000:
            raise ValueError("Gemini decision requests require 1 to 1000 questions")

        # Generated names keep caller identifiers independent of wire constraints.
        heads_by_name: dict[str, str] = {}
        payload_questions: dict[str, dict[str, Any]] = {}
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
                raise ValueError(f"question {head} has an unsupported type")
            if (
                not isinstance(question.instructions, str)
                or not question.instructions.strip()
            ):
                raise ValueError(
                    f"question {head} requires non-empty string instructions"
                )
            payload: dict[str, Any] = {"instructions": question.instructions.strip()}
            if isinstance(question, DecisionChoiceQuestion):
                if (
                    not isinstance(question.criteria, Mapping)
                    or not 2 <= len(question.criteria) <= 255
                ):
                    raise ValueError(
                        f"question {head} requires 2 to 255 criteria entries"
                    )
                for option_id, description in question.criteria.items():
                    if (
                        not isinstance(option_id, str)
                        or not 1 <= len(option_id) <= 128
                        or option_id != option_id.strip()
                        or any(
                            unicodedata.category(char).startswith("C")
                            or (char.isspace() and char != " ")
                            for char in option_id
                        )
                        or not isinstance(description, str)
                    ):
                        raise ValueError(f"question {head} has invalid choice criteria")
                payload.update(type="choice", criteria=dict(question.criteria))
            elif isinstance(question, DecisionScoreQuestion):
                if (
                    not isinstance(question.criteria, list)
                    or not 2 <= len(question.criteria) <= 255
                    or not all(
                        isinstance(level, str) and level.strip()
                        for level in question.criteria
                    )
                ):
                    raise ValueError(
                        f"question {head} requires 2 to 255 non-empty criteria entries"
                    )
                payload.update(type="score", criteria=list(question.criteria))
            else:
                payload["type"] = "noul"
            payload_questions[name] = payload

        request_input = _build_input(state)
        try:
            request_body = json.dumps(
                {
                    "model": self.model,
                    "input": request_input,
                    "questions": payload_questions,
                },
                ensure_ascii=False,
                allow_nan=False,
            ).encode()
        except (TypeError, ValueError):
            raise ValueError(
                "Gemini decision request is not JSON serializable"
            ) from None

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
                    "Gemini Decision",
                    _post,
                    max_attempts=request_max_retries + 1,
                    log_error_details=False,
                )

        try:
            body = await asyncio.wait_for(_request(), timeout=self.total_timeout)
        except asyncio.TimeoutError:
            logger.warning(
                f"[Gemini Decision] Total request timed out after "
                f"{self.total_timeout:g}s"
            )
            raise DecisionError(
                f"Gemini decision total request timed out after {self.total_timeout:g}s"
            ) from None
        except httpx.TimeoutException as exc:
            logger.warning(f"[Gemini Decision] Request failed ({type(exc).__name__})")
            raise DecisionError(
                f"Gemini decision attempt timed out after {self.timeout:g}s"
            ) from None
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 400:
                try:
                    error_body = exc.response.json()
                except (ValueError, UnicodeDecodeError):
                    error_body = None
                error = (
                    error_body.get("error") if isinstance(error_body, Mapping) else None
                )
                if isinstance(error, Mapping) and error.get("code") in (
                    "safety",
                    "prohibited_content",
                    "blocklist",
                    "image_safety",
                    "content_blocked",
                ):
                    # Server error messages can contain private input.
                    logger.warning("[Gemini Decision] Input blocked by content filters")
                    raise DecisionError(
                        "Gemini decision input was blocked by content filters"
                    ) from None
            logger.error(f"[Gemini Decision] HTTP {exc.response.status_code}")
            raise DecisionError(
                f"Gemini decision endpoint returned HTTP {exc.response.status_code}"
            ) from None
        except httpx.RequestError as exc:
            logger.warning(f"[Gemini Decision] Request failed ({type(exc).__name__})")
            raise DecisionError(
                "Gemini decision request failed: unable to connect "
                "(check network or proxy)"
            ) from None
        except (json.JSONDecodeError, UnicodeDecodeError):
            logger.error("[Gemini Decision] Invalid JSON or text encoding")
            raise DecisionError(
                "Gemini decision endpoint returned invalid JSON or text encoding"
            ) from None

        if not isinstance(body, Mapping):
            raise DecisionError("Gemini decision endpoint returned an invalid response")
        feedback = body.get("prompt_feedback")
        if feedback is not None:
            if not isinstance(feedback, Mapping):
                raise DecisionError(
                    "Gemini decision endpoint returned invalid prompt feedback"
                )
            if feedback.get("block_reason"):
                # Do not log server-provided text, which may contain private input.
                raise DecisionError(
                    "Gemini decision input was blocked by content filters"
                )
        raw_answers = body.get("answers")
        if not isinstance(raw_answers, Mapping) or set(raw_answers) != set(
            heads_by_name
        ):
            raise DecisionError(
                "Gemini decision endpoint returned missing or unknown answers"
            )

        def invalid_answer(kind: str) -> DecisionError:
            return DecisionError(
                f"Gemini decision endpoint returned an invalid {kind} answer"
            )

        answers: dict[str, DecisionAnswer] = {}
        for name, head in heads_by_name.items():
            question = questions[head]
            raw_answer = raw_answers[name]
            if not isinstance(raw_answer, Mapping):
                raise invalid_answer("decision")
            confidence = raw_answer.get("confidence")
            if not _is_unit_number(confidence):
                raise invalid_answer("confidence")
            if isinstance(question, DecisionBooleanQuestion):
                probability = raw_answer.get("noul")
                if not (
                    raw_answer.get("type") == "noul"
                    and _is_unit_number(probability)
                    and 0.01 <= probability <= 0.99
                    and math.isclose(
                        confidence,
                        max(probability, 1 - probability),
                        rel_tol=0.0,
                        abs_tol=_PROBABILITY_SUM_TOLERANCE,
                    )
                ):
                    raise invalid_answer("boolean")
                answers[head] = DecisionBooleanAnswer(probability=float(probability))
                continue

            kind = "choice" if isinstance(question, DecisionChoiceQuestion) else "score"
            expected_keys = (
                set(question.criteria)
                if isinstance(question, DecisionChoiceQuestion)
                else {str(index) for index in range(len(question.criteria))}
            )
            raw_probabilities = raw_answer.get("probabilities")
            if not (
                raw_answer.get("type") == kind
                and isinstance(raw_probabilities, Mapping)
                and set(raw_probabilities) == expected_keys
                and all(_is_unit_number(value) for value in raw_probabilities.values())
                and math.isclose(
                    sum(raw_probabilities.values()),
                    1.0,
                    rel_tol=0.0,
                    abs_tol=_PROBABILITY_SUM_TOLERANCE,
                )
            ):
                raise invalid_answer(kind)
            probabilities = {
                key: float(value) for key, value in raw_probabilities.items()
            }
            highest_probability = max(probabilities.values())
            if not math.isclose(
                confidence,
                highest_probability,
                rel_tol=0.0,
                abs_tol=_PROBABILITY_SUM_TOLERANCE,
            ):
                raise invalid_answer(kind)

            if isinstance(question, DecisionChoiceQuestion):
                choice = raw_answer.get("choice")
                # Exact ties use UTF-8 byte order, independent of response order.
                expected_choice = min(
                    probabilities,
                    key=lambda key: (-probabilities[key], key.encode("utf-8")),
                )
                if not isinstance(choice, str) or choice != expected_choice:
                    raise invalid_answer(kind)
                answers[head] = DecisionChoiceAnswer(
                    choice=choice,
                    probability=probabilities[choice],
                    probabilities=probabilities,
                    confidence=float(confidence),
                )
            else:
                score = raw_answer.get("score")
                legend = {
                    str(index): level for index, level in enumerate(question.criteria)
                }
                weighted_score = sum(
                    int(level) * value for level, value in probabilities.items()
                )
                if not (
                    _is_finite_number(score)
                    and 0 <= score <= len(question.criteria) - 1
                    and raw_answer.get("legend") == legend
                    and math.isclose(
                        score,
                        weighted_score,
                        rel_tol=0.0,
                        abs_tol=_PROBABILITY_SUM_TOLERANCE,
                    )
                ):
                    raise invalid_answer(kind)
                answers[head] = DecisionScoreAnswer(
                    score=float(score),
                    legend=legend,
                    probabilities=probabilities,
                    confidence=float(confidence),
                )
        return answers

    async def terminate(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()
