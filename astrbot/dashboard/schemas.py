from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class OpenModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class ConfigProfileCreateRequest(BaseModel):
    name: str | None = None
    config: dict[str, Any] | None = None


class ConfigContentRequest(OpenModel):
    pass


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


class ChatThreadCreateRequest(OpenModel):
    session_id: str
    parent_message_id: str | int
    selected_text: str


class ChatThreadMessageRequest(OpenModel):
    message: Any
    selected_provider: str | None = None
    selected_model: str | None = None
    enable_streaming: bool | None = None


class CronJobRequest(OpenModel):
    pass


class CommandUpdateRequest(BaseModel):
    enabled: bool | None = None
    alias: str | None = None
    aliases: list[str] | None = None
    permission_group: str | None = None


class CommandToggleRequest(BaseModel):
    handler_full_name: str
    enabled: bool


class CommandRenameRequest(BaseModel):
    handler_full_name: str
    new_name: str
    aliases: list[str] | None = None


class CommandPermissionRequest(BaseModel):
    handler_full_name: str
    permission: str


class SubAgentConfigRequest(OpenModel):
    main_enable: bool | None = None
    enable: bool | None = None
    remove_main_duplicate_tools: bool | None = None
    agents: list[dict[str, Any]] | None = None


class TraceSettingsRequest(BaseModel):
    trace_enable: bool | None = None


class StorageCleanupRequest(BaseModel):
    target: str = "all"


class GhProxyTestRequest(BaseModel):
    proxy_url: str | None = None


class OpenApiChatRequest(OpenModel):
    message: Any = None
    session_id: str | None = None
    conversation_id: str | None = None
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


class ImMessageRequest(OpenModel):
    umo: str | None = None
    message: Any = None
    type: str | None = None


class KnowledgeBaseRequest(OpenModel):
    kb_id: str | None = None
    name: str | None = None
    description: str | None = None
    embedding_provider_id: str | None = None
    rerank_provider_id: str | None = None
    chunk_size: int | None = None
    chunk_overlap: int | None = None


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


class ToolEnabledRequest(BaseModel):
    enabled: bool


class ToolPermissionRequest(BaseModel):
    permission: Literal["admin", "member"]


class McpServerRequest(OpenModel):
    name: str | None = None
    oldName: str | None = None
    active: bool | None = None
    enabled: bool | None = None
    config: dict[str, Any] | None = None
    mcpServers: dict[str, Any] | None = None


class McpServerByNameRequest(OpenModel):
    server_name: str
    config: dict[str, Any] | None = None
    mcp_server_config: dict[str, Any] | None = None
    enabled: bool | None = None


class ModelScopeSyncRequest(BaseModel):
    access_token: str | None = None


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


class PersonaByIdRequest(OpenModel):
    persona_id: str


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


class SkillUpdateRequest(OpenModel):
    enabled: bool | None = None
    active: bool | None = None

    def active_value(self) -> bool:
        if self.enabled is not None:
            return self.enabled
        if self.active is not None:
            return self.active
        return True


class SkillByNameUpdateRequest(SkillUpdateRequest):
    skill_name: str


class SkillFileUpdateRequest(OpenModel):
    skill_name: str
    path: str
    content: str = ""


class SkillNeoRequest(OpenModel):
    skill_name: str | None = None
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


class BotConfigRequest(OpenModel):
    bot_id: str | None = None
    id: str | None = None
    name: str | None = None
    type: str | None = None
    enabled: bool | None = None
    enable: bool | None = None
    config: dict[str, Any] | None = None

    def to_dashboard_config(self, *, fallback_id: str | None = None) -> dict[str, Any]:
        config = dict(
            self.config
            or self.model_dump(
                exclude={"bot_id", "config", "enabled"},
                exclude_none=True,
            )
        )
        if fallback_id and "id" not in config:
            config["id"] = fallback_id
        if self.type and "type" not in config:
            config["type"] = self.type
        if self.id and "id" not in config:
            config["id"] = self.id
        if self.enabled is not None:
            config["enable"] = self.enabled
        elif self.enable is not None:
            config["enable"] = self.enable
        elif "enable" not in config:
            config["enable"] = True
        return config


class BotRegistrationRequest(OpenModel):
    action: Literal["start", "poll"] | str | None = None
    platform_config: dict[str, Any] | None = None
    registration_code: str | None = None
    device_code: str | None = None


class ProviderSourceRequest(OpenModel):
    source_id: str | None = None
    id: str | None = None
    config: dict[str, Any] | None = None

    def to_dashboard_config(self, *, fallback_id: str | None = None) -> dict[str, Any]:
        config = dict(
            self.config
            or self.model_dump(exclude={"source_id", "config"}, exclude_none=True)
        )
        if not config.get("id"):
            # 不覆盖已有 id；self.id（显式指定）优先于 fallback_id（旧值兜底）
            if fallback := (self.id or fallback_id):
                config["id"] = fallback
        return config


class ProviderConfigRequest(OpenModel):
    provider_id: str | None = None
    source_id: str | None = None
    id: str | None = None
    provider_source_id: str | None = None
    provider_config: dict[str, Any] | None = None
    capability: str | None = None
    enabled: bool | None = None
    enable: bool | None = None
    config: dict[str, Any] | None = None

    def to_dashboard_config(
        self,
        *,
        fallback_id: str | None = None,
        source_id: str | None = None,
    ) -> dict[str, Any]:
        config = dict(
            self.config
            or self.model_dump(
                exclude={
                    "provider_id",
                    "source_id",
                    "provider_config",
                    "config",
                    "capability",
                    "enabled",
                },
                exclude_none=True,
            )
        )
        if fallback_id and "id" not in config:
            config["id"] = fallback_id
        if self.id and "id" not in config:
            config["id"] = self.id
        if source_id:
            config["provider_source_id"] = source_id
        elif self.provider_source_id and "provider_source_id" not in config:
            config["provider_source_id"] = self.provider_source_id
        if self.enabled is not None:
            config["enable"] = self.enabled
        elif self.enable is not None:
            config["enable"] = self.enable
        elif "enable" not in config:
            config["enable"] = True
        if self.capability and "provider_type" not in config:
            capability_map = {
                "chat": "chat_completion",
                "agent": "agent_runner",
                "stt": "speech_to_text",
                "tts": "text_to_speech",
                "embedding": "embedding",
                "rerank": "rerank",
            }
            config["provider_type"] = capability_map.get(
                self.capability, self.capability
            )
        return config


class ProviderListQuery(BaseModel):
    capability: str | None = None
    source_id: str | None = None
    enabled: bool | None = None


class PluginVersionSupportRequest(OpenModel):
    astrbot_version: str | None = None
    plugin_ids: list[str] | None = None


class PluginInstallRequest(OpenModel):
    repository: str | None = None
    url: str | None = None
    download_url: str | None = None
    proxy: str | None = None
    ignore_version_check: bool | None = None


class PluginSourceBindRequest(OpenModel):
    registry_url: str | None = None
    market_plugin_id: str | None = None


class PluginUpdateRequest(OpenModel):
    plugin_id: str | None = None
    plugin_ids: list[str] | None = None
    name: str | None = None
    names: list[str] | None = None
    proxy: str | None = None
    download_url: str | None = None
    download_urls: dict[str, str] | None = None


class PluginByIdRequest(OpenModel):
    plugin_id: str


class PluginEnabledRequest(PluginByIdRequest):
    enabled: bool


class PluginConfigUpdateRequest(PluginByIdRequest):
    config: dict[str, Any] | None = None


class PluginConfigPayload(OpenModel):
    config: dict[str, Any] | None = None


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
