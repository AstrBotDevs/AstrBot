"""Explicit registration of every table=True SQLModel for schema creation."""

from astrbot.core.db.po.api_keys import ApiKey
from astrbot.core.db.po.attachments import Attachment
from astrbot.core.db.po.auth import (
    AuthAuditLog,
    AuthCapability,
    AuthPlatformMembershipFact,
    AuthPolicyOverride,
    AuthRoleBinding,
    AuthStepUpCredential,
    DashboardAccount,
    DashboardTrustedDevice,
)
from astrbot.core.db.po.commands import CommandConfig, CommandConflict
from astrbot.core.db.po.conversations import ConversationV2
from astrbot.core.db.po.cron import CronJob
from astrbot.core.db.po.memory import (
    MemoryEpisode,
    MemoryFact,
    MemoryOperationLog,
    MemoryProfile,
    MemoryScopePolicyRecord,
    MemoryTuningTask,
)
from astrbot.core.db.po.message_history import PlatformMessageHistory
from astrbot.core.db.po.personas import (
    Persona,
    PersonaBehaviorPolicy,
    PersonaExpressionAsset,
    PersonaFolder,
    PersonaJargonAsset,
    PersonaSessionState,
)
from astrbot.core.db.po.preferences import Preference
from astrbot.core.db.po.projects import ChatUIProject, SessionProjectRelation
from astrbot.core.db.po.sessions import PlatformSession, UmoAlias
from astrbot.core.db.po.statistics import PlatformStat, ProviderStat
from astrbot.core.db.po.webchat import WebChatThread

TABLE_MODELS: tuple[type, ...] = (
    ApiKey,
    Attachment,
    AuthAuditLog,
    AuthCapability,
    AuthPlatformMembershipFact,
    AuthPolicyOverride,
    AuthRoleBinding,
    AuthStepUpCredential,
    ChatUIProject,
    CommandConfig,
    CommandConflict,
    ConversationV2,
    CronJob,
    DashboardAccount,
    DashboardTrustedDevice,
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


def import_all_models() -> tuple[type, ...]:
    """Import and return every table=True model used by the main SQLite schema."""
    return TABLE_MODELS
