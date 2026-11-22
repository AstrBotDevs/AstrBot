"""Dedicated new-SDK plugin covering Storage, Assets, FileToken, and Render."""

from __future__ import annotations

import json
import os
from pathlib import Path

from astrbot_sdk import MessageEvent, Plugin, on
from astrbot_sdk.assets import AssetRef
from astrbot_sdk.message_components import Image
from astrbot_sdk.messages import MessageChain
from astrbot_sdk.render import RenderOptions, TextRenderOptions
from astrbot_sdk.services import prepare_outbound_chain


class SdkStorageAssetsRenderPlugin(Plugin):
    """Exercise KV storage, data_dir, asset transfer, token, and render."""

    @on.command("sar run", description="Run storage, asset, token, and render suite")
    async def sar_run(self, event: MessageEvent):
        """Execute storage KV, asset roundtrip, download token, and HTML/T2I render."""
        await self.ctx.storage.set("sar_k", {"items": [1, 2]})
        got = await self.ctx.storage.get("sar_k")
        await self.ctx.storage.delete("sar_k")
        after_del = await self.ctx.storage.get("sar_k", "gone")

        local_dir = Path(self.ctx.storage.data_dir)
        os.makedirs(local_dir, exist_ok=True)
        local_file = local_dir / "sar_note.txt"
        local_file.write_text("sar-local", encoding="utf-8")

        raw_bytes = b"SAR-ASSET-BYTES"
        asset: AssetRef = await self.ctx.assets.upload(
            raw_bytes,
            filename="sar.bin",
            media_type="application/octet-stream",
        )
        dl_path = await self.ctx.assets.download(asset)
        try:
            asset_ok = dl_path.read_bytes() == raw_bytes
        finally:
            dl_path.unlink(missing_ok=True)

        token = await self.ctx.assets.issue_download_token(
            b"SAR-TOKEN-DATA",
            filename="sar_tok.txt",
            single_use=False,
        )

        prepared = await prepare_outbound_chain(
            MessageChain(Image.from_bytes(b"SAR-PREP", media_type="image/png")),
            self.ctx.assets,
        )
        prepared_ok = isinstance(prepared[0], Image) and isinstance(
            prepared[0].source, AssetRef
        )

        html_ref = await self.ctx.render.html(
            "<p>{{ msg }}</p>",
            {"msg": "sar-html"},
            options=RenderOptions(width=640, extra={"deviceScaleFactor": 2}),
        )
        text_ref = await self.ctx.render.text(
            "sar-t2i",
            options=TextRenderOptions(template_name="default"),
        )
        html_file = await self.ctx.assets.download(html_ref)
        text_file = await self.ctx.assets.download(text_ref)
        try:
            render_ok = (
                len(html_file.read_bytes()) > 0 and len(text_file.read_bytes()) > 0
            )
        finally:
            html_file.unlink(missing_ok=True)
            text_file.unlink(missing_ok=True)

        await self.ctx.messages.send(event.umo, prepared)
        yield event.reply(
            json.dumps(
                {
                    "kv_ok": got == {"items": [1, 2]} and after_del == "gone",
                    "local_ok": local_file.read_text(encoding="utf-8") == "sar-local",
                    "asset_ok": asset_ok and isinstance(asset, AssetRef),
                    "token": token,
                    "prepared_ok": prepared_ok,
                    "render_ok": render_ok,
                },
                sort_keys=True,
            )
        )
