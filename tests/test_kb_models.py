"""Knowledge models keep defaults, identifiers, and database constraints."""

from uuid import UUID

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, create_engine, select

from astrbot.core.knowledge_base.models import (
    BaseKBModel,
    KBDocument,
    KBMedia,
    KnowledgeBase,
)


def test_knowledge_base_defaults_are_independent():
    first = KnowledgeBase(kb_name="first")
    second = KnowledgeBase(kb_name="second")
    assert UUID(first.kb_id) != UUID(second.kb_id)
    assert (first.chunk_size, first.chunk_overlap) == (512, 50)
    assert (first.top_k_dense, first.top_k_sparse, first.top_m_final) == (50, 50, 5)
    assert (first.doc_count, first.chunk_count, first.emoji) == (0, 0, "📚")
    assert first.created_at.tzinfo is not None
    first.doc_count = 4
    assert second.doc_count == 0


@pytest.mark.parametrize(
    ("model", "values", "id_field"),
    [
        (
            KBDocument,
            {
                "kb_id": "kb-1",
                "doc_name": "manual.md",
                "file_type": "md",
                "file_size": 4,
                "file_path": "manual.md",
            },
            "doc_id",
        ),
        (
            KBMedia,
            {
                "kb_id": "kb-1",
                "doc_id": "doc-1",
                "media_type": "image",
                "file_name": "photo.png",
                "file_path": "photo.png",
                "file_size": 4,
                "mime_type": "image/png",
            },
            "media_id",
        ),
    ],
)
def test_model_roundtrip_preserves_owner_and_metadata(model, values, id_field):
    record = model(**values)
    restored = model.model_validate(record.model_dump())
    assert str(UUID(getattr(record, id_field))) == getattr(restored, id_field)
    for key, value in values.items():
        assert getattr(restored, key) == value
    assert restored.created_at == record.created_at


def test_duplicate_names_roll_back_without_losing_existing_record():
    engine = create_engine("sqlite://")
    try:
        BaseKBModel.metadata.create_all(engine)
        with Session(engine) as session:
            original = KnowledgeBase(kb_name="manual")
            session.add(original)
            session.commit()
            original_id = original.kb_id
            session.add(KnowledgeBase(kb_name="manual"))
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
            records = session.exec(select(KnowledgeBase)).all()
            assert [(item.kb_id, item.kb_name) for item in records] == [
                (original_id, "manual")
            ]
    finally:
        engine.dispose()
