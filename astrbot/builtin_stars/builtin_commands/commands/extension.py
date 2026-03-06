from __future__ import annotations

import shlex

from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.core.extensions import ExtensionKind, InstallRequest, InstallResultStatus
from astrbot.core.extensions.runtime import get_extension_orchestrator
from astrbot.core.star.filter.command import GreedyStr


class ExtensionCommands:
    def __init__(self, context: star.Context) -> None:
        self.context = context

    @staticmethod
    def _parse_cli(raw: str) -> tuple[str, str, str, list[str]] | None:
        kind = "plugin"
        provider = ""
        limit = ""
        positional: list[str] = []
        try:
            args = shlex.split(raw)
        except ValueError:
            return None
        i = 0
        while i < len(args):
            token = args[i]
            if token == "--kind" and i + 1 < len(args):
                kind = args[i + 1]
                i += 2
                continue
            if token == "--provider" and i + 1 < len(args):
                provider = args[i + 1]
                i += 2
                continue
            if token == "--limit" and i + 1 < len(args):
                limit = args[i + 1]
                i += 2
                continue
            positional.append(token)
            i += 1
        return kind.strip().lower(), provider.strip().lower(), limit.strip(), positional

    @staticmethod
    def _parse_kind(kind: str) -> ExtensionKind | None:
        try:
            return ExtensionKind(kind)
        except ValueError:
            return None

    @staticmethod
    def _parse_limit(raw_limit: str) -> tuple[int | None, str | None]:
        if not raw_limit:
            return None, None
        try:
            parsed = int(raw_limit)
        except ValueError:
            return None, "Invalid limit. Use a positive integer."
        if parsed <= 0:
            return None, "Invalid limit. Use a positive integer."
        return parsed, None

    async def extend_search(
        self, event: AstrMessageEvent, query: GreedyStr = ""
    ) -> None:
        parsed = self._parse_cli(query)
        if parsed is None:
            event.set_result(
                MessageEventResult().message(
                    "Invalid arguments: unmatched quotes detected."
                )
            )
            return
        kind, provider, raw_limit, positional = parsed
        limit, limit_error = self._parse_limit(raw_limit)
        if limit_error is not None:
            event.set_result(MessageEventResult().message(limit_error))
            return
        kind_enum = self._parse_kind(kind)
        if kind_enum is None:
            event.set_result(
                MessageEventResult().message("Invalid kind. Use: plugin, skill, mcp.")
            )
            return
        query_text = " ".join(positional).strip()
        if not query_text:
            event.set_result(
                MessageEventResult().message(
                    "/extend search <query> [--kind plugin|skill|mcp] [--provider <name>] [--limit <n>]"
                )
            )
            return

        orchestrator = get_extension_orchestrator(self.context)
        candidates = await orchestrator.search(
            kind_enum,
            query_text,
            provider=provider,
            limit=limit,
        )
        if not candidates:
            event.set_result(
                MessageEventResult().message("No extension candidates found.")
            )
            return

        lines = ["Extension search results:"]
        for idx, candidate in enumerate(candidates, start=1):
            lines.append(
                f"{idx}. [{candidate.kind.value}/{candidate.provider}] {candidate.name} -> {candidate.identifier}"
            )
        event.set_result(MessageEventResult().message("\n".join(lines)).use_t2i(False))

    async def extend_install(
        self, event: AstrMessageEvent, target: GreedyStr = ""
    ) -> None:
        parsed = self._parse_cli(target)
        if parsed is None:
            event.set_result(
                MessageEventResult().message(
                    "Invalid arguments: unmatched quotes detected."
                )
            )
            return
        kind, provider, _, positional = parsed
        kind_enum = self._parse_kind(kind)
        if kind_enum is None:
            event.set_result(
                MessageEventResult().message("Invalid kind. Use: plugin, skill, mcp.")
            )
            return
        if not positional:
            event.set_result(
                MessageEventResult().message(
                    "/extend install <id_or_locator> [--kind plugin|skill|mcp] [--provider <name>]"
                )
            )
            return

        install_target = positional[0]
        orchestrator = get_extension_orchestrator(self.context)
        result = await orchestrator.install(
            InstallRequest(
                kind=kind_enum,
                target=install_target,
                provider=provider,
                conversation_id=event.unified_msg_origin,
                requester_id=event.get_sender_id(),
                requester_role=event.role,
            )
        )
        if result.status == InstallResultStatus.PENDING:
            event.set_result(
                MessageEventResult().message(
                    "Install request is pending confirmation.\n"
                    f"operation_id: {result.operation_id}\n"
                    "Reply in chat with a clear confirmation or rejection, "
                    "or use /extend confirm <operation_id> as an admin fallback."
                )
            )
            return

        if result.status == InstallResultStatus.SUCCESS:
            event.set_result(
                MessageEventResult().message("Install completed successfully.")
            )
            return

        if result.status == InstallResultStatus.DENIED:
            event.set_result(
                MessageEventResult().message(f"Install denied: {result.message}")
            )
            return

        event.set_result(
            MessageEventResult().message(f"Install failed: {result.message}")
        )

    async def extend_confirm(
        self, event: AstrMessageEvent, operation_id_or_token: str = ""
    ) -> None:
        if not operation_id_or_token:
            event.set_result(
                MessageEventResult().message("/extend confirm <operation_id>")
            )
            return
        orchestrator = get_extension_orchestrator(self.context)
        result = await orchestrator.confirm(
            operation_id_or_token=operation_id_or_token.strip(),
            actor_id=event.get_sender_id(),
            actor_role=event.role,
        )
        if result.status == InstallResultStatus.SUCCESS:
            event.set_result(
                MessageEventResult().message(
                    "Confirmation accepted, install completed."
                )
            )
            return
        if result.status == InstallResultStatus.DENIED:
            event.set_result(
                MessageEventResult().message(f"Confirmation denied: {result.message}")
            )
            return
        event.set_result(
            MessageEventResult().message(f"Confirmation failed: {result.message}")
        )

    async def extend_deny(
        self, event: AstrMessageEvent, operation_id_or_token: str = ""
    ) -> None:
        if not operation_id_or_token:
            event.set_result(
                MessageEventResult().message("/extend deny <operation_id>")
            )
            return
        orchestrator = get_extension_orchestrator(self.context)
        result = await orchestrator.deny(
            operation_id_or_token=operation_id_or_token.strip(),
            actor_id=event.get_sender_id(),
            actor_role=event.role,
            reason="rejected by command",
        )
        if result.status == InstallResultStatus.DENIED:
            event.set_result(
                MessageEventResult().message("Install operation rejected.")
            )
            return
        event.set_result(
            MessageEventResult().message(f"Reject failed: {result.message}")
        )

    async def extend_pending(self, event: AstrMessageEvent, kind: str = "") -> None:
        kind_enum = None
        if kind:
            kind_enum = self._parse_kind(kind.strip().lower())
            if kind_enum is None:
                event.set_result(
                    MessageEventResult().message(
                        "Invalid kind. Use: plugin, skill, mcp."
                    )
                )
                return

        orchestrator = get_extension_orchestrator(self.context)
        operations = await orchestrator.pending(kind=kind_enum)
        if not operations:
            event.set_result(MessageEventResult().message("No pending operations."))
            return

        lines = ["Pending operations:"]
        for operation in operations[:20]:
            lines.append(
                f"- [{operation.kind}/{operation.provider}] {operation.target} "
                f"(operation_id={operation.operation_id})"
            )
        if len(operations) > 20:
            lines.append(f"... and {len(operations) - 20} more.")
        event.set_result(MessageEventResult().message("\n".join(lines)).use_t2i(False))
