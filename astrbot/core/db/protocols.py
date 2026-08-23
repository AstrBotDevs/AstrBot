"""Narrow structural database contracts grouped by domain."""

from __future__ import annotations

import datetime
import typing as T
from contextlib import AbstractAsyncContextManager
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from astrbot.core.db.po import (
        ApiKey,
        Attachment,
        AuthCapability,
        ChatUIProject,
        CommandConfig,
        CommandConflict,
        ConversationV2,
        CronJob,
        MemoryEpisode,
        MemoryFact,
        MemoryOperationLog,
        MemoryProfile,
        MemoryScopePolicyRecord,
        MemoryTuningTask,
        Persona,
        PersonaBehaviorPolicy,
        PersonaExpressionAsset,
        PersonaFolder,
        PersonaJargonAsset,
        PersonaSessionState,
        PlatformMessageHistory,
        PlatformSession,
        PlatformStat,
        Preference,
        ProviderStat,
        SessionProjectRelation,
        UmoAlias,
        WebChatThread,
    )


@runtime_checkable
class DatabaseSessionStore(Protocol):
    """Expose scoped SQLAlchemy sessions without domain operations."""

    def get_db(self) -> AbstractAsyncContextManager[AsyncSession]: ...


@runtime_checkable
class StatisticsStore(Protocol):
    """Operations for runtime and provider statistics."""

    async def insert_platform_stats(
        self,
        platform_id: str,
        platform_type: str,
        count: int = 1,
        timestamp: datetime.datetime | None = None,
    ) -> None: ...

    async def count_platform_stats(self) -> int: ...

    async def get_platform_stats(
        self, offset_sec: int = 86400
    ) -> list[PlatformStat]: ...

    async def insert_provider_stat(
        self,
        *,
        umo: str,
        provider_id: str,
        provider_model: str | None = None,
        conversation_id: str | None = None,
        status: str = "completed",
        stats: dict | None = None,
        agent_type: str = "internal",
    ) -> ProviderStat: ...


@runtime_checkable
class PersonaRuntimeStore(Protocol):
    """Operations for persona runtime state and learned assets."""

    async def get_persona_session_state(
        self,
        persona_id: str,
        umo: str,
    ) -> PersonaSessionState | None: ...

    async def upsert_persona_session_state(
        self,
        *,
        persona_id: str,
        umo: str,
        agent_state: str = "running",
        talk_frequency_adjust: float = 1.0,
        consecutive_idle_count: int = 0,
        cooldown_until: datetime.datetime | None = None,
        last_interaction_at: datetime.datetime | None = None,
        last_proactive_at: datetime.datetime | None = None,
        extra_state: dict | None = None,
    ) -> PersonaSessionState: ...

    async def upsert_persona_expression_asset(
        self,
        *,
        persona_id: str,
        scope: str,
        trigger_scene: str,
        style_text: str,
        source_message_id: str,
        score: float = 0.5,
        enabled: bool = True,
    ) -> PersonaExpressionAsset: ...

    async def list_persona_expression_assets(
        self,
        *,
        persona_id: str,
        scope: str,
        enabled: bool = True,
        limit: int = 10,
    ) -> list[PersonaExpressionAsset]: ...

    async def upsert_persona_jargon_asset(
        self,
        *,
        persona_id: str,
        scope: str,
        term: str,
        meaning: str | None,
        source_message_id: str,
        score: float = 0.5,
        approved: bool = False,
        enabled: bool = True,
    ) -> PersonaJargonAsset: ...

    async def list_persona_jargon_assets(
        self,
        *,
        persona_id: str,
        scope: str,
        enabled: bool = True,
        approved: bool | None = None,
        limit: int = 10,
    ) -> list[PersonaJargonAsset]: ...

    async def upsert_persona_behavior_policy(
        self,
        *,
        persona_id: str,
        scope: str,
        situation: str,
        preferred_action: str,
        avoid_action: str | None = None,
        confidence: float = 0.5,
        enabled: bool = True,
    ) -> PersonaBehaviorPolicy: ...

    async def list_persona_behavior_policies(
        self,
        *,
        persona_id: str,
        scope: str,
        enabled: bool = True,
        limit: int = 10,
    ) -> list[PersonaBehaviorPolicy]: ...


@runtime_checkable
class MemoryStore(Protocol):
    """Operations for long-term memory and its audit records."""

    async def upsert_memory_fact(
        self,
        *,
        person_id: str,
        chat_id: str,
        scope_id: str,
        fact_text: str,
        fact_type: str,
        source_message_id: str,
        evidence_message_ids: list[str] | None = None,
        confidence: float = 0.6,
        status: str = "active",
        ttl_at: datetime.datetime | None = None,
    ) -> tuple[MemoryFact, bool]: ...

    async def list_memory_facts(
        self,
        *,
        person_id: str | None = None,
        chat_ids: list[str] | None = None,
        scope_id: str | None = None,
        query: str | None = None,
        status: str | None = "active",
        limit: int = 20,
        offset: int = 0,
    ) -> list[MemoryFact]: ...

    async def count_memory_facts(
        self,
        *,
        person_id: str | None = None,
        chat_ids: list[str] | None = None,
        scope_id: str | None = None,
        query: str | None = None,
        status: str | None = "active",
    ) -> int: ...

    async def get_memory_fact(self, fact_id: int) -> MemoryFact | None: ...

    async def update_memory_fact(
        self,
        fact_id: int,
        *,
        fact_text: str | None = None,
        fact_type: str | None = None,
        confidence: float | None = None,
        operator: str,
        reason: str | None = None,
    ) -> MemoryFact | None: ...

    async def update_memory_fact_status(
        self,
        fact_id: int,
        *,
        status: str,
        operator: str,
        reason: str | None = None,
    ) -> bool: ...

    async def upsert_memory_profile(
        self,
        *,
        person_id: str,
        chat_scope: str,
        profile_text: str,
        is_override: bool = False,
    ) -> MemoryProfile: ...

    async def get_memory_profile(
        self,
        person_id: str,
        chat_scope: str,
        *,
        include_override: bool = True,
    ) -> MemoryProfile | None: ...

    async def list_memory_profiles(
        self,
        *,
        person_id: str | None = None,
        chat_scope: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[MemoryProfile]: ...

    async def count_memory_profiles(
        self,
        *,
        person_id: str | None = None,
        chat_scope: str | None = None,
    ) -> int: ...

    async def upsert_memory_episode(
        self,
        *,
        episode_id: str,
        chat_id: str,
        scope_id: str,
        title: str,
        summary: str,
        participant_ids: list[str] | None = None,
        source_message_ids: list[str] | None = None,
        status: str = "active",
        start_at: datetime.datetime | None = None,
        end_at: datetime.datetime | None = None,
    ) -> MemoryEpisode: ...

    async def list_memory_episodes(
        self,
        *,
        chat_ids: list[str] | None = None,
        scope_id: str | None = None,
        query: str | None = None,
        status: str = "active",
        limit: int = 10,
    ) -> list[MemoryEpisode]: ...

    async def count_memory_episodes(
        self,
        *,
        status: str | None = "active",
    ) -> int: ...

    async def upsert_memory_scope_policy(
        self,
        *,
        owner_scope_id: str,
        target_scope_id: str,
        sharing_mode: str = "group-shared",
        enabled: bool = True,
        operator: str = "memory_scope_policy",
        reason: str | None = None,
    ) -> MemoryScopePolicyRecord: ...

    async def list_memory_scope_policies(
        self,
        *,
        owner_scope_id: str | None = None,
        enabled: bool = True,
        limit: int = 50,
    ) -> list[MemoryScopePolicyRecord]: ...

    async def upsert_memory_tuning_task(
        self,
        *,
        task_id: str,
        task_type: str,
        target_scope: str,
        candidate_config: dict | None = None,
        evaluation_result: dict | None = None,
        status: str = "pending",
    ) -> MemoryTuningTask: ...

    async def list_memory_tuning_tasks(
        self,
        *,
        target_scope: str | None = None,
        status: str | None = None,
        limit: int = 20,
    ) -> list[MemoryTuningTask]: ...

    async def insert_memory_operation_log(
        self,
        *,
        operator: str,
        target_type: str,
        target_id: str,
        action: str,
        reason: str | None = None,
        payload: dict | None = None,
    ) -> MemoryOperationLog: ...

    async def list_memory_operation_logs(
        self,
        *,
        target_type: str | None = None,
        target_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MemoryOperationLog]: ...

    async def count_memory_operation_logs(
        self,
        *,
        target_type: str | None = None,
        target_id: str | None = None,
    ) -> int: ...


@runtime_checkable
class ConversationStore(Protocol):
    """Operations for persisted conversations and session views."""

    async def get_conversations(
        self,
        user_id: str | None = None,
        platform_id: str | None = None,
    ) -> list[ConversationV2]: ...

    async def get_conversation_by_id(self, cid: str) -> ConversationV2 | None: ...

    async def get_all_conversations(
        self,
        page: int = 1,
        page_size: int = 20,
    ) -> list[ConversationV2]: ...

    async def get_filtered_conversations(
        self,
        page: int = 1,
        page_size: int = 20,
        platform_ids: list[str] | None = None,
        search_query: str = "",
        **kwargs,
    ) -> tuple[list[ConversationV2], int]: ...

    async def create_conversation(
        self,
        user_id: str,
        platform_id: str,
        content: list[dict] | None = None,
        title: str | None = None,
        persona_id: str | None = None,
        cid: str | None = None,
        created_at: datetime.datetime | None = None,
        updated_at: datetime.datetime | None = None,
    ) -> ConversationV2: ...

    async def update_conversation(
        self,
        cid: str,
        title: str | None = None,
        persona_id: str | None = None,
        content: list[dict] | None = None,
        token_usage: int | None = None,
    ) -> ConversationV2 | None: ...

    async def delete_conversation(self, cid: str) -> None: ...

    async def delete_conversations_by_user_id(self, user_id: str) -> None: ...

    async def get_session_conversations(
        self,
        page: int = 1,
        page_size: int = 20,
        search_query: str | None = None,
        platform: str | None = None,
    ) -> tuple[list[dict], int]: ...


@runtime_checkable
class MessageHistoryStore(Protocol):
    """Operations for platform message history."""

    async def insert_platform_message_history(
        self,
        platform_id: str,
        user_id: str,
        content: dict,
        sender_id: str | None = None,
        sender_name: str | None = None,
        role: str = "user",
        is_group: bool = False,
        llm_checkpoint_id: str | None = None,
        max_messages: int | None = None,
    ) -> PlatformMessageHistory: ...

    async def update_platform_message_history(
        self,
        message_id: int,
        content: dict | None = None,
        role: str | None = None,
        llm_checkpoint_id: str | None = None,
    ) -> None: ...

    async def delete_platform_message_history_by_id(self, message_id: int) -> None: ...

    async def delete_platform_message_offset(
        self,
        platform_id: str,
        user_id: str,
        offset_sec: int = 86400,
    ) -> None: ...

    async def get_platform_message_history(
        self,
        platform_id: str,
        user_id: str,
        page: int = 1,
        page_size: int = 20,
        *,
        is_group: bool | None = None,
        before_id: int | None = None,
    ) -> list[PlatformMessageHistory]: ...

    async def get_group_message_history(
        self,
        platform_id: str,
        group_id: str,
        *,
        limit: int = 50,
        before_id: int | None = None,
    ) -> list[PlatformMessageHistory]: ...

    async def get_platform_message_history_by_id(
        self,
        message_id: int,
    ) -> PlatformMessageHistory | None: ...


@runtime_checkable
class WebChatThreadStore(Protocol):
    """Operations for WebChat side threads."""

    async def create_webchat_thread(
        self,
        creator: str,
        parent_session_id: str,
        parent_message_id: int,
        base_checkpoint_id: str,
        selected_text: str,
    ) -> WebChatThread: ...

    async def get_webchat_thread_by_id(
        self,
        thread_id: str,
    ) -> WebChatThread | None: ...

    async def get_webchat_threads_by_parent_session(
        self,
        parent_session_id: str,
        creator: str | None = None,
    ) -> list[WebChatThread]: ...

    async def get_webchat_thread_by_parent_message_and_text(
        self,
        parent_session_id: str,
        parent_message_id: int,
        selected_text: str,
        creator: str | None = None,
    ) -> WebChatThread | None: ...

    async def delete_webchat_thread(self, thread_id: str) -> None: ...

    async def delete_webchat_threads_by_parent_session(
        self,
        parent_session_id: str,
    ) -> list[str]: ...

    async def delete_webchat_threads_by_parent_message_ids(
        self,
        parent_session_id: str,
        parent_message_ids: list[int],
    ) -> list[str]: ...


@runtime_checkable
class AttachmentStore(Protocol):
    """Operations for stored attachments."""

    async def insert_attachment(
        self,
        path: str,
        type: str,
        mime_type: str,
    ) -> Attachment: ...

    async def get_attachment_by_id(self, attachment_id: str) -> Attachment | None: ...

    async def get_attachments(self, attachment_ids: list[str]) -> list[Attachment]: ...

    async def delete_attachment(self, attachment_id: str) -> bool: ...

    async def delete_attachments(self, attachment_ids: list[str]) -> int: ...


@runtime_checkable
class ApiKeyStore(Protocol):
    """Operations for Dashboard API keys."""

    async def create_api_key(
        self,
        name: str,
        key_hash: str,
        key_prefix: str,
        scopes: list[str] | None,
        created_by: str,
        expires_at: datetime.datetime | None = None,
    ) -> ApiKey: ...

    async def list_api_keys(self) -> list[ApiKey]: ...

    async def get_api_key_by_id(self, key_id: str) -> ApiKey | None: ...

    async def get_active_api_key_by_hash(self, key_hash: str) -> ApiKey | None: ...

    async def touch_api_key(self, key_id: str) -> None: ...

    async def revoke_api_key(self, key_id: str) -> bool: ...

    async def delete_api_key(self, key_id: str) -> bool: ...

    async def upsert_capability(
        self,
        *,
        subject_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        config_id: str | None = None,
        created_by: str | None = None,
        expires_at: datetime.datetime | None = None,
    ) -> AuthCapability: ...


@runtime_checkable
class PersonaStore(Protocol):
    """Operations for personas and their folders."""

    async def insert_persona(
        self,
        persona_id: str,
        system_prompt: str,
        begin_dialogs: list[str] | None = None,
        tools: list[str] | None = None,
        skills: list[str] | None = None,
        custom_error_message: str | None = None,
        folder_id: str | None = None,
        sort_order: int = 0,
    ) -> Persona: ...

    async def get_persona_by_id(self, persona_id: str) -> Persona | None: ...

    async def get_personas(self) -> list[Persona]: ...

    async def update_persona(
        self,
        persona_id: str,
        system_prompt: str | None = None,
        begin_dialogs: list[str] | None = None,
        tools: list[str] | None | object = ...,
        skills: list[str] | None | object = ...,
        custom_error_message: str | None | object = ...,
    ) -> Persona | None: ...

    async def delete_persona(self, persona_id: str) -> None: ...

    async def insert_persona_folder(
        self,
        name: str,
        parent_id: str | None = None,
        description: str | None = None,
        sort_order: int = 0,
    ) -> PersonaFolder: ...

    async def get_persona_folder_by_id(
        self, folder_id: str
    ) -> PersonaFolder | None: ...

    async def get_persona_folders(
        self, parent_id: str | None = None
    ) -> list[PersonaFolder]: ...

    async def get_all_persona_folders(self) -> list[PersonaFolder]: ...

    async def update_persona_folder(
        self,
        folder_id: str,
        name: str | None = None,
        parent_id: T.Any = ...,
        description: T.Any = ...,
        sort_order: int | None = None,
    ) -> PersonaFolder | None: ...

    async def delete_persona_folder(self, folder_id: str) -> None: ...

    async def move_persona_to_folder(
        self, persona_id: str, folder_id: str | None
    ) -> Persona | None: ...

    async def get_personas_by_folder(
        self, folder_id: str | None = None
    ) -> list[Persona]: ...

    async def batch_update_sort_order(
        self,
        items: list[dict],
    ) -> None: ...


@runtime_checkable
class PreferenceStore(Protocol):
    """Operations for scoped preferences."""

    async def insert_preference_or_update(
        self,
        scope: str,
        scope_id: str,
        key: str,
        value: dict,
    ) -> Preference: ...

    async def get_preference(
        self, scope: str, scope_id: str, key: str
    ) -> Preference | None: ...

    async def get_preferences(
        self,
        scope: str | None = None,
        scope_id: str | None = None,
        key: str | None = None,
    ) -> list[Preference]: ...

    async def remove_preference(self, scope: str, scope_id: str, key: str) -> None: ...

    async def clear_preferences(self, scope: str, scope_id: str) -> None: ...


@runtime_checkable
class CommandStore(Protocol):
    """Operations for command configuration and conflict records."""

    async def get_command_configs(self) -> list[CommandConfig]: ...

    async def get_command_config(
        self, handler_full_name: str
    ) -> CommandConfig | None: ...

    async def get_command_config_by_command_id(
        self, command_id: str
    ) -> CommandConfig | None: ...

    async def upsert_command_config(
        self,
        handler_full_name: str,
        plugin_name: str,
        module_path: str,
        original_command: str,
        *,
        command_id: str | None = None,
        previous_handler_full_name: str | None = None,
        resolved_command: str | None = None,
        enabled: bool | None = None,
        conflict_key: str | None = None,
        resolution_strategy: str | None = None,
        note: str | None = None,
        extra_data: dict | None = None,
        auto_managed: bool | None = None,
    ) -> CommandConfig: ...

    async def delete_command_config(self, handler_full_name: str) -> None: ...

    async def delete_command_configs(self, handler_full_names: list[str]) -> None: ...

    async def list_command_conflicts(
        self,
        status: str | None = None,
    ) -> list[CommandConflict]: ...

    async def upsert_command_conflict(
        self,
        conflict_key: str,
        handler_full_name: str,
        plugin_name: str,
        *,
        command_id: str | None = None,
        status: str | None = None,
        resolution: str | None = None,
        resolved_command: str | None = None,
        note: str | None = None,
        extra_data: dict | None = None,
        auto_generated: bool | None = None,
    ) -> CommandConflict: ...

    async def delete_command_conflicts(self, ids: list[int]) -> None: ...


@runtime_checkable
class CronStore(Protocol):
    """Operations for persisted cron jobs."""

    async def create_cron_job(
        self,
        name: str,
        job_type: str,
        cron_expression: str | None,
        *,
        timezone: str | None = None,
        payload: dict | None = None,
        description: str | None = None,
        enabled: bool = True,
        persistent: bool = True,
        run_once: bool = False,
        status: str | None = None,
        job_id: str | None = None,
    ) -> CronJob: ...

    async def update_cron_job(
        self,
        job_id: str,
        *,
        name: str | None = None,
        cron_expression: str | None = None,
        timezone: str | None = None,
        payload: dict | None = None,
        description: str | None = None,
        enabled: bool | None = None,
        persistent: bool | None = None,
        run_once: bool | None = None,
        status: str | None = None,
        next_run_time: datetime.datetime | None = None,
        last_run_at: datetime.datetime | None = None,
        last_error: str | None = None,
    ) -> CronJob | None: ...

    async def delete_cron_job(self, job_id: str) -> None: ...

    async def get_cron_job(self, job_id: str) -> CronJob | None: ...

    async def list_cron_jobs(self, job_type: str | None = None) -> list[CronJob]: ...


@runtime_checkable
class PlatformSessionStore(Protocol):
    """Operations for persisted platform sessions."""

    async def create_platform_session(
        self,
        creator: str,
        platform_id: str = "webchat",
        session_id: str | None = None,
        display_name: str | None = None,
        is_group: int = 0,
    ) -> PlatformSession: ...

    async def get_platform_session_by_id(
        self, session_id: str
    ) -> PlatformSession | None: ...

    async def get_platform_sessions_by_ids(
        self, session_ids: list[str]
    ) -> list[PlatformSession]: ...

    async def get_platform_sessions_by_creator(
        self,
        creator: str,
        platform_id: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> list[dict]: ...

    async def get_platform_sessions_by_creator_paginated(
        self,
        creator: str,
        platform_id: str | None = None,
        page: int = 1,
        page_size: int = 20,
        exclude_project_sessions: bool = False,
    ) -> tuple[list[dict], int]: ...

    async def update_platform_session(
        self,
        session_id: str,
        display_name: str | None = None,
    ) -> None: ...

    async def delete_platform_session(self, session_id: str) -> None: ...


@runtime_checkable
class UmoAliasStore(Protocol):
    """Operations for UMO display aliases."""

    async def upsert_umo_alias(
        self,
        umo: str,
        creator_sender_id: str,
        auto_name: str | None,
        user_alias: str | None,
    ) -> UmoAlias: ...

    async def get_umo_alias(self, umo: str) -> UmoAlias | None: ...

    async def get_umo_aliases(
        self, umos: list[str] | None = None
    ) -> list[UmoAlias]: ...


@runtime_checkable
class ChatProjectStore(Protocol):
    """Operations for ChatUI projects and their session relations."""

    async def create_chatui_project(
        self,
        creator: str,
        title: str,
        emoji: str | None = "📁",
        description: str | None = None,
    ) -> ChatUIProject: ...

    async def get_chatui_project_by_id(
        self, project_id: str
    ) -> ChatUIProject | None: ...

    async def get_chatui_projects_by_creator(
        self,
        creator: str,
        page: int = 1,
        page_size: int = 100,
    ) -> list[ChatUIProject]: ...

    async def update_chatui_project(
        self,
        project_id: str,
        title: str | None = None,
        emoji: str | None = None,
        description: str | None = None,
    ) -> None: ...

    async def delete_chatui_project(self, project_id: str) -> None: ...

    async def add_session_to_project(
        self,
        session_id: str,
        project_id: str,
    ) -> SessionProjectRelation: ...

    async def remove_session_from_project(self, session_id: str) -> None: ...

    async def get_project_sessions(
        self,
        project_id: str,
        page: int = 1,
        page_size: int = 100,
    ) -> list[PlatformSession]: ...

    async def get_project_by_session(
        self, session_id: str, creator: str
    ) -> ChatUIProject | None: ...


@runtime_checkable
class ChatStore(
    AttachmentStore,
    ChatProjectStore,
    MessageHistoryStore,
    PlatformSessionStore,
    WebChatThreadStore,
    Protocol,
):
    """Compose the stores needed by Chat transport services."""


@runtime_checkable
class OpenApiStore(
    ApiKeyStore,
    AttachmentStore,
    PlatformSessionStore,
    Protocol,
):
    """Compose the stores needed by the OpenAPI transport service."""


@runtime_checkable
class ChatProjectSessionStore(ChatProjectStore, PlatformSessionStore, Protocol):
    """Compose ChatUI project and platform session operations."""


@runtime_checkable
class SessionManagementStore(UmoAliasStore, DatabaseSessionStore, Protocol):
    """Compose session metadata and scoped SQL access."""


@runtime_checkable
class StatisticsSessionStore(StatisticsStore, DatabaseSessionStore, Protocol):
    """Compose statistics queries and scoped SQL access."""


@runtime_checkable
class PluginRuntimeStore(
    CommandStore,
    DatabaseSessionStore,
    PlatformSessionStore,
    PreferenceStore,
    StatisticsStore,
    UmoAliasStore,
    Protocol,
):
    """Compose the persistence capabilities used by the plugin runtime."""


@runtime_checkable
class WebChatStorageStore(AttachmentStore, MessageHistoryStore, Protocol):
    """Compose attachment and history persistence for the WebChat adapter."""


@runtime_checkable
class DashboardStore(
    ApiKeyStore,
    ChatStore,
    CommandStore,
    DatabaseSessionStore,
    MemoryStore,
    StatisticsStore,
    UmoAliasStore,
    Protocol,
):
    """Compose persistence capabilities at the Dashboard composition root."""


__all__ = [
    "ApiKeyStore",
    "AttachmentStore",
    "ChatProjectStore",
    "ChatProjectSessionStore",
    "ChatStore",
    "CommandStore",
    "ConversationStore",
    "CronStore",
    "DatabaseSessionStore",
    "DashboardStore",
    "MemoryStore",
    "MessageHistoryStore",
    "OpenApiStore",
    "PersonaRuntimeStore",
    "PersonaStore",
    "PlatformSessionStore",
    "PluginRuntimeStore",
    "PreferenceStore",
    "SessionManagementStore",
    "StatisticsStore",
    "StatisticsSessionStore",
    "UmoAliasStore",
    "WebChatStorageStore",
    "WebChatThreadStore",
]
