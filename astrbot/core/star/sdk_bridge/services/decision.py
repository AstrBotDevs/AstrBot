from __future__ import annotations

import json
from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from astrbot_sdk import decision as sdk
from astrbot_sdk.errors import InvalidRequest, NotFound

from astrbot.core.provider import entities as core

if TYPE_CHECKING:
    from astrbot.core.star.context import Context


class DecisionModelService:
    """Forward SDK decision questions through the configured Core provider."""

    capability_id = "decision.ask"

    def __init__(self, context: Context) -> None:
        self._context = context

    async def handle(self, operation: str, payload: dict[str, Any]) -> Any:
        """Return typed answers or raise a portable SDK error.

        Args:
            operation: Requested decision operation.
            payload: Decoded questions, state, and provider selection.

        Returns:
            A decision answer, a keyed batch of answers, or a boolean.

        Raises:
            InvalidRequest: Parameters are invalid.
            NotFound: The operation is unknown.
            sdk.DecisionError: The configured provider could not answer.
        """
        service = self._context.decision
        state = payload.get("state")
        provider_id = payload.get("provider_id")
        try:
            if state is not None:
                if not isinstance(state, str | list | dict):
                    raise ValueError("state must be text, a list, or an object")
                json.dumps(state, allow_nan=False)
            if provider_id is not None and not isinstance(provider_id, str):
                raise ValueError("provider_id must be a string")
            if operation == "ask":
                questions = payload.get("questions")
                if not isinstance(questions, dict) or not questions:
                    raise ValueError("questions must be a nonempty mapping")
                question_types = {
                    sdk.DecisionChoiceQuestion: core.DecisionChoiceQuestion,
                    sdk.DecisionBooleanQuestion: core.DecisionBooleanQuestion,
                    sdk.DecisionScoreQuestion: core.DecisionScoreQuestion,
                }
                if any(
                    type(question) not in question_types
                    for question in questions.values()
                ):
                    raise ValueError("questions must be SDK DecisionQuestion values")
                answers = await service.ask(
                    {
                        key: question_types[type(question)](**asdict(question))
                        for key, question in questions.items()
                    },
                    state,
                    provider_id=provider_id,
                )
                answer_types = {
                    core.DecisionChoiceAnswer: sdk.DecisionChoiceAnswer,
                    core.DecisionBooleanAnswer: sdk.DecisionBooleanAnswer,
                    core.DecisionScoreAnswer: sdk.DecisionScoreAnswer,
                }
                return {
                    key: answer_types[type(answer)](**asdict(answer))
                    for key, answer in answers.items()
                }
            if operation in {"choose", "yes_no"}:
                question = payload.get("question")
                if not isinstance(question, str):
                    raise ValueError("question must be a string")
                if operation == "choose":
                    criteria = payload.get("criteria")
                    if not isinstance(criteria, dict | list):
                        raise ValueError("criteria must be a list or mapping")
                    answer = await service.choose(
                        question, criteria, state=state, provider_id=provider_id
                    )
                    return sdk.DecisionChoiceAnswer(**asdict(answer))
                return await service.yes_no(
                    question,
                    state=state,
                    provider_id=provider_id,
                    threshold=payload.get("threshold", 0.5),
                    default=payload.get("default"),
                )
        except core.DecisionError as exc:
            raise sdk.DecisionError(str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise InvalidRequest(str(exc)) from exc
        raise NotFound(f"unknown decision operation: {operation}")
