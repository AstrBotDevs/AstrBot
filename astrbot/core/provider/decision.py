from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from .entities import (
    DecisionAnswer,
    DecisionBooleanQuestion,
    DecisionChoiceQuestion,
    DecisionError,
    DecisionQuestion,
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
        state: Any = None,
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
            ValueError: The questions or options are unusable.
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
        return await provider.ask(questions, state)

    async def choose(
        self,
        question: str,
        options: Mapping[str, str] | Sequence[str],
        *,
        state: Any = None,
        provider_id: str | None = None,
    ) -> DecisionAnswer:
        """Choose one option for a question.

        Args:
            question: The decision question.
            options: Option values, or a mapping of values to descriptions.
            state: Context forwarded to the provider.
            provider_id: Provider instance ID, or None to use the default decision provider.

        Returns:
            The selected original option value and its probability distribution.

        Raises:
            ValueError: The questions or options are unusable.
        """
        question = question.strip()
        if not question:
            raise ValueError("question must not be empty")
        normalized = (
            [(str(value), str(description)) for value, description in options.items()]
            if isinstance(options, Mapping)
            else [(str(value), str(value)) for value in options]
        )
        if len(normalized) < 2:
            raise ValueError("options must contain at least two values")
        values = [value for value, _ in normalized]
        if len(set(values)) != len(values):
            raise ValueError("options must be unique")

        option_ids = {f"o{index}": value for index, value in enumerate(values, start=1)}
        answers = await self.ask(
            {
                "answer": DecisionChoiceQuestion(
                    instructions=question,
                    options={
                        f"o{index}": description
                        for index, (_, description) in enumerate(normalized, start=1)
                    },
                )
            },
            state,
            provider_id=provider_id,
        )
        answer = answers["answer"]
        if answer.choice is None:
            raise DecisionError("Decision provider returned no choice")
        if answer.choice not in option_ids or set(answer.probabilities) != set(
            option_ids
        ):
            raise DecisionError("Decision provider returned an invalid choice")
        return DecisionAnswer(
            choice=option_ids[answer.choice],
            probability=answer.probability,
            probabilities={
                option_ids[option_id]: probability
                for option_id, probability in answer.probabilities.items()
            },
            confidence=answer.confidence,
        )

    async def yes_no(
        self,
        question: str,
        *,
        state: Any = None,
        threshold: float = 0.5,
        provider_id: str | None = None,
    ) -> bool:
        """Return whether a statement is true at the given probability threshold.

        Args:
            question: The statement or yes/no question.
            state: Context forwarded to the provider.
            threshold: Probability at or above which the result is true.
            provider_id: Provider instance ID, or None to use the default decision provider.

        Returns:
            True when the model probability meets ``threshold``.

        Raises:
            ValueError: The question or threshold is unusable.
        """
        question = question.strip()
        if not question:
            raise ValueError("question must not be empty")
        if not 0 <= threshold <= 1:
            raise ValueError("threshold must be between 0 and 1")
        answers = await self.ask(
            {"answer": DecisionBooleanQuestion(question)},
            state,
            provider_id=provider_id,
        )
        return answers["answer"].probability >= threshold
