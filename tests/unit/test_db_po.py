"""Tests for database PO (Persistent Object) model classes.

These tests verify construction, field defaults, and type correctness
for all model classes defined in ``astrbot.core.db.po``.
"""

from datetime import datetime, timezone

import pytest

from astrbot.core.db.po import (
    ApiKey,
    Attachment,
    ChatUIProject,
    CommandConfig,
    CommandConflict,
    Conversation,
    ConversationV2,
    CronJob,
    Persona,
    PersonaFolder,
    Personality,
    PlatformMessageHistory,
    PlatformSession,
    PlatformStat,
    Preference,
    ProviderStat,
    SessionProjectRelation,
    Stats,
    TimestampMixin,
    WebChatThread,
)


class TestCronJob:
    """Tests for the CronJob SQLModel."""

    def test_minimal_construction(self):
        """CronJob can be created with only required fields."""
        job = CronJob(name="test-job", job_type="basic")
        assert job.name == "test-job"
        assert job.job_type == "basic"
        assert job.enabled is True
        assert job.persistent is True
        assert job.run_once is False
        assert job.status == "scheduled"
        assert job.cron_expression is None
        assert job.job_id is not None  # auto-generated via default_factory

    def test_full_construction(self):
        """CronJob accepts all optional fields."""
        job = CronJob(
            name="full-job",
            job_type="active_agent",
            cron_expression="0 9 * * *",
            timezone="UTC",
            payload={"session": "test:group:1"},
            description="A full job",
            enabled=False,
            persistent=True,
            run_once=True,
            status="running",
        )
        assert job.name == "full-job"
        assert job.job_type == "active_agent"
        assert job.cron_expression == "0 9 * * *"
        assert job.timezone == "UTC"
        assert job.payload == {"session": "test:group:1"}
        assert job.description == "A full job"
        assert job.enabled is False
        assert job.run_once is True
        assert job.status == "running"

    def test_auto_timestamps(self):
        """CronJob inherits TimestampMixin which auto-generates created_at/updated_at."""
        job = CronJob(name="ts-test", job_type="basic")
        assert isinstance(job.created_at, datetime)
        assert isinstance(job.updated_at, datetime)

    def test_job_id_auto_generated(self):
        """Each instance gets a unique job_id."""
        job1 = CronJob(name="a", job_type="basic")
        job2 = CronJob(name="b", job_type="basic")
        assert job1.job_id != job2.job_id


class TestConversationV2:
    """Tests for the ConversationV2 SQLModel."""

    def test_minimal_construction(self):
        """ConversationV2 can be created with required fields."""
        conv = ConversationV2(platform_id="qq", user_id="user-1")
        assert conv.platform_id == "qq"
        assert conv.user_id == "user-1"
        assert conv.conversation_id is not None
        assert conv.title is None
        assert conv.persona_id is None
        assert conv.token_usage == 0

    def test_full_construction(self):
        """ConversationV2 accepts all optional fields."""
        conv = ConversationV2(
            platform_id="webchat",
            user_id="admin",
            content=[{"role": "user", "content": "hi"}],
            title="Chat",
            persona_id="p1",
            token_usage=42,
        )
        assert conv.content == [{"role": "user", "content": "hi"}]
        assert conv.title == "Chat"
        assert conv.persona_id == "p1"
        assert conv.token_usage == 42


class TestConversationDataclass:
    """Tests for the deprecated Conversation dataclass."""

    def test_construction(self):
        """Conversation dataclass sets all fields."""
        conv = Conversation(
            platform_id="qq",
            user_id="u1",
            cid="abc-123",
            history="[{}]",
            title="My Chat",
            persona_id="p1",
            created_at=1000,
            updated_at=2000,
            token_usage=50,
        )
        assert conv.platform_id == "qq"
        assert conv.user_id == "u1"
        assert conv.cid == "abc-123"
        assert conv.history == "[{}]"
        assert conv.title == "My Chat"
        assert conv.persona_id == "p1"
        assert conv.created_at == 1000
        assert conv.updated_at == 2000
        assert conv.token_usage == 50

    def test_defaults(self):
        """Conversation dataclass has sensible defaults."""
        conv = Conversation(platform_id="qq", user_id="u1", cid="x")
        assert conv.history == ""
        assert conv.title == ""
        assert conv.persona_id == ""
        assert conv.created_at == 0
        assert conv.token_usage == 0


class TestPersona:
    """Tests for the Persona SQLModel."""

    def test_minimal_construction(self):
        """Persona with only required fields."""
        p = Persona(persona_id="helper", system_prompt="You are helpful.")
        assert p.persona_id == "helper"
        assert p.system_prompt == "You are helpful."
        assert p.begin_dialogs is None
        assert p.tools is None
        assert p.skills is None
        assert p.custom_error_message is None
        assert p.sort_order == 0

    def test_with_all_fields(self):
        """Persona with all optional fields."""
        p = Persona(
            persona_id="custom",
            system_prompt="Be concise.",
            begin_dialogs=["Hello"],
            tools=["search", "calc"],
            skills=["weather"],
            custom_error_message="Sorry, try later.",
            folder_id="folder-1",
            sort_order=5,
        )
        assert p.begin_dialogs == ["Hello"]
        assert p.tools == ["search", "calc"]
        assert p.skills == ["weather"]
        assert p.custom_error_message == "Sorry, try later."
        assert p.folder_id == "folder-1"
        assert p.sort_order == 5


class TestPersonaFolder:
    """Tests for the PersonaFolder SQLModel."""

    def test_construction(self):
        """PersonaFolder creation with required fields."""
        folder = PersonaFolder(name="My Folder")
        assert folder.name == "My Folder"
        assert folder.folder_id is not None
        assert folder.parent_id is None
        assert folder.description is None
        assert folder.sort_order == 0

    def test_nested_folder(self):
        """PersonaFolder can have a parent_id."""
        child = PersonaFolder(name="Child", parent_id="parent-uuid", description="Nested")
        assert child.parent_id == "parent-uuid"
        assert child.description == "Nested"


class TestApiKey:
    """Tests for the ApiKey SQLModel."""

    def test_construction(self):
        """ApiKey with required fields."""
        key = ApiKey(
            name="dev-key",
            key_hash="sha256:abc123",
            key_prefix="astr_",
            created_by="admin",
        )
        assert key.name == "dev-key"
        assert key.key_hash == "sha256:abc123"
        assert key.key_prefix == "astr_"
        assert key.created_by == "admin"
        assert key.scopes is None
        assert key.last_used_at is None
        assert key.expires_at is None
        assert key.revoked_at is None
        assert key.key_id is not None

    def test_with_scopes(self):
        """ApiKey can have scopes and expiry."""
        expires = datetime.now(timezone.utc)
        key = ApiKey(
            name="scoped-key",
            key_hash="sha256:xyz",
            key_prefix="astr_",
            created_by="admin",
            scopes=["read", "write"],
            expires_at=expires,
        )
        assert key.scopes == ["read", "write"]
        assert key.expires_at == expires


class TestPlatformStat:
    """Tests for the PlatformStat SQLModel."""

    def test_construction(self):
        """PlatformStat with all fields."""
        ts = datetime.now(timezone.utc)
        stat = PlatformStat(
            timestamp=ts,
            platform_id="qq_bot",
            platform_type="aiocqhttp",
            count=5,
        )
        assert stat.timestamp == ts
        assert stat.platform_id == "qq_bot"
        assert stat.platform_type == "aiocqhttp"
        assert stat.count == 5

    def test_default_count(self):
        """PlatformStat defaults count to 0."""
        stat = PlatformStat(
            timestamp=datetime.now(timezone.utc),
            platform_id="test",
            platform_type="test",
        )
        assert stat.count == 0


class TestProviderStat:
    """Tests for the ProviderStat SQLModel."""

    def test_construction(self):
        """ProviderStat with required fields."""
        ps = ProviderStat(umo="test:private:1", provider_id="openai")
        assert ps.umo == "test:private:1"
        assert ps.provider_id == "openai"
        assert ps.agent_type == "internal"
        assert ps.status == "completed"
        assert ps.token_input_other == 0
        assert ps.token_input_cached == 0
        assert ps.token_output == 0

    def test_with_stats(self):
        """ProviderStat records token and timing stats."""
        ps = ProviderStat(
            umo="test:private:1",
            provider_id="anthropic",
            provider_model="claude-3",
            conversation_id="conv-1",
            status="completed",
            agent_type="cron",
            token_input_other=100,
            token_input_cached=50,
            token_output=200,
            start_time=1000.0,
            end_time=1005.0,
            time_to_first_token=0.5,
        )
        assert ps.provider_model == "claude-3"
        assert ps.conversation_id == "conv-1"
        assert ps.token_input_other == 100
        assert ps.token_input_cached == 50
        assert ps.token_output == 200
        assert ps.start_time == 1000.0
        assert ps.end_time == 1005.0
        assert ps.time_to_first_token == 0.5


class TestPreference:
    """Tests for the Preference SQLModel."""

    def test_construction(self):
        """Preference with required fields."""
        pref = Preference(
            scope="plugin",
            scope_id="my_plugin",
            key="theme",
            value={"color": "dark"},
        )
        assert pref.scope == "plugin"
        assert pref.scope_id == "my_plugin"
        assert pref.key == "theme"
        assert pref.value == {"color": "dark"}


class TestOtherModels:
    """Tests for remaining SQLModel classes."""

    def test_attachment(self):
        """Attachment model construction."""
        att = Attachment(path="/tmp/file.png", type="image", mime_type="image/png")
        assert att.path == "/tmp/file.png"
        assert att.type == "image"
        assert att.mime_type == "image/png"
        assert att.attachment_id is not None

    def test_webchat_thread(self):
        """WebChatThread model construction."""
        thread = WebChatThread(
            creator="user-1",
            parent_session_id="session-1",
            parent_message_id=42,
            base_checkpoint_id="ckpt-1",
            selected_text="selected text",
        )
        assert thread.creator == "user-1"
        assert thread.parent_session_id == "session-1"
        assert thread.parent_message_id == 42
        assert thread.base_checkpoint_id == "ckpt-1"
        assert thread.selected_text == "selected text"
        assert thread.thread_id is not None

    def test_platform_session(self):
        """PlatformSession model construction."""
        sess = PlatformSession(
            creator="user-1",
            platform_id="webchat",
            display_name="My Chat",
        )
        assert sess.creator == "user-1"
        assert sess.platform_id == "webchat"
        assert sess.display_name == "My Chat"
        assert sess.is_group == 0
        assert sess.session_id is not None

    def test_chatui_project(self):
        """ChatUIProject model construction."""
        proj = ChatUIProject(
            creator="admin",
            title="My Project",
            emoji="star",
            description="A test project",
        )
        assert proj.creator == "admin"
        assert proj.title == "My Project"
        assert proj.emoji == "star"
        assert proj.description == "A test project"
        assert proj.project_id is not None

    def test_session_project_relation(self):
        """SessionProjectRelation model construction."""
        rel = SessionProjectRelation(session_id="sess-1", project_id="proj-1")
        assert rel.session_id == "sess-1"
        assert rel.project_id == "proj-1"

    def test_command_config(self):
        """CommandConfig model construction."""
        cc = CommandConfig(
            handler_full_name="plugin.command",
            plugin_name="test-plugin",
            module_path="plugins.test",
            original_command="/test",
        )
        assert cc.handler_full_name == "plugin.command"
        assert cc.plugin_name == "test-plugin"
        assert cc.module_path == "plugins.test"
        assert cc.original_command == "/test"
        assert cc.enabled is True
        assert cc.auto_managed is False

    def test_command_conflict(self):
        """CommandConflict model construction."""
        cf = CommandConflict(
            conflict_key="/greet",
            handler_full_name="p1.greet",
            plugin_name="plugin1",
        )
        assert cf.conflict_key == "/greet"
        assert cf.handler_full_name == "p1.greet"
        assert cf.plugin_name == "plugin1"
        assert cf.status == "pending"
        assert cf.auto_generated is False

    def test_platform_message_history(self):
        """PlatformMessageHistory model construction."""
        pmh = PlatformMessageHistory(
            platform_id="qq",
            user_id="user-1",
            content={"text": "hello"},
        )
        assert pmh.platform_id == "qq"
        assert pmh.user_id == "user-1"
        assert pmh.content == {"text": "hello"}
        assert pmh.sender_id is None
        assert pmh.sender_name is None
        assert pmh.llm_checkpoint_id is None

    def test_timestamp_mixin_fields(self):
        """TimestampMixin provides created_at and updated_at."""
        ts = datetime.now(timezone.utc)
        mixin = TimestampMixin()
        # created_at and updated_at have default factories
        assert isinstance(mixin.created_at, datetime)
        assert isinstance(mixin.updated_at, datetime)

    def test_personality_typeddict(self):
        """Personality TypedDict can be constructed with all keys."""
        personality: Personality = {
            "prompt": "You are a bot.",
            "name": "Bot",
            "begin_dialogs": ["Hello"],
            "mood_imitation_dialogs": ["Hi there"],
            "tools": ["search"],
            "skills": ["weather"],
            "custom_error_message": "Oops",
            "_begin_dialogs_processed": [{"role": "user", "content": "Hello"}],
            "_mood_imitation_dialogs_processed": "Hi there",
        }
        assert personality["prompt"] == "You are a bot."
        assert personality["name"] == "Bot"

    def test_stats_dataclass(self):
        """Stats dataclass holds a list of Platforms."""
        stats = Stats()
        assert stats.platform == []
