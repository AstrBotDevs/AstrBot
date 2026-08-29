from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, delete, select, text

from astrbot.core.db.po import CommandConfig, CommandConflict
from astrbot.core.db.stores.mixin import DatabaseStoreMixin, store_session
from astrbot.core.db.stores.session import run_in_tx


class CommandStoreMixin(DatabaseStoreMixin):
    @staticmethod
    def _apply_updates(model, **updates) -> None:
        for field, value in updates.items():
            if value is not None:
                setattr(model, field, value)

    @staticmethod
    def _new_command_config(
        handler_full_name: str,
        plugin_name: str,
        module_path: str,
        original_command: str,
        *,
        command_id: str | None = None,
        resolved_command: str | None = None,
        enabled: bool | None = None,
        conflict_key: str | None = None,
        resolution_strategy: str | None = None,
        note: str | None = None,
        extra_data: dict | None = None,
        auto_managed: bool | None = None,
    ) -> CommandConfig:
        resolved_id = command_id or (
            f"{plugin_name}:{(original_command or '').replace(' ', '.')}"
        )
        return CommandConfig(
            handler_full_name=handler_full_name,
            command_id=resolved_id,
            plugin_name=plugin_name,
            module_path=module_path,
            original_command=original_command,
            resolved_command=resolved_command,
            enabled=True if enabled is None else enabled,
            conflict_key=conflict_key or original_command,
            resolution_strategy=resolution_strategy,
            note=note,
            extra_data=extra_data,
            auto_managed=bool(auto_managed),
        )

    @staticmethod
    def _new_command_conflict(
        conflict_key: str,
        handler_full_name: str,
        plugin_name: str,
        *,
        config_id: str | None = None,
        command_id: str | None = None,
        status: str | None = None,
        resolution: str | None = None,
        resolved_command: str | None = None,
        note: str | None = None,
        extra_data: dict | None = None,
        auto_generated: bool | None = None,
    ) -> CommandConflict:
        return CommandConflict(
            config_id=config_id or "",
            conflict_key=conflict_key,
            handler_full_name=handler_full_name,
            command_id=command_id or "",
            plugin_name=plugin_name,
            status=status or "pending",
            resolution=resolution,
            resolved_command=resolved_command,
            note=note,
            extra_data=extra_data,
            auto_generated=bool(auto_generated),
        )

    async def get_command_configs(self) -> list[CommandConfig]:
        async with store_session(self) as session:
            session: AsyncSession
            result = await session.execute(select(CommandConfig))
            return list(result.scalars().all())

    async def get_command_config(
        self,
        handler_full_name: str,
    ) -> CommandConfig | None:
        async with store_session(self) as session:
            session: AsyncSession
            return await session.get(CommandConfig, handler_full_name)

    async def get_command_config_by_command_id(
        self,
        command_id: str,
    ) -> CommandConfig | None:
        async with store_session(self) as session:
            session: AsyncSession
            result = await session.execute(
                select(CommandConfig).where(CommandConfig.command_id == command_id),
            )
            return result.scalar_one_or_none()

    async def upsert_command_config(
        self,
        handler_full_name: str,
        plugin_name: str,
        module_path: str,
        original_command: str,
        *,
        command_id: str | None = None,
        previous_handler_full_name: str | None = None,
        resolved_command: str | None = None,
        enabled: bool | None = None,
        conflict_key: str | None = None,
        resolution_strategy: str | None = None,
        note: str | None = None,
        extra_data: dict | None = None,
        auto_managed: bool | None = None,
    ) -> CommandConfig:
        async def _op(session: AsyncSession) -> CommandConfig:
            config = await session.get(CommandConfig, handler_full_name)
            if (
                config is None
                and previous_handler_full_name
                and previous_handler_full_name != handler_full_name
            ):
                old = await session.get(CommandConfig, previous_handler_full_name)
                if old is not None:
                    await session.execute(
                        text(
                            "UPDATE command_configs SET handler_full_name = :new "
                            "WHERE handler_full_name = :old"
                        ),
                        {
                            "new": handler_full_name,
                            "old": previous_handler_full_name,
                        },
                    )
                    await session.flush()
                    session.expire_all()
                    config = await session.get(CommandConfig, handler_full_name)
            if not config:
                config = self._new_command_config(
                    handler_full_name,
                    plugin_name,
                    module_path,
                    original_command,
                    command_id=command_id,
                    resolved_command=resolved_command,
                    enabled=enabled,
                    conflict_key=conflict_key,
                    resolution_strategy=resolution_strategy,
                    note=note,
                    extra_data=extra_data,
                    auto_managed=auto_managed,
                )
                session.add(config)
            else:
                self._apply_updates(
                    config,
                    command_id=command_id,
                    plugin_name=plugin_name,
                    module_path=module_path,
                    original_command=original_command,
                    resolved_command=resolved_command,
                    enabled=enabled,
                    conflict_key=conflict_key,
                    resolution_strategy=resolution_strategy,
                    note=note,
                    extra_data=extra_data,
                    auto_managed=auto_managed,
                )
            await session.flush()
            await session.refresh(config)
            return config

        return await run_in_tx(self, _op)

    async def delete_command_config(self, handler_full_name: str) -> None:
        await self.delete_command_configs([handler_full_name])

    async def delete_command_configs(self, handler_full_names: list[str]) -> None:
        if not handler_full_names:
            return

        async def _op(session: AsyncSession) -> None:
            await session.execute(
                delete(CommandConfig).where(
                    col(CommandConfig.handler_full_name).in_(handler_full_names),
                ),
            )

        await run_in_tx(self, _op)

    async def list_command_conflicts(
        self,
        status: str | None = None,
        config_id: str | None = None,
    ) -> list[CommandConflict]:
        async with store_session(self) as session:
            session: AsyncSession
            query = select(CommandConflict)
            if status:
                query = query.where(CommandConflict.status == status)
            if config_id is not None:
                query = query.where(CommandConflict.config_id == config_id)
            result = await session.execute(query)
            return list(result.scalars().all())

    async def upsert_command_conflict(
        self,
        conflict_key: str,
        handler_full_name: str,
        plugin_name: str,
        *,
        config_id: str | None = None,
        command_id: str | None = None,
        status: str | None = None,
        resolution: str | None = None,
        resolved_command: str | None = None,
        note: str | None = None,
        extra_data: dict | None = None,
        auto_generated: bool | None = None,
    ) -> CommandConflict:
        async def _op(session: AsyncSession) -> CommandConflict:
            scope_id = config_id or ""
            resolved_id = command_id or ""
            result = await session.execute(
                select(CommandConflict).where(
                    CommandConflict.config_id == scope_id,
                    CommandConflict.conflict_key == conflict_key,
                    CommandConflict.command_id == resolved_id,
                ),
            )
            record = result.scalar_one_or_none()
            if record is None:
                result = await session.execute(
                    select(CommandConflict).where(
                        CommandConflict.conflict_key == conflict_key,
                        CommandConflict.handler_full_name == handler_full_name,
                    ),
                )
                record = result.scalar_one_or_none()
            if not record:
                record = self._new_command_conflict(
                    conflict_key,
                    handler_full_name,
                    plugin_name,
                    config_id=scope_id,
                    command_id=resolved_id,
                    status=status,
                    resolution=resolution,
                    resolved_command=resolved_command,
                    note=note,
                    extra_data=extra_data,
                    auto_generated=auto_generated,
                )
                session.add(record)
            else:
                self._apply_updates(
                    record,
                    config_id=scope_id,
                    command_id=resolved_id or None,
                    plugin_name=plugin_name,
                    handler_full_name=handler_full_name,
                    status=status,
                    resolution=resolution,
                    resolved_command=resolved_command,
                    note=note,
                    extra_data=extra_data,
                    auto_generated=auto_generated,
                )
            await session.flush()
            await session.refresh(record)
            return record

        return await run_in_tx(self, _op)

    async def delete_command_conflicts(self, ids: list[int]) -> None:
        if not ids:
            return

        async def _op(session: AsyncSession) -> None:
            await session.execute(
                delete(CommandConflict).where(col(CommandConflict.id).in_(ids)),
            )

        await run_in_tx(self, _op)
