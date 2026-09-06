"""Test that update_conversation accepts clear_persona parameter.

BaseDatabase declares ``clear_persona: bool = False``, but SQLiteDatabase
was missing the parameter, causing ``TypeError`` when callers passed it.
"""

import pytest


def test_sqlite_update_conversation_accepts_clear_persona():
    """Verify SQLiteDatabase.update_conversation accepts all abstract params."""
    from inspect import signature
    from astrbot.core.db import BaseDatabase
    from astrbot.core.db.sqlite import SQLiteDatabase

    sig = signature(BaseDatabase.update_conversation)
    impl_sig = signature(SQLiteDatabase.update_conversation)

    for name, param in sig.parameters.items():
        assert name in impl_sig.parameters, (
            f"SQLiteDatabase.update_conversation missing parameter: {name}"
        )


@pytest.mark.asyncio
async def test_update_conversation_clear_persona_does_not_crash():
    """Call update_conversation with clear_persona=True does not raise."""
    from astrbot.core.db.sqlite import SQLiteDatabase

    db = SQLiteDatabase(":memory:")
    await db.initialize()

    try:
        result = await db.update_conversation(
            cid="test-cid",
            title="test",
            clear_persona=True,
        )
        # No conversation exists, so result should be None
        assert result is None
    except TypeError as e:
        pytest.fail(f"update_conversation(clear_persona=True) raised: {e}")
    finally:
        await db.engine.dispose()
