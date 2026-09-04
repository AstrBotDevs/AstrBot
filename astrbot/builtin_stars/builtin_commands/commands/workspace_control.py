"""Administrator commands for approving workspace instruction artifacts."""

from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.core.workspace import resolve_workspace_root_for_umo
from astrbot.core.workspace_control import (
    approve_workspace_control_artifact,
    list_workspace_control_artifacts,
    revoke_workspace_control_artifact,
)


class WorkspaceControlCommands:
    """Manage the current session workspace's approved control artifacts."""

    def __init__(self, context: star.Context) -> None:
        self.context = context

    async def workspace_control(
        self,
        event: AstrMessageEvent,
        action: str = "",
        relative_path: str = "",
        expected_sha256: str = "",
    ) -> None:
        """List, approve, or revoke workspace prompt and Skill instruction files.

        Args:
            event: Incoming administrator command event.
            action: One of ``list``, ``approve``, or ``revoke``.
            relative_path: Workspace-relative control artifact path.
            expected_sha256: Exact digest required for approval.
        """
        action = action.strip().lower()
        try:
            workspace_root = await resolve_workspace_root_for_umo(
                event.unified_msg_origin,
                self.context.get_db(),
            )
            if action == "list":
                artifacts = list_workspace_control_artifacts(workspace_root)
                if not artifacts:
                    message = "No workspace control artifacts found."
                else:
                    message = "\n".join(
                        " | ".join(
                            [
                                item["path"],
                                f"status={item['status']}",
                                f"sha256={item['sha256'] or '-'}",
                                f"approved_sha256={item['approved_sha256'] or '-'}",
                            ]
                        )
                        for item in artifacts
                    )
            elif action == "approve":
                if not relative_path or not expected_sha256:
                    raise ValueError(
                        "Usage: /workspace-control approve <relative-path> <sha256>"
                    )
                approval = approve_workspace_control_artifact(
                    workspace_root,
                    relative_path,
                    expected_sha256=expected_sha256,
                    approved_by=str(event.get_sender_id() or ""),
                )
                message = f"Approved {relative_path} with sha256={approval['sha256']}."
            elif action == "revoke":
                if not relative_path:
                    raise ValueError("Usage: /workspace-control revoke <relative-path>")
                if revoke_workspace_control_artifact(workspace_root, relative_path):
                    message = f"Revoked approval for {relative_path}."
                else:
                    message = f"No approval exists for {relative_path}."
            else:
                message = (
                    "Usage: /workspace-control list | "
                    "/workspace-control approve <relative-path> <sha256> | "
                    "/workspace-control revoke <relative-path>"
                )
        except ValueError as exc:
            message = f"Workspace control failed: {exc}"
        except Exception:
            message = "Workspace control failed. Check the server logs."

        event.set_result(MessageEventResult().message(message).use_t2i(False))
