from abc import ABC
from typing import Any, Callable
from ..basic.conversation_mgr import BaseConversationManager
from astr_agent_sdk.tool import ToolSet, FunctionTool
from astr_agent_sdk.message import Message
from ..provider.entities import LLMResponse
from ..message.chain import MessageChain


class Context(ABC):
    conversation_manager: BaseConversationManager
    persona_manager: Any

    def __init__(self):
        self._registered_managers: dict[str, Any] = {}
        self._registered_functions: dict[str, Callable] = {}

    def _register_component(self, *components: Any) -> None:
        """Register a components instance and its public methods.

        This allows the components's methods to be called via RPC using the pattern:
        ComponentClassName.method_name

        Args:
            components: The components instance to register
        """
        for component in components:
            class_name = component.__class__.__name__
            self._registered_managers[class_name] = component

            # Register all public methods (not starting with _)
            for attr_name in dir(component):
                if not attr_name.startswith("_"):
                    attr = getattr(component, attr_name)
                    if callable(attr):
                        full_name = f"{class_name}.{attr_name}"
                        self._registered_functions[full_name] = attr

    async def llm_generate(
        self,
        chat_provider_id: str,
        prompt: str | None = None,
        image_urls: list[str] | None = None,
        tools: ToolSet | None = None,
        system_prompt: str | None = None,
        contexts: list[Message] | list[dict] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Call the LLM to generate a response. The method will not automatically execute tool calls. If you want to use tool calls, please use `tool_loop_agent()`.

        Args:
            chat_provider_id: The chat provider ID to use.
            prompt: The prompt to send to the LLM, if `contexts` and `prompt` are both provided, `prompt` will be appended as the last user message
            image_urls: List of image URLs to include in the prompt, if `contexts` and `prompt` are both provided, `image_urls` will be appended to the last user message
            tools: ToolSet of tools available to the LLM
            system_prompt: System prompt to guide the LLM's behavior, if provided, it will always insert as the first system message in the context
            contexts: context messages for the LLM
            **kwargs: Additional keyword arguments for LLM generation, OpenAI compatible

        Raises:
            ChatProviderNotFoundError: If the specified chat provider ID is not found
            Exception: For other errors during LLM generation
        """
        ...

    async def tool_loop_agent(
        self,
        chat_provider_id: str,
        prompt: str | None = None,
        image_urls: list[str] | None = None,
        tools: ToolSet | None = None,
        system_prompt: str | None = None,
        contexts: list[Message] | list[dict] | None = None,
        max_steps: int = 30,
        **kwargs: Any,
    ) -> LLMResponse:
        """Run an agent loop that allows the LLM to call tools iteratively until a final answer is produced.

        Args:
            chat_provider_id: The chat provider ID to use.
            prompt: The prompt to send to the LLM, if `contexts` and `prompt` are both provided, `prompt` will be appended as the last user message
            image_urls: List of image URLs to include in the prompt, if `contexts` and `prompt` are both provided, `image_urls` will be appended to the last user message
            tools: ToolSet of tools available to the LLM
            system_prompt: System prompt to guide the LLM's behavior, if provided, it will always insert as the first system message in the context
            contexts: context messages for the LLM
            max_steps: Maximum number of tool calls before stopping the loop
            **kwargs: Additional keyword arguments for LLM generation, OpenAI compatible

        Returns:
            The final LLMResponse after tool calls are completed.

        Raises:
            ChatProviderNotFoundError: If the specified chat provider ID is not found
            Exception: For other errors during LLM generation
        """
        ...

    async def send_message(
        self,
        session: str,
        message_chain: MessageChain,
    ) -> None:
        """Send a message to a user or group.

        Args:
            session: unified message origin(umo), this can represent a user or group in a specific platform instance
            message_chain: The MessageChain to send

        Raises:
            Exception: If sending the message fails
        """
        ...

    async def add_llm_tools(self, *tools: FunctionTool) -> None:
        """Add tools to the LLM's toolset.

        Args:
            tools: The FunctionTool instances to add
        """
        ...

    async def put_kv_data(
        self,
        key: str,
        value: dict,
    ) -> None:
        """Insert a key-value pair data. The data will permanently stored in AstrBot unless user explicitly deleted.

        Args:
            key: The key to insert
            value: The value to insert
        """
        ...

    async def get_kv_data(self, key: str) -> dict | None:
        """Get a value by key from the key-value store.

        Args:
            key: The key to retrieve

        Returns:
            The value associated with the key, or None if not found
        """
        ...

    async def delete_kv_data(self, key: str) -> None:
        """Delete a key-value pair by key.

        Args:
            key: The key to delete
        """
        ...
