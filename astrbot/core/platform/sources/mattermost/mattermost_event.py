import asyncio
import re
from collections.abc import AsyncGenerator

from astrbot import logger
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform import Group, MessageMember
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.send_result import PlatformSendResult

from .client import MattermostClient


class MattermostMessageEvent(AstrMessageEvent):
    _FALLBACK_SENTENCE_PATTERN = re.compile(r"[^。？！~…]+[。？！~…]+")

    def __init__(
        self,
        message_str,
        message_obj,
        platform_meta,
        session_id,
        client: MattermostClient,
    ) -> None:
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self._client = client
        for path in getattr(message_obj, "temporary_file_paths", []):
            self.track_temporary_local_file(path)

    async def send(self, message: MessageChain) -> PlatformSendResult | None:
        await self._client.send_message_chain(self.get_session_id(), message)
        return await super().send(message)

    async def send_streaming(
        self,
        generator: AsyncGenerator,
        use_fallback: bool = False,
    ):
        return await self.send_non_streaming_response(
            generator,
            use_fallback=use_fallback,
            sentence_pattern=self._FALLBACK_SENTENCE_PATTERN,
            sleep=asyncio.sleep,
            record_empty=True,
        )

    async def get_group(self, group_id=None, **kwargs):
        """Gets Mattermost channel information and all visible members.

        Args:
            group_id: Optional Mattermost channel identifier.
            **kwargs: Reserved compatibility arguments.

        Returns:
            Enriched channel information, or a basic group if lookup fails.
        """
        channel_id = group_id or self.get_group_id()
        if not channel_id:
            return None

        current_group = getattr(self.message_obj, "group", None)
        group = Group(
            group_id=channel_id,
            group_name=(
                current_group.group_name
                if current_group and current_group.group_id == channel_id
                else None
            ),
        )

        try:
            channel = await self._client.get_channel(channel_id)
            group.group_name = (
                channel.get("display_name") or channel.get("name") or group.group_name
            )
        except Exception as exc:
            logger.debug(
                "Mattermost channel lookup failed for %s: %s",
                channel_id,
                exc,
            )
            return group

        try:
            stats = await self._client.get_channel_stats(channel_id)
            group.member_count = stats.get("member_count")
        except Exception as exc:
            logger.debug(
                "Mattermost channel stats lookup failed for %s: %s",
                channel_id,
                exc,
            )

        memberships: list[dict] = []
        page = 0
        per_page = 200
        try:
            while True:
                membership_page = await self._client.get_channel_members(
                    channel_id,
                    page=page,
                    per_page=per_page,
                )
                memberships.extend(membership_page)
                if len(membership_page) < per_page:
                    break
                if group.member_count and len(memberships) >= group.member_count:
                    break
                page += 1
        except Exception as exc:
            logger.debug(
                "Mattermost channel member lookup failed for %s: %s",
                channel_id,
                exc,
            )
            return group

        unique_memberships: dict[str, dict] = {}
        for membership in memberships:
            user_id = str(membership.get("user_id") or "")
            if user_id:
                unique_memberships[user_id] = membership

        user_ids = list(unique_memberships)
        users_by_id: dict[str, dict] = {}
        for offset in range(0, len(user_ids), 100):
            user_id_batch = user_ids[offset : offset + 100]
            try:
                users = await self._client.get_users_by_ids(user_id_batch)
            except Exception as exc:
                logger.debug(
                    "Mattermost user batch lookup failed for %s: %s",
                    channel_id,
                    exc,
                )
                continue
            for user in users:
                user_id = str(user.get("id") or "")
                if user_id:
                    users_by_id[user_id] = user

        members: list[MessageMember] = []
        admins: list[str] = []
        for user_id, membership in unique_memberships.items():
            user = users_by_id.get(user_id, {})
            members.append(
                MessageMember(
                    user_id=user_id,
                    nickname=(user.get("nickname") or user.get("username") or user_id),
                ),
            )
            if (
                "channel_admin" in str(membership.get("roles") or "").split()
                or membership.get("scheme_admin") is True
            ):
                admins.append(user_id)

        group.members = members
        group.group_admins = admins
        group.member_count = group.member_count or len(members)
        return group
