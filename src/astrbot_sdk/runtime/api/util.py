import inspect
from functools import wraps
from typing import Callable, Type, Any, get_type_hints, TypeVar, overload
from ..star_runner import StarRunner
from ..types import CallContextFunctionRequest

F = TypeVar("F", bound=Callable[..., Any])


@overload
def rpc_method(func: F) -> F: ...


@overload
def rpc_method(*, return_model: Type[Any] | None = None) -> Callable[[F], F]: ...


def rpc_method(
    func: F | None = None, *, return_model: Type[Any] | None = None
) -> F | Callable[[F], F]:
    """sign as an RPC method.

    Args:
        func: The function to decorate
        return_model: The expected return type/model (e.g., dict, BaseModel, etc.)
                     If not specified, will try to infer from type hints

    Examples:
        @rpc_method
        async def get_config(self) -> dict:
            ...

        @rpc_method(return_model=dict)
        async def get_config(self):
            ...
    """

    def decorator(f: F) -> F:
        # Try to get return type from type hints if not explicitly provided
        _return_model = return_model
        if _return_model is None:
            try:
                hints = get_type_hints(f)
                if "return" in hints:
                    _return_model = hints["return"]
            except Exception:
                pass

        # Store return model as function attribute for potential inspection
        setattr(f, "__return_model__", _return_model)

        @wraps(f)
        async def wrapper(self, *args, **kwargs):
            if not hasattr(self, "runner") or not isinstance(self.runner, StarRunner):
                raise RuntimeError(
                    f"Class {self.__class__.__name__} is not configured for RPC calls."
                )
            method_name = f"{self.__class__.__name__}.{f.__name__}"
            sig = inspect.signature(f)
            bound_args = sig.bind(self, *args, **kwargs)
            bound_args.apply_defaults()
            params = dict(bound_args.arguments)
            params.pop("self")

            runner: StarRunner = getattr(self, "runner")

            result = await runner._call_rpc(
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

            # TODO: Process result based on _return_model if needed
            return result

        # Also store on wrapper for easy access
        setattr(wrapper, "__return_model__", _return_model)
        return wrapper  # type: ignore

    # Support both @rpc_method and @rpc_method(return_model=...)
    if func is None:
        # Called with arguments: @rpc_method(return_model=...)
        return decorator
    else:
        # Called without arguments: @rpc_method
        return decorator(func)
