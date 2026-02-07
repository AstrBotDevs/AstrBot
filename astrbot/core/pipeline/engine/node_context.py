from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

NODE_PACKET_VERSION = 1


class NodePacketKind(Enum):
    """Supported node packet payload kinds."""

    MESSAGE = "message"
    TEXT = "text"
    OBJECT = "object"


def _infer_node_output_kind(output: Any) -> NodePacketKind:
    from astrbot.core.message.message_event_result import (
        MessageChain,
        MessageEventResult,
    )

    if isinstance(output, MessageEventResult | MessageChain):
        return NodePacketKind.MESSAGE
    if isinstance(output, str):
        return NodePacketKind.TEXT
    return NodePacketKind.OBJECT


@dataclass
class NodePacket:
    """Standard packet transmitted between pipeline nodes."""

    version: int
    kind: NodePacketKind
    data: Any

    def __post_init__(self) -> None:
        if isinstance(self.kind, str):
            self.kind = NodePacketKind(self.kind)

    @classmethod
    def create(cls, output: Any) -> NodePacket:
        if isinstance(output, cls):
            return output
        return cls(
            version=NODE_PACKET_VERSION,
            kind=_infer_node_output_kind(output),
            data=output,
        )


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
    input: NodePacket | None = None  # From upstream EXECUTED node's output
    output: NodePacket | None = None  # Standard node-to-node payload


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
    ) -> list[NodePacket]:
        """Get node outputs filtered by name/status, preserving chain order."""
        outputs: list[NodePacket] = []
        for ctx in self.get_contexts(names=names, status=status):
            output_packet = ctx.output
            if output_packet is None and not include_none:
                continue
            if output_packet is not None:
                outputs.append(output_packet)
        return outputs

    def last_executed_output(self) -> NodePacket | None:
        """Get output from the most recent EXECUTED node.

        Current PENDING node is naturally excluded since it has no output yet.
        """
        outputs = self.get_outputs(
            status=NodeExecutionStatus.EXECUTED,
            include_none=False,
        )
        return outputs[-1] if outputs else None
