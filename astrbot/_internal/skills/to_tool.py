"""Skill to Tool converter - converts skills with input_schema to FunctionTool."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from pydantic.dataclasses import dataclass

from astrbot.core.agent.tool import FunctionTool

from .manager import SkillInfo


@dataclass
class SkillToToolConverter:
    """Converter that transforms skills with input_schema into FunctionTool instances.

    This enables skills to be used as callable tools in the agent's function calling
    system, providing a structured way to invoke skills with parameters.
    """

    def can_convert(self, skill: SkillInfo) -> bool:
        """Check if a skill can be converted to a FunctionTool.

        Args:
            skill: The skill to check

        Returns:
            True if the skill has an input_schema, False otherwise
        """
        return skill.input_schema is not None

    def convert(self, skill: SkillInfo) -> FunctionTool:
        """Convert a skill to a FunctionTool.

        Args:
            skill: The skill to convert. Must have an input_schema.

        Returns:
            A FunctionTool with name=f"skill_{skill.name}", description, parameters,
            and a handler that executes the skill.

        Raises:
            ValueError: If the skill does not have an input_schema
        """
        if not self.can_convert(skill):
            raise ValueError(
                f"Skill '{skill.name}' cannot be converted to FunctionTool: "
                "no input_schema defined"
            )

        tool_name = f"skill_{skill.name}"
        tool_description = skill.description or f"Skill: {skill.name}"

        # Create a handler that executes the skill
        # The actual execution is delegated to the skill execution system
        async def skill_handler(
            context: Any = None,
            **kwargs: Any,
        ) -> str | None:
            # This is a placeholder handler that integrates with the skill system
            # The actual skill execution would happen here through the skill manager
            # For now, we return a message indicating the skill should be executed
            # through the standard skill execution flow
            return f"Skill '{skill.name}' execution requested with params: {kwargs}"

        handler: Callable[..., Awaitable[str | None]] = skill_handler

        return FunctionTool(
            name=tool_name,
            description=tool_description,
            parameters=skill.input_schema,  # type: ignore[arg-type]
            handler=handler,
            handler_module_path="astrbot._internal.skills.to_tool",
            active=True,
            is_background_task=False,
            source="skill",
        )
