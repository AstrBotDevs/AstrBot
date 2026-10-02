from collections.abc import Callable
from typing import TypeVar

_F = TypeVar("_F", bound=Callable[..., object])

def deprecated(*args: object, **kwargs: object) -> Callable[[_F], _F]: ...
