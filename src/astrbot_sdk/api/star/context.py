from abc import ABC
from typing import Any, Callable
from ..basic.conversation_mgr import BaseConversationManager


class Context(ABC):
    conversation_manager: BaseConversationManager

    def __init__(self):
        self._registered_managers: dict[str, Any] = {}
        self._registered_functions: dict[str, Callable] = {}

    def register_component(self, *components: Any) -> None:
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

    def get_registered_function(self, full_name: str) -> Callable | None:
        """Get a registered function by its full name.

        Args:
            full_name: Full name in format "ComponentClassName.method_name"

        Returns:
            The callable function or None if not found
        """

        return self._registered_functions.get(full_name)

    def list_registered_functions(self) -> list[str]:
        """List all registered function names.

        Returns:
            List of full function names in format "ComponentClassName.method_name"
        """
        return list(self._registered_functions.keys())
