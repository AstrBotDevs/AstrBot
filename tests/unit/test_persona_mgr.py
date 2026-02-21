"""Tests for PersonaManager."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core.db.po import Persona, PersonaFolder
from astrbot.core.persona_mgr import DEFAULT_PERSONALITY, PersonaManager


@pytest.fixture
def mock_db():
    """Create a mock database."""
    db = MagicMock()
    db.get_persona_by_id = AsyncMock()
    db.get_personas = AsyncMock(return_value=[])
    db.create_persona = AsyncMock()
    db.insert_persona = AsyncMock()
    db.update_persona = AsyncMock()
    db.delete_persona = AsyncMock()
    db.get_personas_by_folder = AsyncMock(return_value=[])
    db.move_persona_to_folder = AsyncMock()
    db.insert_persona_folder = AsyncMock()
    db.get_persona_folder_by_id = AsyncMock()
    db.get_persona_folders = AsyncMock(return_value=[])
    db.get_all_persona_folders = AsyncMock(return_value=[])
    db.update_persona_folder = AsyncMock()
    db.delete_persona_folder = AsyncMock()
    db.batch_update_sort_order = AsyncMock()
    return db


@pytest.fixture
def mock_config_manager():
    """Create a mock AstrBotConfigManager."""
    config_mgr = MagicMock()
    config_mgr.default_conf = {
        "provider_settings": {
            "default_personality": "default"
        }
    }
    config_mgr.get_conf = MagicMock(return_value={
        "provider_settings": {"default_personality": "default"}
    })
    return config_mgr


@pytest.fixture
def persona_manager(mock_db, mock_config_manager):
    """Create a PersonaManager instance."""
    return PersonaManager(mock_db, mock_config_manager)


@pytest.fixture
def sample_persona():
    """Create a sample Persona."""
    return Persona(
        persona_id="test-persona",
        system_prompt="You are a helpful assistant.",
        begin_dialogs=["Hello!", "Hi there!"],
        tools=["tool1"],
        skills=["skill1"],
        folder_id=None,
        sort_order=0,
    )


@pytest.fixture
def sample_folder():
    """Create a sample PersonaFolder."""
    return PersonaFolder(
        folder_id="test-folder",
        name="Test Folder",
        parent_id=None,
        description="A test folder",
        sort_order=0,
    )


class TestPersonaManagerInit:
    """Tests for PersonaManager initialization."""

    def test_init(self, mock_db, mock_config_manager):
        """Test PersonaManager initialization."""
        manager = PersonaManager(mock_db, mock_config_manager)

        assert manager.db == mock_db
        assert manager.acm == mock_config_manager
        assert manager.personas == []
        assert manager.default_persona == "default"

    def test_init_with_custom_default_persona(self, mock_db, mock_config_manager):
        """Test initialization with custom default persona."""
        mock_config_manager.default_conf = {
            "provider_settings": {"default_personality": "custom-default"}
        }

        manager = PersonaManager(mock_db, mock_config_manager)

        assert manager.default_persona == "custom-default"


class TestPersonaManagerInitialize:
    """Tests for PersonaManager.initialize method."""

    @pytest.mark.asyncio
    async def test_initialize(self, persona_manager, mock_db):
        """Test initialize loads personas."""
        mock_persona = MagicMock()
        mock_persona.persona_id = "test-persona"
        mock_db.get_personas.return_value = [mock_persona]

        with patch.object(persona_manager, "get_v3_persona_data"):
            await persona_manager.initialize()

        assert len(persona_manager.personas) == 1
        mock_db.get_personas.assert_called_once()


class TestGetPersona:
    """Tests for get_persona method."""

    @pytest.mark.asyncio
    async def test_get_persona_exists(self, persona_manager, mock_db, sample_persona):
        """Test getting an existing persona."""
        mock_db.get_persona_by_id.return_value = sample_persona

        result = await persona_manager.get_persona("test-persona")

        assert result == sample_persona
        mock_db.get_persona_by_id.assert_called_once_with("test-persona")

    @pytest.mark.asyncio
    async def test_get_persona_not_exists(self, persona_manager, mock_db):
        """Test getting a non-existing persona."""
        mock_db.get_persona_by_id.return_value = None

        with pytest.raises(ValueError, match="does not exist"):
            await persona_manager.get_persona("non-existent")


class TestGetDefaultPersonaV3:
    """Tests for get_default_persona_v3 method."""

    @pytest.mark.asyncio
    async def test_get_default_persona_v3_default(self, persona_manager):
        """Test getting default persona when set to default."""
        result = await persona_manager.get_default_persona_v3()

        assert result == DEFAULT_PERSONALITY

    @pytest.mark.asyncio
    async def test_get_default_persona_v3_custom(self, persona_manager):
        """Test getting custom default persona."""
        persona_manager.personas_v3 = [
            {"name": "custom", "prompt": "Custom prompt", "begin_dialogs": []}
        ]
        persona_manager.acm.get_conf.return_value = {
            "provider_settings": {"default_personality": "custom"}
        }

        result = await persona_manager.get_default_persona_v3()

        assert result["name"] == "custom"

    @pytest.mark.asyncio
    async def test_get_default_persona_v3_fallback(self, persona_manager):
        """Test fallback when custom persona not found."""
        persona_manager.personas_v3 = []
        persona_manager.acm.get_conf.return_value = {
            "provider_settings": {"default_personality": "non-existent"}
        }

        result = await persona_manager.get_default_persona_v3()

        assert result == DEFAULT_PERSONALITY


class TestCreatePersona:
    """Tests for create_persona method."""

    @pytest.mark.asyncio
    async def test_create_persona(self, persona_manager, mock_db, sample_persona):
        """Test creating a new persona."""
        mock_db.get_persona_by_id.return_value = None
        mock_db.insert_persona.return_value = sample_persona

        with patch.object(persona_manager, "get_v3_persona_data"):
            result = await persona_manager.create_persona(
                persona_id="test-persona",
                system_prompt="You are helpful.",
                begin_dialogs=["Hello!"],
                tools=["tool1"],
            )

        assert result == sample_persona
        assert sample_persona in persona_manager.personas
        mock_db.insert_persona.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_persona_already_exists(self, persona_manager, mock_db, sample_persona):
        """Test creating a persona that already exists."""
        mock_db.get_persona_by_id.return_value = sample_persona

        with pytest.raises(ValueError, match="already exists"):
            await persona_manager.create_persona(
                persona_id="test-persona",
                system_prompt="You are helpful.",
            )


class TestUpdatePersona:
    """Tests for update_persona method."""

    @pytest.mark.asyncio
    async def test_update_persona(self, persona_manager, mock_db, sample_persona):
        """Test updating a persona."""
        updated_persona = Persona(
            persona_id="test-persona",
            system_prompt="Updated prompt",
            begin_dialogs=[],
            tools=None,
            skills=None,
        )
        mock_db.get_persona_by_id.return_value = sample_persona
        mock_db.update_persona.return_value = updated_persona
        persona_manager.personas = [sample_persona]

        with patch.object(persona_manager, "get_v3_persona_data"):
            result = await persona_manager.update_persona(
                persona_id="test-persona",
                system_prompt="Updated prompt",
            )

        assert result == updated_persona
        mock_db.update_persona.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_persona_not_found(self, persona_manager, mock_db):
        """Test updating a non-existing persona."""
        mock_db.get_persona_by_id.return_value = None

        with pytest.raises(ValueError, match="does not exist"):
            await persona_manager.update_persona(
                persona_id="non-existent",
                system_prompt="New prompt",
            )


class TestDeletePersona:
    """Tests for delete_persona method."""

    @pytest.mark.asyncio
    async def test_delete_persona(self, persona_manager, mock_db, sample_persona):
        """Test deleting a persona."""
        mock_db.get_persona_by_id.return_value = sample_persona
        persona_manager.personas = [sample_persona]

        with patch.object(persona_manager, "get_v3_persona_data"):
            await persona_manager.delete_persona("test-persona")

        mock_db.delete_persona.assert_called_once_with("test-persona")
        assert sample_persona not in persona_manager.personas

    @pytest.mark.asyncio
    async def test_delete_persona_not_found(self, persona_manager, mock_db):
        """Test deleting a non-existing persona."""
        mock_db.get_persona_by_id.return_value = None

        with pytest.raises(ValueError, match="does not exist"):
            await persona_manager.delete_persona("non-existent")


class TestGetAllPersonas:
    """Tests for get_all_personas method."""

    @pytest.mark.asyncio
    async def test_get_all_personas(self, persona_manager, mock_db, sample_persona):
        """Test getting all personas."""
        mock_db.get_personas.return_value = [sample_persona]

        result = await persona_manager.get_all_personas()

        assert len(result) == 1
        assert result[0] == sample_persona


class TestGetPersonasByFolder:
    """Tests for get_personas_by_folder method."""

    @pytest.mark.asyncio
    async def test_get_personas_by_folder(self, persona_manager, mock_db, sample_persona):
        """Test getting personas by folder."""
        sample_persona.folder_id = "folder-1"
        mock_db.get_personas_by_folder.return_value = [sample_persona]

        result = await persona_manager.get_personas_by_folder("folder-1")

        assert len(result) == 1
        mock_db.get_personas_by_folder.assert_called_once_with("folder-1")

    @pytest.mark.asyncio
    async def test_get_personas_root_folder(self, persona_manager, mock_db):
        """Test getting personas in root folder."""
        mock_db.get_personas_by_folder.return_value = []

        await persona_manager.get_personas_by_folder(None)

        mock_db.get_personas_by_folder.assert_called_once_with(None)


class TestMovePersonaToFolder:
    """Tests for move_persona_to_folder method."""

    @pytest.mark.asyncio
    async def test_move_persona_to_folder(self, persona_manager, mock_db, sample_persona):
        """Test moving persona to a folder."""
        updated_persona = Persona(
            persona_id="test-persona",
            system_prompt="You are a helpful assistant.",
            begin_dialogs=["Hello!", "Hi there!"],
            tools=["tool1"],
            skills=["skill1"],
            folder_id="folder-1",
            sort_order=0,
        )
        mock_db.move_persona_to_folder.return_value = updated_persona
        persona_manager.personas = [sample_persona]

        result = await persona_manager.move_persona_to_folder("test-persona", "folder-1")

        mock_db.move_persona_to_folder.assert_called_once_with("test-persona", "folder-1")
        assert result == updated_persona
        assert persona_manager.personas[0] == updated_persona


class TestFolderManagement:
    """Tests for folder management methods."""

    @pytest.mark.asyncio
    async def test_create_folder(self, persona_manager, mock_db, sample_folder):
        """Test creating a folder."""
        mock_db.insert_persona_folder.return_value = sample_folder

        result = await persona_manager.create_folder(
            name="Test Folder",
            parent_id=None,
            description="A test folder",
        )

        mock_db.insert_persona_folder.assert_called_once_with(
            name="Test Folder",
            parent_id=None,
            description="A test folder",
            sort_order=0,
        )
        assert result == sample_folder

    @pytest.mark.asyncio
    async def test_get_folder(self, persona_manager, mock_db, sample_folder):
        """Test getting a folder."""
        mock_db.get_persona_folder_by_id.return_value = sample_folder

        result = await persona_manager.get_folder("test-folder")

        mock_db.get_persona_folder_by_id.assert_called_once_with("test-folder")
        assert result == sample_folder

    @pytest.mark.asyncio
    async def test_get_folders(self, persona_manager, mock_db):
        """Test getting folders."""
        mock_db.get_persona_folders.return_value = []

        await persona_manager.get_folders(parent_id=None)

        mock_db.get_persona_folders.assert_called_once_with(None)

    @pytest.mark.asyncio
    async def test_get_all_folders(self, persona_manager, mock_db):
        """Test getting all folders."""
        mock_db.get_all_persona_folders.return_value = []

        await persona_manager.get_all_folders()

        mock_db.get_all_persona_folders.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_folder(self, persona_manager, mock_db, sample_folder):
        """Test updating a folder."""
        mock_db.update_persona_folder.return_value = sample_folder

        result = await persona_manager.update_folder(
            folder_id="test-folder",
            name="Updated Name",
        )

        mock_db.update_persona_folder.assert_called_once_with(
            folder_id="test-folder",
            name="Updated Name",
            parent_id=None,
            description=None,
            sort_order=None,
        )
        assert result == sample_folder

    @pytest.mark.asyncio
    async def test_delete_folder(self, persona_manager, mock_db):
        """Test deleting a folder."""
        await persona_manager.delete_folder("test-folder")

        mock_db.delete_persona_folder.assert_called_once_with("test-folder")


class TestGetFolderTree:
    """Tests for get_folder_tree method."""

    @pytest.mark.asyncio
    async def test_get_folder_tree_empty(self, persona_manager, mock_db):
        """Test getting folder tree when empty."""
        mock_db.get_all_persona_folders.return_value = []

        result = await persona_manager.get_folder_tree()

        assert result == []

    @pytest.mark.asyncio
    async def test_get_folder_tree_with_folders(self, persona_manager, mock_db):
        """Test getting folder tree with nested folders."""
        folders = [
            PersonaFolder(folder_id="root1", name="Root 1", parent_id=None, sort_order=0),
            PersonaFolder(folder_id="child1", name="Child 1", parent_id="root1", sort_order=0),
            PersonaFolder(folder_id="root2", name="Root 2", parent_id=None, sort_order=1),
        ]
        mock_db.get_all_persona_folders.return_value = folders

        result = await persona_manager.get_folder_tree()

        assert len(result) == 2  # Two root folders
        assert result[0]["folder_id"] == "root1"
        assert len(result[0]["children"]) == 1  # One child in root1
        assert result[0]["children"][0]["folder_id"] == "child1"


class TestBatchUpdateSortOrder:
    """Tests for batch_update_sort_order method."""

    @pytest.mark.asyncio
    async def test_batch_update_sort_order(self, persona_manager, mock_db):
        """Test batch updating sort order."""
        items = [
            {"id": "persona1", "type": "persona", "sort_order": 1},
            {"id": "folder1", "type": "folder", "sort_order": 2},
        ]
        mock_db.get_personas.return_value = []

        with patch.object(persona_manager, "get_v3_persona_data"):
            await persona_manager.batch_update_sort_order(items)

        mock_db.batch_update_sort_order.assert_called_once_with(items)


class TestGetV3PersonaData:
    """Tests for get_v3_persona_data method."""

    def test_get_v3_persona_data_empty(self, persona_manager):
        """Test getting V3 persona data when empty."""
        persona_manager.personas = []

        config, personas_v3, selected = persona_manager.get_v3_persona_data()

        assert config == []
        assert selected == DEFAULT_PERSONALITY

    def test_get_v3_persona_data_with_personas(self, persona_manager, sample_persona):
        """Test getting V3 persona data with personas."""
        persona_manager.personas = [sample_persona]

        config, personas_v3, selected = persona_manager.get_v3_persona_data()

        assert len(config) == 1
        assert config[0]["name"] == "test-persona"
        assert len(personas_v3) >= 1

    def test_get_v3_persona_data_odd_begin_dialogs(self, persona_manager):
        """Test handling odd number of begin_dialogs."""
        persona = Persona(
            persona_id="test",
            system_prompt="Test",
            begin_dialogs=["One", "Two", "Three"],  # Odd number
            tools=None,
            skills=None,
        )
        persona_manager.personas = [persona]

        with patch("astrbot.core.persona_mgr.logger") as mock_logger:
            config, personas_v3, selected = persona_manager.get_v3_persona_data()

        # Should log error for odd number of dialogs
        mock_logger.error.assert_called()
