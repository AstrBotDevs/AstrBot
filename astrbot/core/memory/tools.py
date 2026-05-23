from pydantic import Field
from pydantic.dataclasses import dataclass

from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext, ContextWrapper


@dataclass
class AddMemory(FunctionTool[AstrAgentContext]):
    """Tool for adding memories to user's long-term memory storage"""

    name: str = "astr_add_memory"
    description: str = (
        "Add a new memory to the user's long-term memory storage. "
        "Use this tool only when the user explicitly asks you to remember something, "
        "or when they share stable preferences, identity, or long-term goals that will be useful in future interactions."
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "fact": {
                    "type": "string",
                    "description": (
                        "The concrete memory content to store, such as a user preference, "
                        "identity detail, long-term goal, or stable profile fact."
                    ),
                },
                "memory_type": {
                    "type": "string",
                    "enum": ["persona", "fact", "ephemeral"],
                    "description": (
                        "The relative importance of this memory. "
                        "Use 'persona' for core identity or highly impactful information, "
                        "'fact' for normal long-term preferences, "
                        "and 'ephemeral' for minor or tentative facts."
                    ),
                },
            },
            "required": ["fact", "memory_type"],
        }
    )

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> ToolExecResult:
        """Add a memory to long-term storage

        Args:
            context: Agent context
            **kwargs: Must contain 'fact' and 'memory_type'

        Returns:
            ToolExecResult with success message

        """
        mm = context.context.context.memory_manager
        fact = kwargs.get("fact")
        memory_type = kwargs.get("memory_type", "fact")

        if not fact:
            return "Missing required parameter: fact"

        try:
            # Get owner_id from context
            owner_id = context.context.event.unified_msg_origin

            # Add memory using memory manager
            memory = await mm.add_memory(
                fact=fact,
                owner_id=owner_id,
                memory_type=memory_type,
            )

            return f"Memory added successfully (ID: {memory.mem_id})"

        except Exception as e:
            return f"Failed to add memory: {str(e)}"


@dataclass
class QueryMemory(FunctionTool[AstrAgentContext]):
    """Tool for querying user's long-term memories"""

    name: str = "astr_query_memory"
    description: str = (
        "Query the user's long-term memory storage and return the most relevant memories. "
        "Use this tool when you need user-specific context, preferences, or past facts "
        "that are not explicitly present in the current conversation."
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "top_k": {
                    "type": "integer",
                    "description": (
                        "Maximum number of memories to retrieve after retention-based ranking. "
                        "Typically between 3 and 10."
                    ),
                    "default": 5,
                    "minimum": 1,
                    "maximum": 20,
                },
            },
            "required": [],
        }
    )

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> ToolExecResult:
        """Query memories from long-term storage

        Args:
            context: Agent context
            **kwargs: Optional 'top_k' parameter

        Returns:
            ToolExecResult with formatted memory list

        """
        mm = context.context.context.memory_manager
        top_k = kwargs.get("top_k", 5)

        try:
            # Get owner_id from context
            owner_id = context.context.event.unified_msg_origin

            # Query memories using memory manager
            memories = await mm.query_memory(
                owner_id=owner_id,
                top_k=top_k,
            )

            if not memories:
                return "No memories found for this user."

            # Format memories for output
            formatted_memories = []
            for i, mem in enumerate(memories, 1):
                formatted_memories.append(
                    f"{i}. [{mem.memory_type.upper()}] {mem.fact} "
                    f"(retrieved {mem.retrieval_count} times, "
                    f"last: {mem.last_retrieval_at.strftime('%Y-%m-%d')})"
                )

            result_text = "Retrieved memories:\n" + "\n".join(formatted_memories)
            return result_text

        except Exception as e:
            return f"Failed to query memories: {str(e)}"


ADD_MEMORY_TOOL = AddMemory()
QUERY_MEMORY_TOOL = QueryMemory()
