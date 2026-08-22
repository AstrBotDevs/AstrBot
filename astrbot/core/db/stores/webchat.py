from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, delete, select

from astrbot.core.db.po import WebChatThread


class WebChatThreadStoreMixin:
    async def create_webchat_thread(
        self,
        creator: str,
        parent_session_id: str,
        parent_message_id: int,
        base_checkpoint_id: str,
        selected_text: str,
    ) -> WebChatThread:
        """Create a WebChat side thread."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                thread = WebChatThread(
                    creator=creator,
                    parent_session_id=parent_session_id,
                    parent_message_id=parent_message_id,
                    base_checkpoint_id=base_checkpoint_id,
                    selected_text=selected_text,
                )
                session.add(thread)
                await session.flush()
                await session.refresh(thread)
                return thread

    async def get_webchat_thread_by_id(
        self,
        thread_id: str,
    ) -> WebChatThread | None:
        """Get a WebChat side thread by thread_id."""
        async with self.get_db() as session:
            session: AsyncSession
            result = await session.execute(
                select(WebChatThread).where(WebChatThread.thread_id == thread_id)
            )
            return result.scalar_one_or_none()

    async def get_webchat_threads_by_parent_session(
        self,
        parent_session_id: str,
        creator: str | None = None,
    ) -> list[WebChatThread]:
        """Get side threads for a parent WebChat session."""
        async with self.get_db() as session:
            session: AsyncSession
            query = select(WebChatThread).where(
                WebChatThread.parent_session_id == parent_session_id
            )
            if creator is not None:
                query = query.where(WebChatThread.creator == creator)
            query = query.order_by(col(WebChatThread.created_at))
            result = await session.execute(query)
            return list(result.scalars().all())

    async def get_webchat_thread_by_parent_message_and_text(
        self,
        parent_session_id: str,
        parent_message_id: int,
        selected_text: str,
        creator: str | None = None,
    ) -> WebChatThread | None:
        """Get an existing side thread for the same selected text."""
        async with self.get_db() as session:
            session: AsyncSession
            query = select(WebChatThread).where(
                WebChatThread.parent_session_id == parent_session_id,
                WebChatThread.parent_message_id == parent_message_id,
                WebChatThread.selected_text == selected_text,
            )
            if creator is not None:
                query = query.where(WebChatThread.creator == creator)
            result = await session.execute(query)
            return result.scalar_one_or_none()

    async def delete_webchat_thread(self, thread_id: str) -> None:
        """Delete a WebChat side thread."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                await session.execute(
                    delete(WebChatThread).where(
                        col(WebChatThread.thread_id) == thread_id
                    )
                )

    async def delete_webchat_threads_by_parent_session(
        self,
        parent_session_id: str,
    ) -> list[str]:
        """Delete side threads for a parent WebChat session."""
        threads = await self.get_webchat_threads_by_parent_session(parent_session_id)
        thread_ids = [thread.thread_id for thread in threads]
        if not thread_ids:
            return []
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                await session.execute(
                    delete(WebChatThread).where(
                        col(WebChatThread.thread_id).in_(thread_ids)
                    )
                )
        return thread_ids

    async def delete_webchat_threads_by_parent_message_ids(
        self,
        parent_session_id: str,
        parent_message_ids: list[int],
    ) -> list[str]:
        """Delete side threads linked to parent message IDs."""
        if not parent_message_ids:
            return []
        async with self.get_db() as session:
            session: AsyncSession
            result = await session.execute(
                select(WebChatThread.thread_id).where(
                    WebChatThread.parent_session_id == parent_session_id,
                    col(WebChatThread.parent_message_id).in_(parent_message_ids),
                )
            )
            thread_ids = list(result.scalars().all())
        if not thread_ids:
            return []
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                await session.execute(
                    delete(WebChatThread).where(
                        col(WebChatThread.thread_id).in_(thread_ids)
                    )
                )
        return thread_ids
