import inspect
from loguru import logger
from typing import Any
from .rpc.server.base import JSONRPCServer
from .stars.registry import star_map, star_handlers_registry
from .rpc.jsonrpc import (
    JSONRPCMessage,
    JSONRPCRequest,
    JSONRPCSuccessResponse,
    JSONRPCErrorResponse,
    JSONRPCErrorData,
)
from .rpc.request_helper import RPCRequestHelper
from .types import (
    CallHandlerRequest,
    HandlerStreamStartNotification,
    HandlerStreamUpdateNotification,
    HandlerStreamEndNotification,
)


class HandshakeHandler:
    """Handles the handshake protocol to exchange plugin metadata."""

    async def handle(self, message: JSONRPCRequest) -> JSONRPCSuccessResponse:
        """Build and return handshake response with plugin metadata."""
        payload = {}
        for star_name, star in star_map.items():
            payload[star_name] = star.__dict__
            handlers = []
            for handler_full_name in star.star_handler_full_names:
                handler = star_handlers_registry.get_handler_by_full_name(
                    handler_full_name
                )
                if handler is None:
                    continue
                handlers.append(handler.dump_model())
            payload[star_name]["handlers"] = handlers

        return JSONRPCSuccessResponse(
            jsonrpc="2.0",
            id=message.id,
            result=payload,
        )


class HandlerExecutor:
    """Executes plugin handlers and manages streaming results."""

    def __init__(self, rpc_request_helper: RPCRequestHelper):
        self.rpc_request_helper = rpc_request_helper

    async def execute(self, message: JSONRPCRequest, server: JSONRPCServer):
        """Execute a handler and stream results back to the caller."""
        params = CallHandlerRequest.Params.model_validate(message.params)
        handler_full_name = params.handler_full_name
        event_model = params.event
        args = params.args
        event = event_model.to_event()

        handler = star_handlers_registry.get_handler_by_full_name(handler_full_name)

        if handler is None:
            await self._send_error(
                server, message.id, -32601, f"Handler not found: {handler_full_name}"
            )
            return

        try:
            await self._execute_and_stream(
                server, message.id, handler_full_name, handler.handler(event, **args)
            )
        except Exception as e:
            await self._send_error(server, message.id, -32000, str(e))

    async def _execute_and_stream(
        self,
        server: JSONRPCServer,
        request_id: str | None,
        handler_name: str,
        ready_to_call,
    ):
        """Execute handler and stream results."""
        # Send start notification
        await server.send_message(
            HandlerStreamStartNotification(
                jsonrpc="2.0",
                method="handler_stream_start",
                params=HandlerStreamStartNotification.Params(
                    id=request_id,
                    handler_full_name=handler_name,
                ),
            )
        )

        try:
            if inspect.iscoroutine(ready_to_call):
                result = await ready_to_call
                # Send update notification
                await server.send_message(
                    HandlerStreamUpdateNotification(
                        jsonrpc="2.0",
                        method="handler_stream_update",
                        params=HandlerStreamUpdateNotification.Params(
                            id=request_id,
                            handler_full_name=handler_name,
                            data=result,
                        ),
                    )
                )
            elif inspect.isasyncgen(ready_to_call):
                async for ret in ready_to_call:
                    # Send update notification for each item
                    await server.send_message(
                        HandlerStreamUpdateNotification(
                            jsonrpc="2.0",
                            method="handler_stream_update",
                            params=HandlerStreamUpdateNotification.Params(
                                id=request_id,
                                handler_full_name=handler_name,
                                data=ret,
                            ),
                        )
                    )
        except Exception as e:
            logger.error(f"Error during handler {handler_name}: {e}")
        finally:
            # Send end notification
            await server.send_message(
                HandlerStreamEndNotification(
                    jsonrpc="2.0",
                    method="handler_stream_end",
                    params=HandlerStreamEndNotification.Params(
                        id=request_id,
                        handler_full_name=handler_name,
                    ),
                )
            )

    async def _send_error(
        self, server: JSONRPCServer, request_id: str | None, code: int, message: str
    ):
        """Send an error response."""
        response = JSONRPCErrorResponse(
            jsonrpc="2.0",
            id=request_id,
            error=JSONRPCErrorData(code=code, message=message),
        )
        await server.send_message(response)


class StarRunner:
    """Main runner to handle RPC messages and route them to handlers."""

    def __init__(self, server: JSONRPCServer):
        self.server = server

        self.rpc_request_helper = RPCRequestHelper()
        self.handler_executor = HandlerExecutor(self.rpc_request_helper)
        self.handshake_handler = HandshakeHandler()

    async def call_context_function(
        self, method_name: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        result = await self.rpc_request_helper.call_rpc(
            self.server,
            JSONRPCRequest(
                jsonrpc="2.0",
                id=self.rpc_request_helper._generate_request_id(),
                method="call_context_function",
                params={
                    "name": method_name,
                    "args": params,
                },
            ),
        )
        if isinstance(result, JSONRPCSuccessResponse):
            return result.result
        elif isinstance(result, JSONRPCErrorResponse):
            raise Exception(f"RPC Error {result.error.code}: {result.error.message}")
        else:
            raise Exception("Invalid RPC response")

    async def _handle_messages(self, message: JSONRPCMessage):
        """Route messages to appropriate handlers."""
        if isinstance(message, JSONRPCRequest):
            if message.method == "handshake":
                response = await self.handshake_handler.handle(message)
                await self.server.send_message(response)
            elif message.method == "call_handler":
                await self.handler_executor.execute(message, self.server)
            else:
                logger.warning(f"Unknown method from client: {message.method}")
        elif isinstance(message, (JSONRPCSuccessResponse, JSONRPCErrorResponse)):
            self.rpc_request_helper.resolve_pending_request(message)

    async def run(self):
        self.server.set_message_handler(handler=self._handle_messages)
        await self.server.start()

    async def stop(self):
        await self.server.stop()
