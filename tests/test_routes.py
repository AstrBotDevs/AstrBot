from unittest.mock import Mock

from astrbot.dashboard.routes.route import Response, Route, RouteContext


class TestResponse:
    """Test cases for the Response class."""

    def test_response_ok_with_data(self):
        """Test Response.ok() with data."""
        data = {"key": "value"}
        response = Response.ok(data, "Success message")

        assert response.status == "ok"
        assert response.message == "Success message"
        assert response.data == data

    def test_response_ok_with_kwargs(self):
        """Test Response.ok() with keyword arguments."""
        response = Response.ok(username="test", token="abc123")

        assert response.status == "ok"
        assert response.message == "ok"
        assert response.data == {"username": "test", "token": "abc123"}

    def test_response_ok_empty_kwargs(self):
        """Test Response.ok() with empty kwargs should return empty dict."""
        response = Response.ok()

        assert response.status == "ok"
        assert response.message == "ok"
        assert response.data is None

    def test_response_error(self):
        """Test Response.error()."""
        response = Response.error("Error message")

        assert response.status == "error"
        assert response.message == "Error message"
        assert response.data is None

    def test_response_error_default_message(self):
        """Test Response.error() with default message."""
        response = Response.error()

        assert response.status == "error"
        assert response.message == "error"
        assert response.data is None

    def test_response_sse(self):
        """Test Response.sse() static method."""
        from fastapi.responses import StreamingResponse

        async def mock_stream():
            yield "data: test\n\n"

        # Create a proper async iterable
        class MockAsyncIterable:
            def __init__(self, generator):
                self.generator = generator

            def __aiter__(self):
                return self.generator()

        sse_response = Response.sse(MockAsyncIterable(mock_stream))

        assert isinstance(sse_response, StreamingResponse)
        assert sse_response.headers["Content-Type"] == "text/event-stream"
        assert sse_response.headers["Cache-Control"] == "no-cache"

    def test_response_sse_with_custom_headers(self):
        """Test Response.sse() with custom headers."""
        from fastapi.responses import StreamingResponse

        async def mock_stream():
            yield "data: test\n\n"

        # Create a proper async iterable
        class MockAsyncIterable:
            def __init__(self, generator):
                self.generator = generator

            def __aiter__(self):
                return self.generator()

        custom_headers = {"X-Custom": "value"}
        sse_response = Response.sse(MockAsyncIterable(mock_stream), custom_headers)

        assert isinstance(sse_response, StreamingResponse)
        assert sse_response.headers["X-Custom"] == "value"
        assert sse_response.headers["Content-Type"] == "text/event-stream"


class TestRoute:
    """Test cases for the Route base class."""

    def test_route_initialization(self):
        """Test Route initialization."""
        mock_config = Mock()
        mock_app = Mock()
        context = RouteContext(config=mock_config, app=mock_app)

        route = Route(context)

        assert route.app == mock_app
        assert route.config == mock_config

    def test_route_register_routes_dict_format(self):
        """Test register_routes with dictionary format."""
        mock_config = Mock()
        mock_app = Mock()
        context = RouteContext(config=mock_config, app=mock_app)

        # Create a test route class
        class TestRoute(Route):
            def __init__(self, context):
                super().__init__(context)
                self.routes = {
                    "/test": ("GET", lambda: "test"),
                    "/test2": ("POST", lambda: "test2"),
                }
                self.register_routes()

        route = TestRoute(context)

        # Verify routes were registered
        assert mock_app.add_api_route.call_count == 2
        mock_app.add_api_route.assert_any_call("/api/test", route.routes["/test"][1], methods=["GET"])
        mock_app.add_api_route.assert_any_call("/api/test2", route.routes["/test2"][1], methods=["POST"])

    def test_route_register_routes_mixed_methods(self):
        """Test register_routes with multiple methods for same route."""
        mock_config = Mock()
        mock_app = Mock()
        context = RouteContext(config=mock_config, app=mock_app)

        # Create a test route class
        class TestRoute(Route):
            def __init__(self, context):
                super().__init__(context)
                self.routes = {
                    "/test": [
                        ("GET", lambda: "get"),
                        ("POST", lambda: "post"),
                    ]
                }
                self.register_routes()

        route = TestRoute(context)

        # Verify routes were registered
        assert mock_app.add_api_route.call_count == 2
        mock_app.add_api_route.assert_any_call("/api/test", route.routes["/test"][0][1], methods=["GET"])
        mock_app.add_api_route.assert_any_call("/api/test", route.routes["/test"][1][1], methods=["POST"])
