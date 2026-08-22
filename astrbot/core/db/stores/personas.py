import typing as T

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, delete, select, update

from astrbot.core.db.po import Persona, PersonaFolder
from astrbot.core.sentinels import NOT_GIVEN


class PersonaStoreMixin:
    async def insert_persona(
        self,
        persona_id: str,
        system_prompt: str,
        begin_dialogs: list[str] | None = None,
        tools: list[str] | None = None,
        skills: list[str] | None = None,
        custom_error_message: str | None = None,
        folder_id: str | None = None,
        sort_order: int = 0,
    ) -> Persona:
        """Insert a new persona record."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                new_persona = Persona(
                    persona_id=persona_id,
                    system_prompt=system_prompt,
                    begin_dialogs=begin_dialogs or [],
                    tools=tools,
                    skills=skills,
                    custom_error_message=custom_error_message,
                    folder_id=folder_id,
                    sort_order=sort_order,
                )
                session.add(new_persona)
                await session.flush()
                await session.refresh(new_persona)
                return new_persona

    async def get_persona_by_id(self, persona_id: str) -> Persona | None:
        """Get a persona by its ID."""
        async with self.get_db() as session:
            session: AsyncSession
            query = select(Persona).where(Persona.persona_id == persona_id)
            result = await session.execute(query)
            return result.scalar_one_or_none()

    async def get_personas(self) -> list[Persona]:
        """Get all personas for a specific bot."""
        async with self.get_db() as session:
            session: AsyncSession
            query = select(Persona)
            result = await session.execute(query)
            return list(result.scalars().all())

    async def update_persona(
        self,
        persona_id: str,
        system_prompt: str | None = None,
        begin_dialogs: list[str] | None = None,
        tools: list[str] | None | object = NOT_GIVEN,
        skills: list[str] | None | object = NOT_GIVEN,
        custom_error_message: str | None | object = NOT_GIVEN,
    ) -> Persona | None:
        """Update a persona's system prompt or begin dialogs."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                query = update(Persona).where(col(Persona.persona_id) == persona_id)
                values = {}
                if system_prompt is not None:
                    values["system_prompt"] = system_prompt
                if begin_dialogs is not None:
                    values["begin_dialogs"] = begin_dialogs
                if tools is not NOT_GIVEN:
                    values["tools"] = tools
                if skills is not NOT_GIVEN:
                    values["skills"] = skills
                if custom_error_message is not NOT_GIVEN:
                    values["custom_error_message"] = custom_error_message
                if not values:
                    return None
                query = query.values(**values)
                await session.execute(query)
        return await self.get_persona_by_id(persona_id)

    async def delete_persona(self, persona_id) -> None:
        """Delete a persona by its ID."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                await session.execute(
                    delete(Persona).where(col(Persona.persona_id) == persona_id),
                )

    # ====
    # Persona Folder Management
    # ====

    async def insert_persona_folder(
        self,
        name: str,
        parent_id: str | None = None,
        description: str | None = None,
        sort_order: int = 0,
    ) -> PersonaFolder:
        """Insert a new persona folder."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                new_folder = PersonaFolder(
                    name=name,
                    parent_id=parent_id,
                    description=description,
                    sort_order=sort_order,
                )
                session.add(new_folder)
                await session.flush()
                await session.refresh(new_folder)
                return new_folder

    async def get_persona_folder_by_id(self, folder_id: str) -> PersonaFolder | None:
        """Get a persona folder by its folder_id."""
        async with self.get_db() as session:
            session: AsyncSession
            query = select(PersonaFolder).where(PersonaFolder.folder_id == folder_id)
            result = await session.execute(query)
            return result.scalar_one_or_none()

    async def get_persona_folders(
        self, parent_id: str | None = None
    ) -> list[PersonaFolder]:
        """Get all persona folders, optionally filtered by parent_id.

        Args:
            parent_id: If None, returns root folders only. If specified, returns
                       children of that folder.
        """
        async with self.get_db() as session:
            session: AsyncSession
            if parent_id is None:
                # Get root folders (parent_id is NULL)
                query = (
                    select(PersonaFolder)
                    .where(col(PersonaFolder.parent_id).is_(None))
                    .order_by(col(PersonaFolder.sort_order), col(PersonaFolder.name))
                )
            else:
                query = (
                    select(PersonaFolder)
                    .where(PersonaFolder.parent_id == parent_id)
                    .order_by(col(PersonaFolder.sort_order), col(PersonaFolder.name))
                )
            result = await session.execute(query)
            return list(result.scalars().all())

    async def get_all_persona_folders(self) -> list[PersonaFolder]:
        """Get all persona folders."""
        async with self.get_db() as session:
            session: AsyncSession
            query = select(PersonaFolder).order_by(
                col(PersonaFolder.sort_order), col(PersonaFolder.name)
            )
            result = await session.execute(query)
            return list(result.scalars().all())

    async def update_persona_folder(
        self,
        folder_id: str,
        name: str | None = None,
        parent_id: T.Any = NOT_GIVEN,
        description: T.Any = NOT_GIVEN,
        sort_order: int | None = None,
    ) -> PersonaFolder | None:
        """Update a persona folder."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                query = update(PersonaFolder).where(
                    col(PersonaFolder.folder_id) == folder_id
                )
                values: dict[str, T.Any] = {}
                if name is not None:
                    values["name"] = name
                if parent_id is not NOT_GIVEN:
                    values["parent_id"] = parent_id
                if description is not NOT_GIVEN:
                    values["description"] = description
                if sort_order is not None:
                    values["sort_order"] = sort_order
                if not values:
                    return None
                query = query.values(**values)
                await session.execute(query)
        return await self.get_persona_folder_by_id(folder_id)

    async def delete_persona_folder(self, folder_id: str) -> None:
        """Delete a persona folder by its folder_id.

        Note: This will also set folder_id to NULL for all personas in this folder,
        moving them to the root directory.
        """
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                # Move personas to root directory
                await session.execute(
                    update(Persona)
                    .where(col(Persona.folder_id) == folder_id)
                    .values(folder_id=None)
                )
                # Delete the folder
                await session.execute(
                    delete(PersonaFolder).where(
                        col(PersonaFolder.folder_id) == folder_id
                    ),
                )

    async def move_persona_to_folder(
        self, persona_id: str, folder_id: str | None
    ) -> Persona | None:
        """Move a persona to a folder (or root if folder_id is None)."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                await session.execute(
                    update(Persona)
                    .where(col(Persona.persona_id) == persona_id)
                    .values(folder_id=folder_id)
                )
        return await self.get_persona_by_id(persona_id)

    async def get_personas_by_folder(
        self, folder_id: str | None = None
    ) -> list[Persona]:
        """Get all personas in a specific folder.

        Args:
            folder_id: If None, returns personas in root directory.
        """
        async with self.get_db() as session:
            session: AsyncSession
            if folder_id is None:
                query = (
                    select(Persona)
                    .where(col(Persona.folder_id).is_(None))
                    .order_by(col(Persona.sort_order), col(Persona.persona_id))
                )
            else:
                query = (
                    select(Persona)
                    .where(Persona.folder_id == folder_id)
                    .order_by(col(Persona.sort_order), col(Persona.persona_id))
                )
            result = await session.execute(query)
            return list(result.scalars().all())

    async def batch_update_sort_order(
        self,
        items: list[dict],
    ) -> None:
        """Batch update sort_order for personas and/or folders.

        Args:
            items: List of dicts with keys:
                - id: The persona_id or folder_id
                - type: Either "persona" or "folder"
                - sort_order: The new sort_order value
        """
        if not items:
            return

        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                for item in items:
                    item_id = item.get("id")
                    item_type = item.get("type")
                    sort_order = item.get("sort_order")

                    if item_id is None or item_type is None or sort_order is None:
                        continue

                    if item_type == "persona":
                        await session.execute(
                            update(Persona)
                            .where(col(Persona.persona_id) == item_id)
                            .values(sort_order=sort_order)
                        )
                    elif item_type == "folder":
                        await session.execute(
                            update(PersonaFolder)
                            .where(col(PersonaFolder.folder_id) == item_id)
                            .values(sort_order=sort_order)
                        )
