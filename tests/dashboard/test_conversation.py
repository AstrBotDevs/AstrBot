"""Import smoke tests for the dashboard conversation route module.

Verifies that the main class and its key method signatures from
``conversation.py`` can be imported without errors.
"""

import inspect

from astrbot.dashboard.routes.conversation import ConversationRoute


class TestConversationRouteClass:
    def test_class_exists(self):
        assert ConversationRoute is not None

    def test_init_method_signature(self):
        sig = inspect.signature(ConversationRoute.__init__)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "context" in params
        assert "db_helper" in params
        assert "core_lifecycle" in params

    def test_list_conversations_method_is_async(self):
        assert inspect.iscoroutinefunction(ConversationRoute.list_conversations)

    def test_list_conversations_method_signature(self):
        sig = inspect.signature(ConversationRoute.list_conversations)
        params = list(sig.parameters.keys())
        assert "self" in params

    def test_del_conv_method_is_async(self):
        assert inspect.iscoroutinefunction(ConversationRoute.del_conv)

    def test_del_conv_method_signature(self):
        sig = inspect.signature(ConversationRoute.del_conv)
        params = list(sig.parameters.keys())
        assert "self" in params

    def test_export_conversations_method_is_async(self):
        assert inspect.iscoroutinefunction(ConversationRoute.export_conversations)

    def test_export_conversations_method_signature(self):
        sig = inspect.signature(ConversationRoute.export_conversations)
        params = list(sig.parameters.keys())
        assert "self" in params
