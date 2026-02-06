from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class NodeExecutionStatus(Enum):
    """Node execution status for tracking in NodeContext."""

    PENDING = "pending"
    EXECUTED = "executed"
    SKIPPED = "skipped"
    FAILED = "failed"
    WAITING = "waiting"


@dataclass
class NodeContext:
    """Single node execution context."""

    node_name: str
    node_uuid: str
    chain_index: int  # Position in chain_config.nodes (fixed)

    status: NodeExecutionStatus = NodeExecutionStatus.PENDING
    input: Any = None  # From upstream EXECUTED node's output
    output: Any = None  # Data to pass downstream


@dataclass
class NodeContextStack:
    """Manages node execution contexts for a chain run."""

    _contexts: list[NodeContext] = field(default_factory=list)

    def push(self, ctx: NodeContext) -> None:
        self._contexts.append(ctx)

    def current(self) -> NodeContext | None:
        return self._contexts[-1] if self._contexts else None

    def get_contexts(
        self,
        *,
        names: set[str] | None = None,
        status: NodeExecutionStatus | None = None,
    ) -> list[NodeContext]:
        """Get contexts filtered by name/status, preserving chain order."""
        contexts: list[NodeContext] = []
        for ctx in self._contexts:
            if status and ctx.status != status:
                continue
            if names and ctx.node_name not in names:
                continue
            contexts.append(ctx)
        return contexts

    def get_outputs(
        self,
        *,
        names: set[str] | None = None,
        status: NodeExecutionStatus | None = NodeExecutionStatus.EXECUTED,
        include_none: bool = False,
    ) -> list[Any]:
        """Get node outputs filtered by name/status, preserving chain order."""
        outputs: list[Any] = []
        for ctx in self.get_contexts(names=names, status=status):
            if ctx.output is None and not include_none:
                continue
            outputs.append(ctx.output)
        return outputs

    def last_executed_output(self) -> Any:
        """Get output from the most recent EXECUTED node.

        Current PENDING node is naturally excluded since it has no output yet.
        """
        outputs = self.get_outputs(
            status=NodeExecutionStatus.EXECUTED,
            include_none=False,
        )
        return outputs[-1] if outputs else None
