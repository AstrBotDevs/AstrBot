"""Run host-configured ACP agents through AstrBot's session and turn contract."""

from __future__ import annotations

import asyncio
import json
from contextlib import AsyncExitStack, suppress
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from acp import PROTOCOL_VERSION, Client, RequestError, spawn_agent_process, text_block
from acp.schema import (
    AgentMessageChunk,
    AgentThoughtChunk,
    AllowedOutcome,
    DeniedOutcome,
    PermissionOption,
    RequestPermissionResponse,
    TextContentBlock,
    ToolCallUpdate,
)
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from astrbot.core.agent.events import (
    MessageCompleted,
    ReasoningDelta,
    RuntimeExecutionError,
    TextDelta,
    TurnPrepared,
    TurnResult,
    TurnStatus,
)
from astrbot.core.agent.input import format_input_content
from astrbot.core.agent.output import PlainOutput, ReasoningOutput
from astrbot.core.agent.runtime import AgentRuntime, AgentSession, AgentTurn
from astrbot.core.utils.astrbot_path import (
    get_astrbot_data_path,
    get_astrbot_workspaces_path,
)

if TYPE_CHECKING:
    from acp.interfaces import Agent

    from astrbot.core.agent.runtime import AgentInput
    from astrbot.core.db import BaseDatabase

_SCOPE = "acp_session"
_STATE_KEY = "state"


class AcpLaunchConfig(BaseModel):
    """Command and arguments for a local ACP stdio connection."""

    model_config = ConfigDict(extra="forbid")

    command: str
    args: list[str] = Field(default_factory=list)
    cwd: Path | None = None

    @field_validator("command")
    @classmethod
    def validate_command(cls, value: str) -> str:
        """Require a nonempty executable name or path."""
        if not value.strip():
            raise ValueError("An ACP command is required.")
        return value.strip()

    @field_validator("cwd")
    @classmethod
    def validate_cwd(cls, value: Path | None) -> Path | None:
        """Keep working directories independent of the server's current directory."""
        if value is not None and not value.is_absolute():
            raise ValueError("The ACP working directory must be absolute.")
        return value


class AcpLauncher(AcpLaunchConfig):
    """A legacy host-file entry with optional process environment overrides."""

    env: dict[str, str] = Field(default_factory=dict)


class AcpSessionState(BaseModel):
    """Persist the ACP identity separately from the owning main conversation."""

    umo: str
    launcher: str | None = None
    launch: AcpLaunchConfig | None = None
    remote_id: str | None = None
    cwd: str | None = None
    history: list[dict[str, str]] = Field(default_factory=list)


class AcpClient(Client):
    """Translate text updates for the current prompt and decline tool approvals."""

    def __init__(self) -> None:
        self.turn: AgentTurn | None = None
        self.session_id: str | None = None
        self.parts: list[PlainOutput | ReasoningOutput] = []

    async def request_permission(
        self,
        session_id: str,
        tool_call: ToolCallUpdate,
        options: list[PermissionOption],
        **kwargs: Any,
    ) -> RequestPermissionResponse:
        """Select a one-time rejection when offered, or cancel the request."""
        for option in options:
            if option.kind == "reject_once":
                return RequestPermissionResponse(
                    outcome=AllowedOutcome(
                        outcome="selected", option_id=option.option_id
                    )
                )
        return RequestPermissionResponse(outcome=DeniedOutcome(outcome="cancelled"))

    async def session_update(self, session_id: str, update: Any, **kwargs: Any) -> None:
        """Forward live text and reasoning while ignoring session-load replay."""
        turn = self.turn
        if (
            turn is None
            or session_id != self.session_id
            or not isinstance(update, (AgentMessageChunk, AgentThoughtChunk))
            or not isinstance(update.content, TextContentBlock)
        ):
            return
        reasoning = isinstance(update, AgentThoughtChunk)
        output_type = ReasoningOutput if reasoning else PlainOutput
        delta_type = ReasoningDelta if reasoning else TextDelta
        text = update.content.text
        if self.parts and isinstance(self.parts[-1], output_type):
            self.parts[-1] = output_type(text=(self.parts[-1].text or "") + text)
        else:
            self.parts.append(output_type(text=text))
        turn.emit(
            delta_type(message_id=turn.id, part_index=len(self.parts) - 1, text=text)
        )


class AcpSession(AgentSession):
    """Bind one AstrBot worker to one ACP session and subprocess."""

    def __init__(
        self, runtime: AcpAgentRuntime, session_id: str, state: AcpSessionState
    ) -> None:
        super().__init__(session_id, state.umo, runtime_name="acp")
        self.runtime = runtime
        self._state = state
        self._client = AcpClient()
        self._connection: Agent | None = None
        self._launcher: AcpLaunchConfig | None = None
        self._process: asyncio.subprocess.Process | None = None
        self._stack = AsyncExitStack()

    async def _save(self, state: AcpSessionState) -> None:
        """Persist a detached snapshot before making it visible to readers."""
        await self.runtime.db.insert_preference_or_update(
            _SCOPE, self.id, _STATE_KEY, {"val": state.model_dump(mode="json")}
        )
        self._state = state

    async def _disconnect(self) -> None:
        """Release the transport and leave the persisted session reusable."""
        self._connection = None
        self._launcher = None
        self._process = None
        await self._stack.aclose()

    async def _connect(self, launcher: AcpLaunchConfig) -> Agent:
        """Start a configured subprocess and establish or restore its ACP session.

        Args:
            launcher: Current host-authorized subprocess settings.

        Returns:
            The connection bound to the persisted ACP session.

        Raises:
            RuntimeExecutionError: If the session cannot be safely continued.
        """
        if (
            self._connection is not None
            and self._launcher == launcher
            and self._process is not None
            and self._process.returncode is None
        ):
            return self._connection
        await self._disconnect()
        workspace = (
            launcher.cwd or Path(get_astrbot_workspaces_path()) / f"acp_{self.id}"
        )
        if launcher.cwd is None:
            workspace.mkdir(parents=True, exist_ok=True)
        cwd = str(workspace.resolve())
        if self._state.cwd is not None and self._state.cwd != cwd:
            raise RuntimeExecutionError(
                "acp_workspace_changed",
                "The ACP workspace changed. Spawn a new worker.",
            )
        async with asyncio.timeout(30):
            connection, process = await self._stack.enter_async_context(
                spawn_agent_process(
                    self._client,
                    launcher.command,
                    *launcher.args,
                    cwd=cwd,
                    env=launcher.env if isinstance(launcher, AcpLauncher) else None,
                    transport_kwargs={"stderr": None, "limit": 4 * 1024 * 1024},
                )
            )
            initialized = await connection.initialize(protocol_version=PROTOCOL_VERSION)
            if initialized.protocol_version != PROTOCOL_VERSION:
                raise RuntimeExecutionError(
                    "acp_protocol_version",
                    f"Unsupported ACP protocol version: {initialized.protocol_version}",
                )
            remote_id = self._state.remote_id
            if remote_id is None:
                session = await connection.new_session(cwd=cwd, mcp_servers=[])
                remote_id = session.session_id
                await self._save(
                    self._state.model_copy(update={"remote_id": remote_id, "cwd": cwd})
                )
            else:
                capabilities = initialized.agent_capabilities
                session_capabilities = (
                    capabilities.session_capabilities if capabilities else None
                )
                if session_capabilities and session_capabilities.resume is not None:
                    await connection.resume_session(
                        session_id=remote_id, cwd=cwd, mcp_servers=[]
                    )
                elif capabilities and capabilities.load_session:
                    await connection.load_session(
                        session_id=remote_id, cwd=cwd, mcp_servers=[]
                    )
                else:
                    raise RuntimeExecutionError(
                        "acp_resume_unsupported",
                        "This ACP agent cannot restore a session after its process exits. Spawn a new worker.",
                    )
            self._client.session_id = remote_id
        self._connection, self._process, self._launcher = connection, process, launcher
        return connection

    async def execute_turn(self, turn: AgentTurn) -> TurnResult:
        """Send the admitted worker input and persist the completed exchange."""
        if not turn.input.permissions.is_admin:
            raise RuntimeExecutionError(
                "acp_permission_denied", "ACP workers require an administrator."
            )
        prompt = format_input_content(turn.input.content or ())
        if not prompt:
            raise RuntimeExecutionError(
                "acp_empty_prompt", "The ACP worker requires a prompt."
            )
        self._client.parts.clear()
        try:
            launcher = self._state.launch
            if launcher is None:
                assert self._state.launcher is not None
                launcher = self.runtime.load_launcher(self._state.launcher)
            connection = await self._connect(launcher)
            assert self._client.session_id is not None
            turn.emit(
                TurnPrepared(
                    user_prompt=prompt,
                    model=self._state.launcher or Path(launcher.command).name,
                    streaming=True,
                )
            )
            self._client.turn = turn
            response = await connection.prompt(
                session_id=self._client.session_id, prompt=[text_block(prompt)]
            )
        except (RequestError, OSError, TimeoutError, EOFError, ValueError) as exc:
            await self._disconnect()
            if isinstance(exc, RequestError) and exc.code == -32000:
                raise RuntimeExecutionError(
                    "acp_auth_required",
                    "Authenticate the ACP agent on the AstrBot host first.",
                ) from None
            raise RuntimeExecutionError(
                "acp_connection_failed",
                f"ACP process failed ({type(exc).__name__}). Check the command, working directory, and server logs.",
            ) from None
        except BaseException:
            await self._disconnect()
            raise
        finally:
            self._client.turn = None

        status = (
            TurnStatus.CANCELLED
            if response.stop_reason == "cancelled" or turn.cancellation_requested
            else TurnStatus.COMPLETED
        )
        result = TurnResult(
            status=status,
            content=tuple(self._client.parts),
            reason=response.stop_reason,
        )
        if result.content:
            turn.emit(
                MessageCompleted(
                    message_id=turn.id, content=result.content, status=status
                )
            )
        if status == TurnStatus.COMPLETED:
            await self._save(
                self._state.model_copy(
                    update={
                        "history": [
                            *self._state.history,
                            {"role": "user", "content": prompt},
                            {"role": "assistant", "content": result.text},
                        ]
                    }
                )
            )
        return result

    async def cancel_turn(self, turn: AgentTurn) -> None:
        """Notify ACP first and give it time to settle before local cancellation."""
        if self._client.turn is turn and self._connection and self._client.session_id:
            with suppress(TimeoutError, RequestError, OSError, EOFError):
                async with asyncio.timeout(2):
                    await self._connection.cancel(session_id=self._client.session_id)
                    await turn.result()

    async def history(self) -> list[dict]:
        """Return the committed AstrBot transcript, detached from mutable state."""
        return [item.copy() for item in self._state.history]

    async def close(self) -> None:
        """Cancel queued and active work, then release the subprocess."""
        await super().close()
        await self._disconnect()


class AcpAgentRuntime(AgentRuntime):
    """Provide the ACP runtime for specialized subagents."""

    def __init__(self, db: BaseDatabase, launcher_path: Path | None = None) -> None:
        self.db = db
        self._launcher_path = (
            launcher_path or Path(get_astrbot_data_path()) / "acp_agents.json"
        )
        self._sessions: dict[str, AcpSession] = {}
        self._opening = asyncio.Lock()
        self._closed = False

    def load_launcher(self, name: str) -> AcpLauncher:
        """Resolve and validate an operator-managed launch entry.

        Args:
            name: Launcher name from the stored AgentConfig.

        Returns:
            Validated host-side settings, including the process environment.

        Raises:
            ValueError: If the file or the named entry is unavailable or invalid.
        """
        try:
            launchers = json.loads(self._launcher_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise ValueError(
                "Configure ACP launchers in data/acp_agents.json first."
            ) from None
        except (OSError, ValueError):
            raise ValueError("Unable to read the ACP launcher configuration.") from None
        if not isinstance(launchers, dict) or name not in launchers:
            raise ValueError(f"Unknown ACP launcher: {name!r}")
        try:
            launcher = AcpLauncher.model_validate(launchers[name])
        except ValidationError:
            raise ValueError(
                f"Invalid host configuration for ACP launcher {name!r}."
            ) from None
        return launcher

    def default_config(self, *, delegated: bool = False) -> dict:
        """Provide empty stdio settings for the specialized Agent editor."""
        return {"command": "", "args": [], "cwd": None}

    def normalize_config(self, config: dict, *, delegated: bool = False) -> dict:
        """Validate a specialized worker's stdio settings or legacy launcher."""
        if not delegated:
            raise ValueError("ACP is available for specialized subagents.")
        if set(config) == {"launcher"}:
            launcher = config["launcher"]
            if not isinstance(launcher, str) or not launcher.strip():
                raise ValueError("An ACP launcher name is required.")
            launcher = launcher.strip()
            self.load_launcher(launcher)
            return {"launcher": launcher}
        try:
            return AcpLaunchConfig.model_validate(config).model_dump(mode="json")
        except ValidationError as exc:
            issue = exc.errors(include_input=False)[0]
            field = ".".join(map(str, issue["loc"]))
            raise ValueError(
                f"Invalid ACP configuration ({field}): {issue['msg']}"
            ) from None

    async def open_session(
        self,
        umo: str,
        *,
        session_id: str | None = None,
        options: dict | None = None,
        input: AgentInput | None = None,
    ) -> AgentSession:
        """Create a specialized worker or reopen its persisted runtime identity."""
        if (options or {}).get("profile") != "subagent":
            raise ValueError("ACP is available for specialized subagents.")
        async with self._opening:
            if self._closed:
                raise ValueError("The ACP runtime is closed.")
            if session_id is not None:
                existing = self._sessions.get(session_id)
                if existing is not None and not existing.closed:
                    if existing.umo != umo:
                        raise ValueError(
                            "ACP session belongs to a different message origin."
                        )
                    return existing
                record = await self.db.get_preference(_SCOPE, session_id, _STATE_KEY)
                if record is None:
                    raise ValueError("ACP session does not exist.")
                state = AcpSessionState.model_validate(record.value["val"])
                if state.umo != umo:
                    raise ValueError(
                        "ACP session belongs to a different message origin."
                    )
                session = AcpSession(self, session_id, state)
            else:
                if (
                    input is None
                    or not input.permissions.is_admin
                    or input.event.unified_msg_origin != umo
                ):
                    raise ValueError("ACP workers require an administrator.")
                assert options is not None
                config = self.normalize_config(
                    options.get("config", {}), delegated=True
                )
                state = AcpSessionState(
                    umo=umo,
                    launcher=config.get("launcher"),
                    launch=AcpLaunchConfig.model_validate(config)
                    if "launcher" not in config
                    else None,
                )
                session = AcpSession(self, uuid4().hex, state)
                await session._save(state)
            self._sessions[session.id] = session
            return session

    async def close(self) -> None:
        """Release all ACP sessions and prohibit new workers."""
        async with self._opening:
            self._closed = True
            sessions = list(self._sessions.values())
            self._sessions.clear()
        await asyncio.gather(*(session.close() for session in sessions))
