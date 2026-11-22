"""Dedicated new-SDK plugin covering commands, filters, events, and components."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from astrbot_sdk import MessageEvent, Plugin, on
from astrbot_sdk.events import MessageType, SenderRole
from astrbot_sdk.message_components import (
    ActionRow,
    At,
    AtAll,
    Button,
    Face,
    File,
    Forward,
    Image,
    Json,
    Location,
    Music,
    Node,
    Nodes,
    Plain,
    Poke,
    Record,
    Reply,
    Share,
    Video,
)
from astrbot_sdk.messages import MessageChain, to_message_chain
from astrbot_sdk.results import Propagation, message_result


class SdkCommandsMessagesPlugin(Plugin):
    """Exercise @on.command, @on.message, @on.button_action, and segments."""

    def __init__(self, context: Any) -> None:
        super().__init__(context)
        self._last_props: dict[str, Any] = {}

    @on.command(
        "cm calc",
        aliases=("cm compute",),
        description="Typed calculator command with multi-platform and admin filters",
        message_types=(MessageType.PRIVATE,),
        platforms=("webchat", "telegram"),
        roles=(SenderRole.ADMIN,),
        priority=5,
    )
    async def cm_calc(
        self,
        event: MessageEvent,
        a: int,
        scale: float,
        round_up: bool = False,
        tag: str = "ok",
    ):
        """Exercise typed int/float/bool/str command argument parsing."""
        raw = a * scale
        val = int(raw) + (1 if round_up and raw > int(raw) else 0)
        self._last_props = {
            "id": event.id,
            "platform_type": event.platform_type,
            "message_ref": event.message_ref.id,
            "sender_id": event.sender.id,
            "sender_role": str(event.sender.role),
            "ts": event.timestamp.isoformat(),
            "cmd_path": event.command.path if event.command else None,
            "is_wake": event.is_wake,
            "extras_keys": sorted(event.extras.keys()),
            "text": event.text,
            "is_private": event.is_private,
            "is_group": event.is_group,
            "is_btn": event.is_button_interaction,
        }
        yield event.reply(
            f"calc:{val}:{tag}",
            quote=True,
            propagation=Propagation.STOP,
        )

    @on.command(
        "cm alias_top",
        aliases=("cm top space",),
        description="Multi-word alias",
    )
    async def cm_alias_top(self, event: MessageEvent):
        """Exercise multi-word command alias resolution."""
        yield event.reply("alias-top-ok")

    @on.command("cm grp", description="Group root command")
    async def cm_grp_root(self, event: MessageEvent):
        """Respond when bare group path is invoked."""
        yield event.reply("grp-root-ok")

    @on.command("cm grp leaf", description="Group leaf subcommand")
    async def cm_grp_leaf(self, event: MessageEvent):
        """Respond when group subcommand is invoked."""
        yield event.reply("grp-leaf-ok")

    @on.message(
        regex=re.compile(r"^#cm-hi$", re.IGNORECASE),
        platforms=("webchat", "telegram"),
        message_types=(MessageType.PRIVATE,),
        roles=(SenderRole.ADMIN,),
        priority=3,
    )
    async def on_regex_hi(self, event: MessageEvent):
        """Exercise @on.message regex with multi-platform OR filters and stop()."""
        yield message_result(
            to_message_chain(f"regex-hi:{event.text}"),
            quote=True,
            propagation=Propagation.STOP,
        )
        yield event.stop()

    @on.button_action("cm_btn")
    async def on_cm_button(self, event: MessageEvent):
        """Exercise @on.button_action and MessageEvent.button_interaction."""
        assert event.is_button_interaction is True
        inter = event.button_interaction
        assert inter is not None
        yield event.reply(json.dumps({"action": inter.action_id, "data": inter.data}))

    @on.command(
        "cm media_rich",
        description="Send every rich segment and media factory",
    )
    async def cm_media_rich(self, event: MessageEvent):
        """Exercise MessageChain helpers, all components, and MediaSegment factories."""
        tmp_dir = Path(self.ctx.storage.data_dir)
        os.makedirs(tmp_dir, exist_ok=True)
        img_file = tmp_dir / "local.png"
        rec_file = tmp_dir / "local.wav"
        vid_file = tmp_dir / "local.mp4"
        doc_file = tmp_dir / "local.txt"
        img_file.write_bytes(b"PNG-LOCAL")
        rec_file.write_bytes(b"WAV-LOCAL")
        vid_file.write_bytes(b"MP4-LOCAL")
        doc_file.write_text("TXT-LOCAL", encoding="utf-8")

        p1 = Plain("head")
        rich_chain = MessageChain(
            p1,
            Plain("tail"),
            At(user_id="u2", name="Ally"),
            AtAll(),
            Reply(id="r1", sender_id="u2", sender_name="Ally", text="ref"),
            Face(id=7),
            Forward(id="fwd-1"),
            Node(sender_id="u2", sender_name="Ally", content=[Plain("n1")]),
            Nodes([Node(sender_id="u2", content=[Plain("n2")])]),
            Poke(poke_type="126", user_id="u2"),
            Json(data={"card": 1}),
            Share(url="https://astrbot.app", title="AstrBot", content="home"),
            Location(lat=31.2, lon=121.5, title="SH", content="center"),
            Music(
                music_type="custom",
                url="https://astrbot.app/m",
                audio="https://astrbot.app/a.mp3",
                title="Song",
            ),
            ActionRow(
                [
                    Button.callback("Go", "cm_btn", data={"v": 1}, style="primary"),
                    Button.link("Site", "https://astrbot.app"),
                ]
            ),
        )
        assert rich_chain.text == "headtail"
        assert rich_chain.count(p1) == 1
        assert rich_chain.index(p1) == 0

        media_chain = MessageChain(
            Image.from_bytes(b"IMG-B", media_type="image/png"),
            Image.from_file(img_file),
            Image.from_url("https://astrbot.app/i.png"),
            Record.from_bytes(b"REC-B", media_type="audio/wav"),
            Record.from_file(rec_file),
            Record.from_url("https://astrbot.app/r.wav"),
            Video.from_bytes(b"VID-B", media_type="video/mp4"),
            Video.from_file(vid_file),
            Video.from_url("https://astrbot.app/v.mp4"),
            File.from_bytes(b"FILE-B", filename="b.bin"),
            File.from_file(doc_file, filename="doc.txt"),
            File.from_url("https://astrbot.app/f.txt", filename="u.txt"),
        )
        await self.ctx.messages.send(event.umo, rich_chain)
        await self.ctx.messages.send(event.umo, media_chain)
        yield event.reply(
            json.dumps(
                {
                    "ok": True,
                    "rich_count": len(rich_chain),
                    "media_count": len(media_chain),
                    "props": self._last_props,
                },
                sort_keys=True,
            )
        )
