"""
Python/IPython component
"""

from typing import Any, Protocol


class PythonComponent(Protocol):
    """Python/IPython operations component"""

    async def exec(
        self,
        code: str,
        kernel_id: str | None = None,
        timeout_seconds: int = 30,
        silent: bool = False,
    ) -> dict[str, Any]:
        """Execute Python code"""
        ...
