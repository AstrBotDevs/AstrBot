from dishka import (
    AsyncContainer,
    Container,
    Provider,
    make_async_container,
    make_container,
)

from .base import AstrbotBaseProvider






base_provider: Provider = AstrbotBaseProvider()
async_base_container: AsyncContainer = make_async_container(base_provider)
sync_base_container: Container = make_container(base_provider)

__all__ = [
    "async_base_container",
    "sync_base_container",
]
