"""Import smoke tests for the dashboard OpenAPI route module.

Verifies that the main class and its key method signatures from
``open_api.py`` can be imported without errors.
"""

import inspect

from astrbot.dashboard.routes.open_api import OpenApiRoute


class TestOpenApiRouteClass:
    def test_class_exists(self):
        assert OpenApiRoute is not None

    def test_init_method_signature(self):
        sig = inspect.signature(OpenApiRoute.__init__)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "context" in params
        assert "db" in params
        assert "core_lifecycle" in params
        assert "chat_route" in params

    def test_chat_send_method_is_async(self):
        assert inspect.iscoroutinefunction(OpenApiRoute.chat_send)

    def test_chat_send_method_signature(self):
        sig = inspect.signature(OpenApiRoute.chat_send)
        params = list(sig.parameters.keys())
        assert "self" in params

    def test_get_chat_configs_method_is_async(self):
        assert inspect.iscoroutinefunction(OpenApiRoute.get_chat_configs)

    def test_get_chat_configs_method_signature(self):
        sig = inspect.signature(OpenApiRoute.get_chat_configs)
        params = list(sig.parameters.keys())
        assert "self" in params

    def test_send_message_method_is_async(self):
        assert inspect.iscoroutinefunction(OpenApiRoute.send_message)

    def test_send_message_method_signature(self):
        sig = inspect.signature(OpenApiRoute.send_message)
        params = list(sig.parameters.keys())
        assert "self" in params
