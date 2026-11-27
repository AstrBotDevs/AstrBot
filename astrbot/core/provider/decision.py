from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from astrbot import logger
from astrbot.core.utils.media_utils import ResolvedMediaData

from .entities import (
    DecisionAnswer,
    DecisionBooleanAnswer,
    DecisionBooleanQuestion,
    DecisionChoiceAnswer,
    DecisionChoiceQuestion,
    DecisionError,
    DecisionQuestion,
    DecisionState,
    ProviderType,
)
from .provider import DecisionProvider

if TYPE_CHECKING:
    from .manager import ProviderManager


class DecisionService:
    """Expose decision questions without coupling callers to a provider adapter."""

    def __init__(self, provider_manager: ProviderManager) -> None:
        self.provider_manager = provider_manager

    async def ask(
        self,
        questions: Mapping[str, DecisionQuestion],
        state: DecisionState | None = None,
        *,
        provider_id: str | None = None,
    ) -> Mapping[str, DecisionAnswer]:
        """Answer multiple decision questions in one request.

        Args:
            questions: Question heads keyed by caller-defined identifiers.
            state: Context forwarded to the provider.
            provider_id: Provider instance ID, or None to use the default decision provider.

        Returns:
            Answers keyed by the same identifiers as ``questions``.

        Raises:
            ValueError: The questions or criteria are unusable.
            DecisionError: The provider is unavailable, the request fails, or
                the response violates the decision contract.
        """
        provider = (
            await self.provider_manager.get_provider_by_id(provider_id)
            if provider_id
            else await self.provider_manager.get_using_provider_async(
                ProviderType.DECISION
            )
        )
        if not isinstance(provider, DecisionProvider):
            target = f" {provider_id}" if provider_id else ""
            raise DecisionError(f"Decision provider{target} is not configured")
        if isinstance(
            state, ResolvedMediaData
        ) and not DecisionProvider.supports_image_input(provider.provider_config):
            raise DecisionError(
                "The selected decision model does not support image input"
            )
        return await provider.ask(questions, state)

    async def choose(
        self,
        question: str,
        criteria: Mapping[str, str] | Sequence[str],
        *,
        state: DecisionState | None = None,
        provider_id: str | None = None,
    ) -> DecisionChoiceAnswer:
        """Choose one option for a question.

        Args:
            question: The decision question.
            criteria: Option values, or a mapping of values to descriptions.
            state: Context forwarded to the provider.
            provider_id: Provider instance ID, or None to use the default decision provider.

        Returns:
            The selected original option value and its probability distribution.

        Raises:
            ValueError: The questions or criteria are unusable.
        """
        question = question.strip()
        if not question:
            raise ValueError("question must not be empty")
        normalized = (
            [(str(value), str(description)) for value, description in criteria.items()]
            if isinstance(criteria, Mapping)
            else [(str(value), str(value)) for value in criteria]
        )
        if len(normalized) < 2:
            raise ValueError("criteria must contain at least two values")
        values = [value for value, _ in normalized]
        if len(set(values)) != len(values):
            raise ValueError("criteria must be unique")

        option_ids = {f"o{index}": value for index, value in enumerate(values, start=1)}
        answers = await self.ask(
            {
                "answer": DecisionChoiceQuestion(
                    instructions=question,
                    criteria={
                        f"o{index}": description
                        for index, (_, description) in enumerate(normalized, start=1)
                    },
                )
            },
            state,
            provider_id=provider_id,
        )
        answer = answers["answer"]
        if not isinstance(answer, DecisionChoiceAnswer):
            raise DecisionError("Decision provider returned no choice answer")
        if answer.choice not in option_ids or set(answer.probabilities) != set(
            option_ids
        ):
            raise DecisionError("Decision provider returned an invalid choice")
        return DecisionChoiceAnswer(
            choice=option_ids[answer.choice],
            probability=answer.probability,
            probabilities={
                option_ids[option_id]: probability
                for option_id, probability in answer.probabilities.items()
            },
            confidence=answer.confidence,
        )

    async def matches(
        self,
        question: str,
        *,
        expected_answer: bool,
        confidence_threshold: float = 0.2,
        state: DecisionState | None = None,
        provider_id: str | None = None,
    ) -> bool:
        """Check a yes or no answer and the model's confidence in that answer.

        Args:
            question: The yes or no question to ask.
            expected_answer: Boolean answer required to match.
            confidence_threshold: Minimum confidence in the selected answer, inclusive.
            state: Text, structured data, or an image to evaluate.
            provider_id: Provider instance ID, or None for the default decision provider.

        Returns:
            True if the selected answer matches and its confidence meets the threshold.

        Raises:
            ValueError: The question is empty or the threshold is outside [0, 1].
            DecisionError: The provider is unavailable or returns an invalid answer.
        """
        if not 0 <= confidence_threshold <= 1:
            raise ValueError("confidence_threshold must be between 0 and 1")
        answer = await self.choose(
            question,
            {"true": "Yes", "false": "No"},
            state=state,
            provider_id=provider_id,
        )
        # Confidence rates the selected answer. (false, 0.2) is a tentative "no".
        # (true, 0.8) is a confident "yes". Neither implies the other.
        selected_answer = answer.choice == "true"
        return (
            selected_answer == expected_answer
            and answer.confidence >= confidence_threshold
        )

    async def yes_no(
        self,
        question: str,
        *,
        state: DecisionState | None = None,
        threshold: float = 0.5,
        provider_id: str | None = None,
        default: bool | None = None,
    ) -> bool:
        """Return whether a statement is true at the given probability threshold.

        Args:
            question: The statement or yes/no question.
            state: Context forwarded to the provider.
            threshold: Probability at or above which the result is true.
            provider_id: Provider instance ID, or None to use the default decision provider.
            default: Value returned when the decision provider fails. When None,
                the provider error is re-raised.

        Returns:
            True when the model probability meets ``threshold``.

        Raises:
            ValueError: The question or threshold is unusable.
            DecisionError: The provider fails and no ``default`` is provided.
        """
        question = question.strip()
        if not question:
            raise ValueError("question must not be empty")
        if not 0 <= threshold <= 1:
            raise ValueError("threshold must be between 0 and 1")
        try:
            answers = await self.ask(
                {"answer": DecisionBooleanQuestion(question)},
                state,
                provider_id=provider_id,
            )
            answer = answers["answer"]
            if not isinstance(answer, DecisionBooleanAnswer):
                raise DecisionError("Decision provider returned no boolean answer")
        except DecisionError as exc:
            if default is None:
                raise
            logger.warning(f"[Decision] yes_no failed; using default {default}: {exc}")
            return default
        return answer.probability >= threshold
