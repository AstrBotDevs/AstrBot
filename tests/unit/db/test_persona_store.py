import pytest

from astrbot.core.db.sqlite import SQLiteDatabase


@pytest.mark.asyncio
async def test_batch_update_sort_order_reorders_personas_and_folders(
    temp_db: SQLiteDatabase,
):
    root_b = await temp_db.insert_persona_folder(name="B", sort_order=20)
    root_a = await temp_db.insert_persona_folder(name="A", sort_order=10)
    await temp_db.insert_persona(
        persona_id="persona-b",
        system_prompt="prompt",
        folder_id=None,
        sort_order=20,
    )
    await temp_db.insert_persona(
        persona_id="persona-a",
        system_prompt="prompt",
        folder_id=None,
        sort_order=10,
    )

    await temp_db.batch_update_sort_order(
        [
            {"id": root_b.folder_id, "type": "folder", "sort_order": 0},
            {"id": "persona-b", "type": "persona", "sort_order": 0},
            {"id": None, "type": "persona", "sort_order": 99},
            {"id": root_a.folder_id, "type": "unknown", "sort_order": 0},
        ]
    )

    folders = await temp_db.get_persona_folders()
    personas = await temp_db.get_personas_by_folder(None)

    assert [folder.name for folder in folders] == ["B", "A"]
    assert [persona.persona_id for persona in personas] == ["persona-b", "persona-a"]


@pytest.mark.asyncio
async def test_update_persona_folder_can_clear_parent_and_description(
    temp_db: SQLiteDatabase,
):
    parent = await temp_db.insert_persona_folder(name="Parent")
    child = await temp_db.insert_persona_folder(
        name="Child",
        parent_id=parent.folder_id,
        description="desc",
        sort_order=5,
    )

    updated = await temp_db.update_persona_folder(
        child.folder_id,
        parent_id=None,
        description=None,
        sort_order=1,
    )

    assert updated is not None
    assert updated.parent_id is None
    assert updated.description is None
    assert updated.sort_order == 1
