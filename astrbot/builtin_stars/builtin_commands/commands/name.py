from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.core.umo_alias import get_event_auto_name, normalize_umo_name

from .utils.i18n import t


class NameCommand:
    def __init__(self, context: star.Context) -> None:
        self.context = context

    async def name(self, event: AstrMessageEvent, alias: str) -> None:
        umo = event.unified_msg_origin
        auto_name = get_event_auto_name(event)
        alias = normalize_umo_name(alias)
        if not alias:
            saved_alias = await self.context.get_db().get_umo_alias(umo)
            user_alias = normalize_umo_name(
                saved_alias.user_alias if saved_alias else ""
            )
            event.set_result(
                MessageEventResult()
                .message(
                    await t(
                        self.context,
                        umo,
                        "name.usage",
                        umo=umo,
                        name=auto_name or "(empty)",
                        alias=user_alias or "(empty)",
                    ),
                )
                .use_t2i(False)
            )
            return

        sender_id = str(event.get_sender_id() or "")

        await self.context.get_db().upsert_umo_alias(
            umo=umo,
            creator_sender_id=sender_id,
            auto_name=auto_name,
            user_alias=alias,
        )

        event.set_result(
            MessageEventResult()
            .message(await t(self.context, umo, "name.set", alias=alias, umo=umo))
            .use_t2i(False)
        )
