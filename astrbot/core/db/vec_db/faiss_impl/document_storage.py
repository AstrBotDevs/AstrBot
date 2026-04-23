import json
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from sqlalchemy import Column, Text, bindparam
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import Field, MetaData, SQLModel, col, func, select, text

from astrbot.core import logger
from astrbot.core.knowledge_base.retrieval.tokenizer import (
    build_fts5_or_query,
    load_stopwords,
    to_fts5_search_text,
)

FTS_TABLE_NAME = "documents_fts"
FTS_REBUILD_BATCH_SIZE = 1000


class BaseDocModel(SQLModel, table=False):
    metadata = MetaData()


class Document(BaseDocModel, table=True):
    """SQLModel for documents table."""

    __tablename__ = "documents"  # type: ignore

    id: int | None = Field(
        default=None,
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
    )
    doc_id: str = Field(nullable=False)
    text: str = Field(nullable=False)
    metadata_: str | None = Field(default=None, sa_column=Column("metadata", Text))
    created_at: datetime | None = Field(default=None)
    updated_at: datetime | None = Field(default=None)


class DocumentStorage:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self.DATABASE_URL = f"sqlite+aiosqlite:///{db_path}"
        self.engine: AsyncEngine | None = None
        self.async_session_maker: sessionmaker | None = None
        self.sqlite_init_path = os.path.join(
            os.path.dirname(__file__),
            "sqlite_init.sql",
        )
        self.fts5_available = False
        self._fts_contentless_delete = False
        self._fts_index_ready = False
        self._stopwords: set[str] | None = None

    async def initialize(self) -> None:
        """Initialize the SQLite database and create the documents table if it doesn't exist."""
        await self.connect()
        async with self.engine.begin() as conn:  # type: ignore
            # Create tables using SQLModel
            await conn.run_sync(BaseDocModel.metadata.create_all)

            try:
                await conn.execute(
                    text(
                        "ALTER TABLE documents ADD COLUMN kb_doc_id TEXT "
                        "GENERATED ALWAYS AS (json_extract(metadata, '$.kb_doc_id')) STORED",
                    ),
                )
                await conn.execute(
                    text(
                        "ALTER TABLE documents ADD COLUMN user_id TEXT "
                        "GENERATED ALWAYS AS (json_extract(metadata, '$.user_id')) STORED",
                    ),
                )

                # Create indexes
                await conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_documents_kb_doc_id ON documents(kb_doc_id)",
                    ),
                )
                await conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_documents_user_id ON documents(user_id)",
                    ),
                )
            except BaseException:
                pass

            await self._initialize_fts5(conn)
            await conn.commit()

    async def _initialize_fts5(self, executor) -> None:
        try:
            await self._create_fts5_table(executor, if_not_exists=True)

            is_valid_fts5, has_contentless_delete = await self._inspect_fts5_table(
                executor,
            )
            if not is_valid_fts5:
                logger.warning(
                    f"Detected incompatible legacy table `{FTS_TABLE_NAME}` in "
                    f"{self.db_path}; recreating FTS5 table.",
                )
                await executor.execute(text(f"DROP TABLE IF EXISTS {FTS_TABLE_NAME}"))
                await self._create_fts5_table(executor, if_not_exists=False)

                is_valid_fts5, has_contentless_delete = await self._inspect_fts5_table(
                    executor,
                )
                if not is_valid_fts5:
                    raise RuntimeError(
                        f"Failed to create a valid FTS5 table `{FTS_TABLE_NAME}`",
                    )

            self.fts5_available = True
            self._fts_contentless_delete = has_contentless_delete
        except Exception as e:
            self.fts5_available = False
            self._fts_contentless_delete = False
            logger.warning(
                f"SQLite FTS5 is unavailable for document storage {self.db_path}; "
                f"falling back to in-memory BM25 sparse retrieval: {e}",
            )

    async def _create_fts5_table(self, executor, if_not_exists: bool) -> None:
        create_clause = (
            "CREATE VIRTUAL TABLE IF NOT EXISTS"
            if if_not_exists
            else "CREATE VIRTUAL TABLE"
        )
        try:
            await executor.execute(
                text(
                    f"""
                    {create_clause} {FTS_TABLE_NAME}
                    USING fts5(
                        search_text,
                        content='',
                        contentless_delete=1,
                        tokenize='unicode61'
                    )
                    """,
                ),
            )
        except Exception:
            await executor.execute(
                text(
                    f"""
                    {create_clause} {FTS_TABLE_NAME}
                    USING fts5(
                        search_text,
                        content='',
                        tokenize='unicode61'
                    )
                    """,
                ),
            )

    async def _inspect_fts5_table(self, executor) -> tuple[bool, bool]:
        schema_result = await executor.execute(
            text(
                """
                SELECT sql
                FROM sqlite_master
                WHERE type='table' AND name=:table_name
                """,
            ),
            {"table_name": FTS_TABLE_NAME},
        )
        create_sql = schema_result.scalar_one_or_none()
        if not create_sql:
            return False, False

        normalized_sql = create_sql.lower()
        if "virtual table" not in normalized_sql or "using fts5" not in normalized_sql:
            return False, False

        pragma_result = await executor.execute(
            text(f"PRAGMA table_info({FTS_TABLE_NAME})"),
        )
        columns = {row[1] for row in pragma_result.fetchall()}
        if "search_text" not in columns:
            return False, False

        normalized_sql_no_whitespace = "".join(normalized_sql.split())
        return True, "contentless_delete=1" in normalized_sql_no_whitespace

    async def connect(self) -> None:
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

    @property
    def stopwords(self) -> set[str]:
        if self._stopwords is None:
            stopwords_path = (
                Path(__file__).parents[3]
                / "knowledge_base"
                / "retrieval"
                / "hit_stopwords.txt"
            )
            self._stopwords = load_stopwords(stopwords_path)
        return self._stopwords

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
        if self.engine is None:
            logger.warning(
                "Database connection is not initialized, returning empty result",
            )
            return []

        async with self.get_session() as session:
            query = select(Document)

            for key, val in metadata_filters.items():
                query = query.where(
                    text(f"json_extract(metadata, '$.{key}') = :filter_{key}"),
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

        async with self.get_session() as session, session.begin():
            document = Document(
                doc_id=doc_id,
                text=text,
                metadata_=json.dumps(metadata),
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
            session.add(document)
            await session.flush()  # Flush to get the ID
            if document.id is not None:
                await self._insert_fts_row(session, int(document.id), text)
            return document.id  # type: ignore

    async def insert_documents_batch(
        self,
        doc_ids: list[str],
        texts: list[str],
        metadatas: list[dict],
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

        async with self.get_session() as session, session.begin():
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
            await self._insert_fts_rows_batch(session, documents, texts)
            return [doc.id for doc in documents]  # type: ignore

    async def delete_document_by_doc_id(self, doc_id: str) -> None:
        """Delete a document by its doc_id.

        Args:
            doc_id (str): The doc_id of the document to delete.

        """
        assert self.engine is not None, "Database connection is not initialized."

        async with self.get_session() as session, session.begin():
            query = select(Document).where(col(Document.doc_id) == doc_id)
            result = await session.execute(query)
            document = result.scalar_one_or_none()

            if document:
                if document.id is not None:
                    await self._delete_fts_row(session, int(document.id), document.text)
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

    async def update_document_by_doc_id(self, doc_id: str, new_text: str) -> None:
        """Update a document by its doc_id.

        Args:
            doc_id (str): The doc_id.
            new_text (str): The new text to update the document with.

        """
        assert self.engine is not None, "Database connection is not initialized."

        async with self.get_session() as session, session.begin():
            query = select(Document).where(col(Document.doc_id) == doc_id)
            result = await session.execute(query)
            document = result.scalar_one_or_none()

            if document:
                if document.id is not None:
                    await self._delete_fts_row(session, int(document.id), document.text)
                document.text = new_text
                document.updated_at = datetime.now()
                session.add(document)
                if document.id is not None:
                    await self._insert_fts_row(session, int(document.id), new_text)

    async def delete_documents(self, metadata_filters: dict) -> None:
        """Delete documents by their metadata filters.

        Args:
            metadata_filters (dict): The metadata filters to apply.

        """
        if self.engine is None:
            logger.warning(
                "Database connection is not initialized, skipping delete operation",
            )
            return

        async with self.get_session() as session, session.begin():
            query = select(Document)

            for key, val in metadata_filters.items():
                query = query.where(
                    text(f"json_extract(metadata, '$.{key}') = :filter_{key}"),
                ).params(**{f"filter_{key}": val})

            result = await session.execute(query)
            documents = result.scalars().all()

            await self._delete_fts_rows_batch(session, documents)
            for doc in documents:
                await session.delete(doc)

    async def count_documents(self, metadata_filters: dict | None = None) -> int:
        """Count documents in the database.

        Args:
            metadata_filters (dict | None): Metadata filters to apply.

        Returns:
            int: The count of documents.

        """
        if self.engine is None:
            logger.warning("Database connection is not initialized, returning 0")
            return 0

        async with self.get_session() as session:
            query = select(func.count(col(Document.id)))

            if metadata_filters:
                for key, val in metadata_filters.items():
                    query = query.where(
                        text(f"json_extract(metadata, '$.{key}') = :filter_{key}"),
                    ).params(**{f"filter_{key}": val})

            result = await session.execute(query)
            count = result.scalar_one_or_none()
            return count if count is not None else 0

    async def ensure_fts_index(self) -> bool:
        """Ensure the FTS5 sparse index exists and matches the documents table."""
        if not self.fts5_available:
            return False
        if self._fts_index_ready:
            return True

        assert self.engine is not None, "Database connection is not initialized."

        async with self.get_session() as session:
            doc_count = await self._count_documents_in_session(session)
            fts_count = await self._count_fts_rows(session)
            if doc_count == fts_count:
                self._fts_index_ready = True
                return True

        logger.info(
            f"Rebuilding FTS5 sparse index for {self.db_path}: "
            f"documents={doc_count}, fts_rows={fts_count}",
        )
        await self.rebuild_fts_index()
        return self.fts5_available

    async def rebuild_fts_index(self) -> None:
        """Rebuild the contentless FTS5 sparse index from documents."""
        if not self.fts5_available:
            return

        assert self.engine is not None, "Database connection is not initialized."

        async with self.get_session() as session, session.begin():
            await session.execute(text(f"DROP TABLE IF EXISTS {FTS_TABLE_NAME}"))
            await self._initialize_fts5(session)
            if not self.fts5_available:
                return

            last_id = 0
            while True:
                query = (
                    select(Document)
                    .where(col(Document.id) > last_id)
                    .order_by(col(Document.id))
                    .limit(FTS_REBUILD_BATCH_SIZE)
                )
                result = await session.execute(query)
                documents = result.scalars().all()
                if not documents:
                    break

                await self._insert_fts_rows_batch(
                    session,
                    documents,
                    [doc.text for doc in documents],
                )
                last_id = int(documents[-1].id or last_id)

        self._fts_index_ready = True

    async def search_sparse(
        self,
        query_tokens: list[str],
        limit: int,
    ) -> list[dict] | None:
        """Search chunks using the FTS5 sparse index.

        Returns None when FTS5 is unavailable so callers can fall back to another
        sparse retrieval implementation.
        """
        if limit <= 0:
            return []
        if not await self.ensure_fts_index():
            return None

        match_query = build_fts5_or_query(query_tokens)
        if not match_query:
            return []

        async with self.get_session() as session:
            try:
                result = await session.execute(
                    text(
                        f"""
                        SELECT
                            d.id AS id,
                            d.doc_id AS doc_id,
                            d.text AS text,
                            d.metadata AS metadata,
                            d.created_at AS created_at,
                            d.updated_at AS updated_at,
                            bm25({FTS_TABLE_NAME}) AS score
                        FROM {FTS_TABLE_NAME}
                        JOIN documents d ON d.id = {FTS_TABLE_NAME}.rowid
                        WHERE {FTS_TABLE_NAME} MATCH :query
                        ORDER BY score ASC, d.id ASC
                        LIMIT :limit
                        """,
                    ),
                    {"query": match_query, "limit": int(limit)},
                )
            except Exception as e:
                logger.warning(
                    f"FTS5 sparse search failed for {self.db_path}; "
                    f"falling back to in-memory BM25: {e}",
                )
                self.fts5_available = False
                return None

            rows = result.mappings().all()
            return [
                {
                    "id": row["id"],
                    "doc_id": row["doc_id"],
                    "text": row["text"],
                    "metadata": row["metadata"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "score": float(row["score"]),
                }
                for row in rows
            ]

    async def _count_documents_in_session(self, session: AsyncSession) -> int:
        result = await session.execute(select(func.count(col(Document.id))))
        count = result.scalar_one_or_none()
        return int(count or 0)

    async def _count_fts_rows(self, session: AsyncSession) -> int:
        result = await session.execute(
            text(f"SELECT count(*) FROM {FTS_TABLE_NAME}"),
        )
        count = result.scalar_one_or_none()
        return int(count or 0)

    async def _insert_fts_row(
        self,
        session: AsyncSession,
        rowid: int,
        content: str,
    ) -> None:
        if not self.fts5_available:
            return

        search_text = to_fts5_search_text(content, self.stopwords)
        await session.execute(
            text(
                f"""
                INSERT INTO {FTS_TABLE_NAME}(rowid, search_text)
                VALUES (:rowid, :search_text)
                """,
            ),
            {"rowid": rowid, "search_text": search_text},
        )

    async def _insert_fts_rows_batch(
        self,
        session: AsyncSession,
        documents: list[Document],
        contents: list[str],
    ) -> None:
        if not self.fts5_available:
            return

        fts_params = [
            {
                "rowid": int(doc.id),
                "search_text": to_fts5_search_text(content, self.stopwords),
            }
            for doc, content in zip(documents, contents)
            if doc.id is not None
        ]
        if not fts_params:
            return

        await session.execute(
            text(
                f"""
                INSERT INTO {FTS_TABLE_NAME}(rowid, search_text)
                VALUES (:rowid, :search_text)
                """,
            ),
            fts_params,
        )

    async def _delete_fts_row(
        self,
        session: AsyncSession,
        rowid: int,
        content: str,
    ) -> None:
        if not self.fts5_available:
            return

        if self._fts_contentless_delete:
            await session.execute(
                text(f"DELETE FROM {FTS_TABLE_NAME} WHERE rowid = :rowid"),
                {"rowid": rowid},
            )
            return

        if not await self._fts_row_exists(session, rowid):
            return

        search_text = to_fts5_search_text(content, self.stopwords)
        await session.execute(
            text(
                f"""
                INSERT INTO {FTS_TABLE_NAME}({FTS_TABLE_NAME}, rowid, search_text)
                VALUES ('delete', :rowid, :search_text)
                """,
            ),
            {"rowid": rowid, "search_text": search_text},
        )

    async def _delete_fts_rows_batch(
        self,
        session: AsyncSession,
        documents: list[Document],
    ) -> None:
        if not self.fts5_available:
            return

        docs_with_ids = [doc for doc in documents if doc.id is not None]
        if not docs_with_ids:
            return

        if self._fts_contentless_delete:
            await session.execute(
                text(f"DELETE FROM {FTS_TABLE_NAME} WHERE rowid = :rowid"),
                [{"rowid": int(doc.id)} for doc in docs_with_ids if doc.id is not None],
            )
            return

        existing_rowids = await self._existing_fts_rowids(
            session,
            [int(doc.id) for doc in docs_with_ids if doc.id is not None],
        )
        fts_params = [
            {
                "rowid": int(doc.id),
                "search_text": to_fts5_search_text(doc.text, self.stopwords),
            }
            for doc in docs_with_ids
            if doc.id is not None and int(doc.id) in existing_rowids
        ]
        if not fts_params:
            return

        await session.execute(
            text(
                f"""
                INSERT INTO {FTS_TABLE_NAME}({FTS_TABLE_NAME}, rowid, search_text)
                VALUES ('delete', :rowid, :search_text)
                """,
            ),
            fts_params,
        )

    async def _fts_row_exists(self, session: AsyncSession, rowid: int) -> bool:
        result = await session.execute(
            text(f"SELECT 1 FROM {FTS_TABLE_NAME} WHERE rowid = :rowid LIMIT 1"),
            {"rowid": rowid},
        )
        return result.scalar_one_or_none() is not None

    async def _existing_fts_rowids(
        self,
        session: AsyncSession,
        rowids: list[int],
    ) -> set[int]:
        if not rowids:
            return set()

        result = await session.execute(
            text(
                f"SELECT rowid FROM {FTS_TABLE_NAME} WHERE rowid IN :rowids"
            ).bindparams(bindparam("rowids", expanding=True)),
            {"rowids": rowids},
        )
        return {int(row[0]) for row in result.fetchall()}

    async def get_user_ids(self) -> list[str]:
        """Retrieve all user IDs from the documents table.

        Returns:
            list: A list of user IDs.

        """
        assert self.engine is not None, "Database connection is not initialized."

        async with self.get_session() as session:
            query = text(
                "SELECT DISTINCT user_id FROM documents WHERE user_id IS NOT NULL",
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

    async def close(self) -> None:
        """Close the connection to the SQLite database."""
        if self.engine:
            await self.engine.dispose()
            self.engine = None
            self.async_session_maker = None
