"""Speech-to-text command."""

from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.core.pipeline.engine.chain_runtime_flags import (
    FEATURE_STT,
    toggle_chain_runtime_flag,
)

from ._node_binding import get_chain_nodes


class STTCommand:
    """Toggle speech-to-text for the current routed chain."""

    def __init__(self, context: star.Context):
        self.context = context

    async def stt(self, event: AstrMessageEvent):
        chain_config = event.chain_config
        if not chain_config:
            event.set_result(MessageEventResult().message("未找到已路由的 Chain。"))
            return

        nodes = get_chain_nodes(event, "stt")
        if not nodes:
            event.set_result(
                MessageEventResult().message("当前 Chain 中没有 STT 节点。")
            )
            return

        enabled = await toggle_chain_runtime_flag(chain_config.chain_id, FEATURE_STT)
        status = "开启" if enabled else "关闭"
        event.set_result(
            MessageEventResult().message(
                f"Chain `{chain_config.chain_id}` 的 STT 功能已{status}（共 {len(nodes)} 个节点）。"
            )
        )
