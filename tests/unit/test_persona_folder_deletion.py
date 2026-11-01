import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize("nested", [False, True], ids=["root-folder", "nested-folder"])
async def test_delete_folder_preserves_children_and_personas(temp_db, nested):
    """Keep descendants reachable when deleting a root or nested folder.

    Args:
        temp_db: Isolated SQLite database fixture.
        nested: Whether the deleted folder has a parent.
    """
    db = temp_db
    unrelated = await db.insert_persona_folder("Unrelated")
    parent_id = unrelated.folder_id if nested else None
    target = await db.insert_persona_folder("Target", parent_id=parent_id)
    child = await db.insert_persona_folder("Child", parent_id=target.folder_id)
    sibling = await db.insert_persona_folder("Sibling", parent_id=target.folder_id)
    grandchild = await db.insert_persona_folder("Grandchild", parent_id=child.folder_id)
    for name, folder in (
        ("direct", target),
        ("child", child),
        ("grandchild", grandchild),
        ("unrelated", unrelated),
    ):
        await db.insert_persona(name, "Test prompt", folder_id=folder.folder_id)

    await db.delete_persona_folder(target.folder_id)

    assert await db.get_persona_folder_by_id(target.folder_id) is None
    assert {folder.folder_id for folder in await db.get_persona_folders()} == {
        unrelated.folder_id,
        child.folder_id,
        sibling.folder_id,
    }
    assert {
        folder.folder_id for folder in await db.get_persona_folders(child.folder_id)
    } == {grandchild.folder_id}
    assert {folder.folder_id for folder in await db.get_all_persona_folders()} == {
        unrelated.folder_id,
        child.folder_id,
        sibling.folder_id,
        grandchild.folder_id,
    }
    assert {
        persona.persona_id: persona.folder_id for persona in await db.get_personas()
    } == {
        "direct": None,
        "child": child.folder_id,
        "grandchild": grandchild.folder_id,
        "unrelated": unrelated.folder_id,
    }
