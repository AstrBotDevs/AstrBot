import inspect
from functools import wraps
from typing import Callable
from ..star_runner import StarRunner
from ..types import CallContextFunctionRequest


def rpc_method(func: Callable) -> Callable:
    """sign as an RPC method."""

    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        if not hasattr(self, "runner") or not isinstance(self.runner, StarRunner):
            raise RuntimeError(
                f"Class {self.__class__.__name__} is not configured for RPC calls."
            )
        method_name = f"{self.__class__.__name__}.{func.__name__}"
        sig = inspect.signature(func)
        bound_args = sig.bind(self, *args, **kwargs)
        bound_args.apply_defaults()
        params = dict(bound_args.arguments)
        params.pop("self")

        runner: StarRunner = getattr(self, "runner")

        return await runner._call_rpc(
            CallContextFunctionRequest(
                jsonrpc="2.0",
                id=runner._generate_request_id(),
                method="call_context_function",
                params=CallContextFunctionRequest.Params(
                    name=method_name,
                    args=params,
                ),
            )
        )

    return wrapper
