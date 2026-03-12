from __future__ import annotations

from ...decorators import on_command, on_message, require_admin

ADMIN = "admin"


def command(name: str):
    return on_command(name)


def regex(pattern: str):
    return on_message(regex=pattern)


def permission(level):
    if level == ADMIN:
        return require_admin

    def decorator(func):
        return func

    return decorator


class _FilterNamespace:
    command = staticmethod(command)
    regex = staticmethod(regex)
    permission = staticmethod(permission)


filter = _FilterNamespace()

__all__ = ["ADMIN", "command", "regex", "permission", "filter"]
