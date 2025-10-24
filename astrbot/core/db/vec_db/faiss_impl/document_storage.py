import os
import json
from datetime import datetime
from contextlib import asynccontextmanager

from sqlalchemy import Text, Column
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import Field, SQLModel, select, col, func, text, MetaData


class BaseDocModel(SQLModel, table=False):
    metadata = MetaData()


class Document(BaseDocModel, table=True):
    """SQLModel for documents table."""

    __tablename__ = "documents"  # type: ignore

    id: int | None = Field(
        default=None, primary_key=True, sa_column_kwargs={"autoincrement": True}
    )
    doc_id: str = Field(nullable=False)
    text: str = Field(nullable=False)
    metadata_: str | None = Field(default=None, sa_column=Column("metadata", Text))
    created_at: datetime | None = Field(default=None)
    updated_at: datetime | None = Field(default=None)


class DocumentStorage:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.DATABASE_URL = f"sqlite+aiosqlite:///{db_path}"
        self.engine: AsyncEngine | None = None
        self.async_session_maker: sessionmaker | None = None
        self.sqlite_init_path = os.path.join(
            os.path.dirname(__file__), "sqlite_init.sql"
        )

    async def initialize(self):
        """Initialize the SQLite database and create the documents table if it doesn't exist."""
        await self.connect()
        async with self.engine.begin() as conn:  # type: ignore
            # Create tables using SQLModel
            await conn.run_sync(BaseDocModel.metadata.create_all)

            try:
                await conn.execute(
                    text(
                        "ALTER TABLE documents ADD COLUMN kb_doc_id TEXT "
                        "GENERATED ALWAYS AS (json_extract(metadata, '$.kb_doc_id')) STORED"
                    )
                )
                await conn.execute(
                    text(
                        "ALTER TABLE documents ADD COLUMN user_id TEXT "
                        "GENERATED ALWAYS AS (json_extract(metadata, '$.user_id')) STORED"
                    )
                )

                # Create indexes
                await conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_documents_kb_doc_id ON documents(kb_doc_id)"
                    )
                )
                await conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_documents_user_id ON documents(user_id)"
                    )
                )
            except BaseException:
                pass

            await conn.commit()

    async def connect(self):
        """Connect to the SQLite database."""
        if self.engine is None:
            self.engine = create_async_engine(
                self.DATABASE_URL,
                echo=False,
                future=True,
            )
            self.async_session_maker = sessionmaker(
                self.engine,  # type: ignore
                class_=AsyncSession,
                expire_on_commit=False,
            )  # type: ignore

    @asynccontextmanager
    async def get_session(self):
        """Context manager for database sessions."""
        async with self.async_session_maker() as session:  # type: ignore
            yield session

    async def get_documents(
        self,
        metadata_filters: dict,
        ids: list | None = None,
        offset: int | None = 0,
        limit: int | None = 100,
    ) -> list[dict]:
        """Retrieve documents by metadata filters and ids.

        Args:
            metadata_filters (dict): The metadata filters to apply.
            ids (list | None): Optional list of document IDs to filter.
            offset (int | None): Offset for pagination.
            limit (int | None): Limit for pagination.

        Returns:
            list: The list of documents that match the filters.
        """
        assert self.engine is not None, "Database connection is not initialized."

        async with self.get_session() as session:
            query = select(Document)

            for key, val in metadata_filters.items():
                query = query.where(
                    text(f"json_extract(metadata, '$.{key}') = :filter_{key}")
                ).params(**{f"filter_{key}": val})

            if ids is not None and len(ids) > 0:
                valid_ids = [int(i) for i in ids if i != -1]
                if valid_ids:
                    query = query.where(col(Document.id).in_(valid_ids))

            if limit is not None:
                query = query.limit(limit)
            if offset is not None:
                query = query.offset(offset)

            result = await session.execute(query)
            documents = result.scalars().all()

            return [self._document_to_dict(doc) for doc in documents]

    async def insert_document(self, doc_id: str, text: str, metadata: dict) -> int:
        """Insert a single document and return its integer ID.

        Args:
            doc_id (str): The document ID (UUID string).
            text (str): The document text.
            metadata (dict): The document metadata.

        Returns:
            int: The integer ID of the inserted document.
        """
        assert self.engine is not None, "Database connection is not initialized."

        async with self.get_session() as session:
            async with session.begin():
                document = Document(
                    doc_id=doc_id,
                    text=text,
                    metadata_=json.dumps(metadata),
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                )
                session.add(document)
                await session.flush()  # Flush to get the ID
                return document.id  # type: ignore

    async def insert_documents_batch(
        self, doc_ids: list[str], texts: list[str], metadatas: list[dict]
    ) -> list[int]:
        """Batch insert documents and return their integer IDs.

        Args:
            doc_ids (list[str]): List of document IDs (UUID strings).
            texts (list[str]): List of document texts.
            metadatas (list[dict]): List of document metadata.

        Returns:
            list[int]: List of integer IDs of the inserted documents.
        """
        assert self.engine is not None, "Database connection is not initialized."

        async with self.get_session() as session:
            async with session.begin():
                import json

                documents = []
                for doc_id, text, metadata in zip(doc_ids, texts, metadatas):
                    document = Document(
                        doc_id=doc_id,
                        text=text,
                        metadata_=json.dumps(metadata),
                        created_at=datetime.now(),
                        updated_at=datetime.now(),
                    )
                    documents.append(document)
                    session.add(document)

                await session.flush()  # Flush to get all IDs
                return [doc.id for doc in documents]  # type: ignore

    async def delete_document_by_doc_id(self, doc_id: str):
        """Delete a document by its doc_id.

        Args:
            doc_id (str): The doc_id of the document to delete.
        """
        assert self.engine is not None, "Database connection is not initialized."

        async with self.get_session() as session:
            async with session.begin():
                query = select(Document).where(col(Document.doc_id) == doc_id)
                result = await session.execute(query)
                document = result.scalar_one_or_none()

                if document:
                    await session.delete(document)

    async def get_document_by_doc_id(self, doc_id: str):
        """Retrieve a document by its doc_id.

        Args:
            doc_id (str): The doc_id of the document to retrieve.

        Returns:
            dict: The document data or None if not found.
        """
        assert self.engine is not None, "Database connection is not initialized."

        async with self.get_session() as session:
            query = select(Document).where(col(Document.doc_id) == doc_id)
            result = await session.execute(query)
            document = result.scalar_one_or_none()

            if document:
                return self._document_to_dict(document)
            return None

    async def update_document_by_doc_id(self, doc_id: str, new_text: str):
        """Update a document by its doc_id.

        Args:
            doc_id (str): The doc_id.
            new_text (str): The new text to update the document with.
        """
        assert self.engine is not None, "Database connection is not initialized."

        async with self.get_session() as session:
            async with session.begin():
                query = select(Document).where(col(Document.doc_id) == doc_id)
                result = await session.execute(query)
                document = result.scalar_one_or_none()

                if document:
                    document.text = new_text
                    document.updated_at = datetime.now()
                    session.add(document)

    async def delete_documents(self, metadata_filters: dict):
        """Delete documents by their metadata filters.

        Args:
            metadata_filters (dict): The metadata filters to apply.
        """
        assert self.engine is not None, "Database connection is not initialized."

        async with self.get_session() as session:
            async with session.begin():
                query = select(Document)

                for key, val in metadata_filters.items():
                    query = query.where(
                        text(f"json_extract(metadata, '$.{key}') = :filter_{key}")
                    ).params(**{f"filter_{key}": val})

                result = await session.execute(query)
                documents = result.scalars().all()

                for doc in documents:
                    await session.delete(doc)

    async def count_documents(self, metadata_filters: dict | None = None) -> int:
        """Count documents in the database.

        Args:
            metadata_filters (dict | None): Metadata filters to apply.

        Returns:
            int: The count of documents.
        """
        assert self.engine is not None, "Database connection is not initialized."

        async with self.get_session() as session:
            query = select(func.count(col(Document.id)))

            if metadata_filters:
                for key, val in metadata_filters.items():
                    query = query.where(
                        text(f"json_extract(metadata, '$.{key}') = :filter_{key}")
                    ).params(**{f"filter_{key}": val})

            result = await session.execute(query)
            count = result.scalar_one_or_none()
            return count if count is not None else 0

    async def get_user_ids(self) -> list[str]:
        """Retrieve all user IDs from the documents table.

        Returns:
            list: A list of user IDs.
        """
        assert self.engine is not None, "Database connection is not initialized."

        async with self.get_session() as session:
            query = text(
                "SELECT DISTINCT user_id FROM documents WHERE user_id IS NOT NULL"
            )
            result = await session.execute(query)
            rows = result.fetchall()
            return [row[0] for row in rows]

    def _document_to_dict(self, document: Document) -> dict:
        """Convert a Document model to a dictionary.

        Args:
            document (Document): The document to convert.

        Returns:
            dict: The converted dictionary.
        """
        return {
            "id": document.id,
            "doc_id": document.doc_id,
            "text": document.text,
            "metadata": document.metadata_,
            "created_at": document.created_at.isoformat()
            if isinstance(document.created_at, datetime)
            else document.created_at,
            "updated_at": document.updated_at.isoformat()
            if isinstance(document.updated_at, datetime)
            else document.updated_at,
        }

    async def tuple_to_dict(self, row):
        """Convert a tuple to a dictionary.

        Args:
            row (tuple): The row to convert.

        Returns:
            dict: The converted dictionary.

        Note: This method is kept for backward compatibility but is no longer used internally.
        """
        return {
            "id": row[0],
            "doc_id": row[1],
            "text": row[2],
            "metadata": row[3],
            "created_at": row[4],
            "updated_at": row[5],
        }

    async def close(self):
        """Close the connection to the SQLite database."""
        if self.engine:
            await self.engine.dispose()
            self.engine = None
            self.async_session_maker = None
