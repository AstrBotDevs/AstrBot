import asyncio
import inspect
from loguru import logger
from .rpc.server.base import JSONRPCServer
from .stars.registry import star_map, star_handlers_registry
from .rpc.jsonrpc import (
    JSONRPCMessage,
    JSONRPCRequest,
    JSONRPCSuccessResponse,
    JSONRPCErrorResponse,
    JSONRPCErrorData,
)
from .types import CallHandlerRequest, HandshakeRequest
from ..api.event.astr_message_event import AstrMessageEvent


class StarRunner:
    def __init__(self, server: JSONRPCServer):
        self.server = server
        self._request_id_counter = 0
        self.pending_requests: dict[str, asyncio.Future] = {}

    def _generate_request_id(self) -> str:
        self._request_id_counter += 1
        return str(self._request_id_counter)

    async def _call_rpc(self, message: JSONRPCMessage):
        if message.id is not None:
            self.pending_requests[message.id] = asyncio.get_event_loop().create_future()
        await self.server.send_message(message)
        if message.id is not None:
            return await self.pending_requests[message.id]

    async def _handle_messages(self, message: JSONRPCMessage):
        if isinstance(message, JSONRPCRequest):
            logger.debug(f"Received RPC request: {message.method}")
            if message.method == "handshake":
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
                response = JSONRPCSuccessResponse(
                    jsonrpc="2.0",
                    id=message.id,
                    result=payload,
                )
                await self.server.send_message(response)
            elif message.method == "call_handler":
                params = CallHandlerRequest.Params.model_validate(message.params)
                handler_full_name = params.handler_full_name
                event_model = params.event
                args = params.args
                event = event_model.to_event()
                logger.debug(f"Parsed event: {event}")

                handler = star_handlers_registry.get_handler_by_full_name(
                    handler_full_name
                )
                logger.debug(f"Invoking handler: {handler_full_name} with args: {args}")
                if handler is None:
                    response = JSONRPCErrorResponse(
                        jsonrpc="2.0",
                        id=message.id,
                        error=JSONRPCErrorData(
                            code=-32601,
                            message=f"Handler not found: {handler_full_name}",
                        ),
                    )
                    await self.server.send_message(response)
                else:
                    try:
                        ready_to_call = handler.handler(event, **args)
                        notification = JSONRPCRequest(
                            jsonrpc="2.0",
                            method="handler_stream_start",
                            params={
                                "id": message.id,
                                "handler_full_name": handler_full_name,
                            },
                        )
                        await self.server.send_message(notification)
                        if inspect.iscoroutine(ready_to_call):
                            result = await ready_to_call
                            notification = JSONRPCRequest(
                                jsonrpc="2.0",
                                method="handler_stream_update",
                                params={
                                    "id": message.id,
                                    "handler_full_name": handler_full_name,
                                    "data": result,
                                },
                            )
                            await self.server.send_message(notification)
                        elif inspect.isasyncgen(ready_to_call):
                            try:
                                async for ret in ready_to_call:
                                    # Send intermediate results as notifications
                                    notification = JSONRPCRequest(
                                        jsonrpc="2.0",
                                        method="handler_stream_update",
                                        params={
                                            "id": message.id,
                                            "handler_full_name": handler_full_name,
                                            "data": ret,
                                        },
                                    )
                                    await self.server.send_message(notification)
                            except Exception as e:
                                logger.error(
                                    f"Error during async generator of handler {handler_full_name}: {e}"
                                )
                    except Exception as e:
                        response = JSONRPCErrorResponse(
                            jsonrpc="2.0",
                            id=message.id,
                            error=JSONRPCErrorData(
                                code=-32000,
                                message=str(e),
                            ),
                        )
                    finally:
                        notification = JSONRPCRequest(
                            jsonrpc="2.0",
                            method="handler_stream_end",
                            params={
                                "id": message.id,
                                "handler_full_name": handler_full_name,
                            },
                        )
                        await self.server.send_message(notification)
        elif isinstance(message, (JSONRPCSuccessResponse, JSONRPCErrorResponse)):
            if message.id in self.pending_requests:
                future = self.pending_requests.pop(message.id)
                if not future.done():
                    future.set_result(message)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.stop()

    async def run(self):
        self.server.set_message_handler(handler=self._handle_messages)
        await self.server.start()

    async def stop(self):
        await self.server.stop()
