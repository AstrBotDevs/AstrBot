"""Import smoke tests for send_message tool module."""

import pytest


class TestSendMessageToolImports:
    """Verify send_message.py module can be imported and key classes exist."""

    def test_module_import(self):
        """Import the module without error."""
        from astrbot.core.tools import send_message
        assert send_message is not None

    def test_send_message_to_user_tool(self):
        """SendMessageToUserTool class is present."""
        from astrbot.core.tools.send_message import SendMessageToUserTool
        assert SendMessageToUserTool is not None
        assert SendMessageToUserTool.name == "send_message_to_user"

    def test_singleton_instance(self):
        """SEND_MESSAGE_TO_USER_TOOL singleton exists."""
        from astrbot.core.tools.send_message import SEND_MESSAGE_TO_USER_TOOL
        from astrbot.core.tools.send_message import SendMessageToUserTool
        assert isinstance(SEND_MESSAGE_TO_USER_TOOL, SendMessageToUserTool)

    def test_message_component_typed_dict(self):
        """MessageComponent TypedDict is present."""
        from astrbot.core.tools.send_message import MessageComponent
        assert MessageComponent is not None

    def test_get_all_tools(self):
        """get_all_tools function is present and returns a list."""
        from astrbot.core.tools.send_message import get_all_tools
        tools = get_all_tools()
        assert isinstance(tools, list)
        assert len(tools) == 1
