from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class OpenModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class DataFileContentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(max_length=1024 * 1024)
    expected_etag: str | None = Field(default=None, max_length=256)
    encoding: Literal["utf-8"] = "utf-8"


class DataFileEntryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=4096)
    type: Literal["file", "directory"] = "file"
    content: str = Field(default="", max_length=1024 * 1024)


class DataFileMoveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_path: str = Field(min_length=1, max_length=4096)
    target_path: str = Field(min_length=1, max_length=4096)


class DataFileDeleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=4096)
    recursive: bool = False


class PluginDashboardSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_version: Literal[1]
    expected_generation: str = Field(min_length=1, max_length=128)


class PluginDashboardActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_version: Literal[1]
    instance_id: str = Field(min_length=1, max_length=128)
    expected_generation: str = Field(min_length=1, max_length=128)
    payload: Any


class PluginDashboardFileRequest(PluginDashboardActionRequest):
    expected_disposition: Literal["inline", "attachment"]


class PluginDashboardUploadMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_version: Literal[1]
    instance_id: str = Field(min_length=1, max_length=128)
    expected_generation: str = Field(min_length=1, max_length=128)
    fields: Any


def _reject_legacy_mcp_request_fields(
    value: Any,
    *,
    forbidden: tuple[str, ...],
) -> Any:
    if not isinstance(value, dict):
        return value
    legacy_fields = [key for key in forbidden if key in value]
    if legacy_fields:
        fields = ", ".join(sorted(legacy_fields))
        raise ValueError(f"Legacy MCP request fields are not supported: {fields}")
    return value


_DEPRECATED_PERMISSION_CONFIG_FIELDS = frozenset(
    {"admins_id", "tool_permissions", "disable_builtin_commands"}
)


def _reject_deprecated_permission_config_fields(value: Any) -> Any:
    """Reject removed permission fields at the Dashboard config boundary."""
    if not isinstance(value, dict):
        return value
    fields = sorted(_DEPRECATED_PERMISSION_CONFIG_FIELDS.intersection(value))
    if fields:
        joined = ", ".join(fields)
        raise ValueError(
            f"Deprecated permission config fields are not supported: {joined}"
        )
    return value


class ConfigProfileCreateRequest(BaseModel):
    name: str | None = None
    config: dict[str, Any] | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_deprecated_permission_fields(cls, value: Any) -> Any:
        if isinstance(value, dict):
            _reject_deprecated_permission_config_fields(value.get("config"))
        return value


class ConfigContentRequest(OpenModel):
    @model_validator(mode="before")
    @classmethod
    def reject_deprecated_permission_fields(cls, value: Any) -> Any:
        return _reject_deprecated_permission_config_fields(value)


class RenameRequest(BaseModel):
    name: str | None = None


class EnabledPatch(BaseModel):
    enabled: bool


class ApiKeyCreateRequest(OpenModel):
    name: str | None = None
    scopes: list[str] | None = None
    expires_in_days: int | None = None


class ApiKeyIdRequest(BaseModel):
    key_id: str


class LoginRequest(OpenModel):
    username: str | None = None
    password: str | None = None
    code: str | None = None
    trust_device_flag: bool | None = None


class AuthSetupRequest(OpenModel):
    username: str | None = None
    password: str | None = None
    confirm_password: str | None = None


class TotpSetupRequest(OpenModel):
    secret: str | None = None
    code: str | None = None


class AccountUpdateRequest(OpenModel):
    password: str | None = None
    new_password: str | None = None
    confirm_password: str | None = None
    new_username: str | None = None


class DashboardAccountCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=1024)
    role: Literal["operator", "root"] = "operator"


class DashboardAccountUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str | None = Field(default=None, min_length=3, max_length=255)
    password: str | None = Field(default=None, min_length=8, max_length=1024)
    is_active: bool | None = None


class AuthorizationBindingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject_id: str = Field(min_length=3, max_length=512)
    role: Literal[
        "root",
        "operator",
        "instance_operator",
        "session_owner",
        "session_admin",
        "member",
    ]
    scope_type: Literal["global", "instance", "session", "resource"]
    scope_id: str = Field(min_length=1, max_length=4096)
    config_id: str | None = Field(default=None, max_length=128)
    expires_at: datetime | None = None


class AuthorizationStepUpRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str = Field(min_length=1, max_length=128)
    resource_type: str = Field(min_length=1, max_length=128)
    resource_id: str = Field(min_length=1, max_length=4096)
    config_id: str | None = Field(default=None, max_length=128)
    password: str | None = Field(default=None, max_length=1024)
    code: str | None = Field(default=None, max_length=128)


class WebChatStepUpRequest(BaseModel):
    """Fresh Dashboard factor for the current WebChat session's tools."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1, max_length=512)
    password: str | None = Field(default=None, max_length=1024)
    code: str | None = Field(default=None, max_length=128)


class AuthorizationBindingBatchRevokeRequest(BaseModel):
    """One exact binding set plus an optional factor for issuing step-up."""

    model_config = ConfigDict(extra="forbid")

    binding_ids: list[str] = Field(min_length=1, max_length=100)
    password: str | None = Field(default=None, max_length=1024)
    code: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def validate_binding_ids(self) -> AuthorizationBindingBatchRevokeRequest:
        if any(
            not binding_id or len(binding_id) > 128 for binding_id in self.binding_ids
        ):
            raise ValueError("Invalid binding id")
        if len(set(self.binding_ids)) != len(self.binding_ids):
            raise ValueError("Binding IDs must be unique")
        return self


class BackupUploadInitRequest(OpenModel):
    filename: str | None = None
    total_size: int | None = None


class BackupUploadSessionRequest(OpenModel):
    upload_id: str | None = None


class BackupImportRequest(OpenModel):
    confirmed: bool | None = None


class BackupRenameRequest(OpenModel):
    new_name: str | None = None


class UpdateRequest(OpenModel):
    version: str | None = None
    proxy: str | None = None
    reboot: bool | None = None
    progress_id: str | None = None


class PipInstallRequest(OpenModel):
    package: str | None = None
    mirror: str | None = None


class ChatProjectRequest(OpenModel):
    project_id: str | None = None
    title: str | None = None
    emoji: str | None = None
    description: str | None = None


class ChatProjectSessionRequest(OpenModel):
    project_id: str | None = None
    session_id: str | None = None


class ChatSessionBatchDeleteRequest(OpenModel):
    session_ids: list[str]


class ChatSessionPatchRequest(OpenModel):
    display_name: str | None = None


class ChatMessagePatchRequest(OpenModel):
    content: dict[str, Any]


class ChatMessageRegenerateRequest(OpenModel):
    selected_provider: str | None = None
    selected_model: str | None = None
    enable_streaming: bool | None = None
    webchat_step_up_tokens: dict[str, str] | None = Field(
        default=None,
        alias="_webchat_step_up_tokens",
        description="Internal WebUI in-memory WebChat step-up proofs.",
        json_schema_extra={"writeOnly": True},
    )


class ChatThreadCreateRequest(OpenModel):
    session_id: str
    parent_message_id: str | int
    selected_text: str


class ChatThreadMessageRequest(OpenModel):
    message: Any
    selected_provider: str | None = None
    selected_model: str | None = None
    enable_streaming: bool | None = None
    webchat_step_up_tokens: dict[str, str] | None = Field(
        default=None,
        alias="_webchat_step_up_tokens",
        description="Internal WebUI in-memory WebChat step-up proofs.",
        json_schema_extra={"writeOnly": True},
    )


class CronJobRequest(OpenModel):
    pass


class CommandUpdateRequest(BaseModel):
    enabled: bool | None = None
    alias: str | None = None
    aliases: list[str] | None = None
    action: str | None = Field(default=None, min_length=3, max_length=128)


class CommandToggleRequest(BaseModel):
    command_id: str
    enabled: bool


class BuiltinCommandBulkToggleRequest(BaseModel):
    enabled: bool


class CommandRenameRequest(BaseModel):
    command_id: str
    new_name: str
    aliases: list[str] | None = None


class CommandPermissionRequest(BaseModel):
    command_id: str
    action: str


class SubAgentConfigRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    main_enable: bool | None = None
    remove_main_duplicate_tools: bool | None = None
    agents: list[dict[str, Any]] | None = None


class TraceSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


class StorageCleanupRequest(BaseModel):
    target: str = "all"


class GhProxyTestRequest(BaseModel):
    proxy_url: str | None = None


class OpenApiChatRequest(OpenModel):
    message: Any = None
    session_id: str | None = None
    username: str | None = Field(
        default=None,
        description=(
            "Caller-declared WebChat sender/session owner. This value is used "
            "as the message sender identity and may participate in "
            "sender-ID-based permission checks; trusted integrations should "
            "validate or map it before accepting end-user input."
        ),
    )
    config_id: str | None = None
    config_name: str | None = None
    platform_id: str | None = None
    enable_streaming: bool | None = None
    webchat_step_up_tokens: dict[str, str] | None = Field(
        default=None,
        alias="_webchat_step_up_tokens",
        description="Internal WebUI in-memory WebChat step-up proofs.",
        json_schema_extra={"writeOnly": True},
    )


class ImMessageRequest(OpenModel):
    umo: str | None = None
    message: Any = None
    type: str | None = None


class KnowledgeBaseRequest(OpenModel):
    kb_name: str | None = Field(None, alias="name")
    description: str | None = None
    emoji: str | None = None
    embedding_provider_id: str | None = None
    rerank_provider_id: str | None = None
    chunk_size: int | None = None
    chunk_overlap: int | None = None
    top_k_dense: int | None = None
    top_k_sparse: int | None = None
    top_m_final: int | None = None

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    def canonical_payload(self) -> dict[str, Any]:
        """Return the service-facing knowledge base payload.

        Returns:
            Dictionary accepted by KnowledgeBaseService.
        """
        return self.model_dump(
            exclude_unset=True,
            include={
                "kb_name",
                "description",
                "emoji",
                "embedding_provider_id",
                "rerank_provider_id",
                "chunk_size",
                "chunk_overlap",
                "top_k_dense",
                "top_k_sparse",
                "top_m_final",
            },
            by_alias=False,
        )


class KnowledgeBaseCreateRequest(KnowledgeBaseRequest):
    model_config = ConfigDict(
        populate_by_name=True,
        extra="allow",
        json_schema_extra={"required": ["kb_name", "embedding_provider_id"]},
    )


class KnowledgeBaseImportRequest(OpenModel):
    documents: list[dict[str, Any]] | None = None
    batch_size: int | None = None
    tasks_limit: int | None = None
    max_retries: int | None = None


class KnowledgeBaseUrlImportRequest(OpenModel):
    url: str | None = None
    urls: list[str] | None = None
    chunk_size: int | None = None
    chunk_overlap: int | None = None
    batch_size: int | None = None
    tasks_limit: int | None = None
    max_retries: int | None = None


class KnowledgeBaseRetrieveRequest(OpenModel):
    query: str | None = None
    top_k: int | None = None
    threshold: float | None = None
    rerank: bool | None = None


class MemoryFactCreateRequest(OpenModel):
    person_id: str
    chat_id: str
    fact_text: str
    scope_id: str | None = None
    fact_type: str | None = None
    source_message_id: str | None = None
    evidence_message_ids: list[str] | None = None
    confidence: float | None = None
    reason: str | None = None


class MemoryFactPatchRequest(OpenModel):
    fact_text: str | None = None
    fact_type: str | None = None
    confidence: float | None = None
    reason: str | None = None


class MemoryFactActionRequest(OpenModel):
    reason: str | None = None


class MemoryProfileRefreshRequest(OpenModel):
    chat_scope: str | None = None
    scope_id: str | None = None
    chat_id: str | None = None


class ToolEnabledRequest(BaseModel):
    enabled: bool


class McpServerRequest(BaseModel):
    """The strict modern MCP server configuration accepted by Dashboard APIs."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    active: bool | None = None
    transport: Literal["stdio", "streamable_http"] | None = None
    command: str | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None
    url: str | None = None
    headers: dict[str, str] | None = None
    allow_private_network: bool | None = None
    connect_timeout_seconds: float | None = None
    read_timeout_seconds: float | None = None
    terminate_on_close: bool | None = None
    auth_ref: str | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_legacy_fields(cls, value: Any) -> Any:
        return _reject_legacy_mcp_request_fields(
            value,
            forbidden=(
                "enabled",
                "mcpServers",
                "mcp_server_config",
                "oldName",
                "type",
                "sse",
                "sse_read_timeout",
                "session_read_timeout",
                "timeout",
                "config",
            ),
        )


class ModelScopeSyncRequest(BaseModel):
    access_token: str | None = None


class McpResourceReadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    uri: str = Field(min_length=1, max_length=4096)


class McpPromptGetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    arguments: dict[str, str] | None = None


class McpCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference: dict[str, Any]
    argument: dict[str, str]
    context_arguments: dict[str, str] | None = None


class T2iTemplateRequest(BaseModel):
    name: str | None = None
    content: str | None = None


class T2iActiveTemplateRequest(BaseModel):
    name: str


class PersonaRequest(OpenModel):
    persona_id: str | None = None
    system_prompt: str | None = None
    begin_dialogs: list[Any] | None = None
    tools: list[str] | None = None
    skills: list[str] | None = None
    custom_error_message: str | None = None
    folder_id: str | None = None
    sort_order: int | None = None


class PersonaMoveRequest(BaseModel):
    persona_id: str
    folder_id: str | None = None


class PersonaReorderItem(BaseModel):
    id: str
    type: Literal["persona", "folder"]
    sort_order: int


class PersonaReorderRequest(BaseModel):
    items: list[PersonaReorderItem]


class PersonaFolderRequest(OpenModel):
    folder_id: str | None = None
    name: str | None = None
    parent_id: str | None = None
    description: str | None = None
    sort_order: int | None = None


class SkillUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active: bool


class SkillNeoRequest(OpenModel):
    skill_name: str | None = None
    skill_key: str | None = None
    name: str | None = None
    candidate_id: str | None = None
    release_id: str | None = None
    profile_id: str | None = None
    payload: dict[str, Any] | None = None


class ConversationRef(BaseModel):
    user_id: str
    cid: str


class ConversationPatchRequest(OpenModel):
    user_id: str | None = None
    title: str | None = None
    persona_id: str | None = None


class ConversationMessagesReplaceRequest(OpenModel):
    user_id: str | None = None
    history: list[Any] | str | None = None
    messages: list[Any] | str | None = None


class ConversationBatchDeleteRequest(BaseModel):
    conversations: list[ConversationRef]


class ConversationExportRequest(BaseModel):
    conversations: list[ConversationRef]


class BotConfigRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config: dict[str, Any]


class BotActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_name: str
    payload: dict[str, Any] | None = None


class BotRegistrationRequest(OpenModel):
    action: Literal["start", "poll"] | str | None = None
    platform_config: dict[str, Any] | None = None
    registration_code: str | None = None
    device_code: str | None = None


class ProviderSourceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config: dict[str, Any]


class ProviderConfigRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config: dict[str, Any]


class ProviderEmbeddingDimensionRequest(OpenModel):
    config: dict[str, Any] | None = None


class PluginGithubInstallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repository: str
    download_url: str | None = None
    proxy: str | None = None
    ignore_version_check: bool | None = None
    install_method: str | None = None
    registry_url: str | None = None
    market_plugin_id: str | None = None


class PluginUrlInstallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    download_url: str | None = None
    proxy: str | None = None
    ignore_version_check: bool | None = None
    install_method: str | None = None
    registry_url: str | None = None
    market_plugin_id: str | None = None


class PluginSourceBindRequest(OpenModel):
    install_method: str | None = None
    registry_url: str | None = None
    market_plugin_id: str | None = None


class PluginUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proxy: str | None = None


class PluginBatchUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    names: list[str]
    proxy: str | None = None


class PluginConfigPayload(OpenModel):
    config: dict[str, Any] | None = None


class PluginLogLevelPayload(OpenModel):
    level: str | None = None


class PluginSourceRequest(OpenModel):
    id: str | None = None
    name: str | None = None
    url: str | None = None
    sources: list[Any] | None = None


class PluginUninstallRequest(OpenModel):
    delete_config: bool | None = None
    delete_data: bool | None = None


class PluginConfigFileDeleteRequest(OpenModel):
    path: str | None = None
    file: str | None = None
    filename: str | None = None
    key: str | None = None


class ConfigRoutesReplaceRequest(BaseModel):
    routing: dict[str, str]


class ConfigRouteUpsertRequest(BaseModel):
    config_id: str = Field(..., min_length=1)


class SessionRuleRequest(OpenModel):
    umo: str | None = None
    rule_key: str | None = None
    rule_value: Any = None


class UmoListRequest(OpenModel):
    umo: str | None = None
    umos: list[str] | None = None
    scope: Literal["all", "group", "private", "custom_group"] | None = None
    group_id: str | None = None
    rule_key: str | None = None


class BatchSessionProviderRequest(UmoListRequest):
    provider_id: str | None = None
    provider_type: (
        Literal[
            "chat_completion",
            "speech_to_text",
            "text_to_speech",
        ]
        | None
    ) = None


class BatchSessionServiceRequest(UmoListRequest):
    session_enabled: bool | None = None
    llm_enabled: bool | None = None
    tts_enabled: bool | None = None


class SessionGroupRequest(OpenModel):
    id: str | None = None
    name: str | None = None
    umos: list[str] | None = None
    add_umos: list[str] | None = None
    remove_umos: list[str] | None = None
