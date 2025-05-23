import aiosqlite
import os


class DocumentStorage:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.connection = None
        self.sqlite_init_path = os.path.join(
            os.path.dirname(__file__), "sqlite_init.sql"
        )

    async def initialize(self):
        """Initialize the SQLite database and create the documents table if it doesn't exist."""
        if not os.path.exists(self.db_path):
            await self.connect()
            async with self.connection.cursor() as cursor:
                with open(self.sqlite_init_path, "r", encoding="utf-8") as f:
                    sql_script = f.read()
                await cursor.executescript(sql_script)
            await self.connection.commit()
        else:
            await self.connect()

    async def connect(self):
        """Connect to the SQLite database."""
        self.connection = await aiosqlite.connect(self.db_path)

    async def get_documents(self, metadata_filters: dict, ids: list = None):
        """Retrieve documents by metadata filters and ids.

        Args:
            metadata_filters (dict): The metadata filters to apply.

        Returns:
            list: The list of document IDs(primary key, not doc_id) that match the filters.
        """
        # metadata filter -> SQL WHERE clause
        where_clauses = []
        values = []
        for key, val in metadata_filters.items():
            where_clauses.append(f"json_extract(metadata, '$.{key}') = ?")
            values.append(val)
        if ids is not None and len(ids) > 0:
            ids = [str(i) for i in ids if i != -1]
            where_clauses.append("id IN ({})".format(",".join("?" * len(ids))))
            values.extend(ids)
        where_sql = " AND ".join(where_clauses) or "1=1"

        result = []
        async with self.connection.cursor() as cursor:
            sql = "SELECT * FROM documents WHERE " + where_sql
            await cursor.execute(sql, values)
            for row in await cursor.fetchall():
                result.append(await self.tuple_to_dict(row))
        return result

    async def get_document_by_doc_id(self, doc_id: str):
        """Retrieve a document by its doc_id.

        Args:
            doc_id (str): The doc_id of the document to retrieve.

        Returns:
            dict: The document data.
        """
        async with self.connection.cursor() as cursor:
            await cursor.execute("SELECT * FROM documents WHERE doc_id = ?", (doc_id,))
            row = await cursor.fetchone()
            if row:
                return await self.tuple_to_dict(row)
            else:
                return None

    async def update_document_by_doc_id(self, doc_id: str, new_text: str):
        """Retrieve a document by its doc_id.

        Args:
            doc_id (str): The doc_id.
            new_text (str): The new text to update the document with.
        """
        async with self.connection.cursor() as cursor:
            await cursor.execute(
                "UPDATE documents SET text = ? WHERE doc_id = ?", (new_text, doc_id)
            )
            await self.connection.commit()

    async def get_user_ids(self) -> list[str]:
        """Retrieve all user IDs from the documents table.

        Returns:
            list: A list of user IDs.
        """
        async with self.connection.cursor() as cursor:
            await cursor.execute("SELECT DISTINCT user_id FROM documents")
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

    async def tuple_to_dict(self, row):
        """Convert a tuple to a dictionary.

        Args:
            row (tuple): The row to convert.

        Returns:
            dict: The converted dictionary.
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
        if self.connection:
            await self.connection.close()
            self.connection = None
