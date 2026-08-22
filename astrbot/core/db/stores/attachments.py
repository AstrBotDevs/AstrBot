import typing as T

from sqlalchemy import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, delete, select

from astrbot.core.db.po import Attachment


class AttachmentStoreMixin:
    async def insert_attachment(self, path, type, mime_type):
        """Insert a new attachment record."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                new_attachment = Attachment(
                    path=path,
                    type=type,
                    mime_type=mime_type,
                )
                session.add(new_attachment)
                return new_attachment

    async def get_attachment_by_id(self, attachment_id):
        """Get an attachment by its ID."""
        async with self.get_db() as session:
            session: AsyncSession
            query = select(Attachment).where(Attachment.attachment_id == attachment_id)
            result = await session.execute(query)
            return result.scalar_one_or_none()

    async def get_attachments(self, attachment_ids: list[str]) -> list:
        """Get multiple attachments by their IDs."""
        if not attachment_ids:
            return []
        async with self.get_db() as session:
            session: AsyncSession
            query = select(Attachment).where(
                col(Attachment.attachment_id).in_(attachment_ids)
            )
            result = await session.execute(query)
            return list(result.scalars().all())

    async def delete_attachment(self, attachment_id: str) -> bool:
        """Delete an attachment by its ID.

        Returns True if the attachment was deleted, False if it was not found.
        """
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                query = delete(Attachment).where(
                    col(Attachment.attachment_id) == attachment_id
                )
                result = T.cast(CursorResult, await session.execute(query))
                return result.rowcount > 0

    async def delete_attachments(self, attachment_ids: list[str]) -> int:
        """Delete multiple attachments by their IDs.

        Returns the number of attachments deleted.
        """
        if not attachment_ids:
            return 0
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                query = delete(Attachment).where(
                    col(Attachment.attachment_id).in_(attachment_ids)
                )
                result = T.cast(CursorResult, await session.execute(query))
                return result.rowcount
