from __future__ import annotations

import time
import traceback
from typing import TYPE_CHECKING

from astrbot.core import file_token_service, html_renderer, logger
from astrbot.core.message.components import Image, Plain
from astrbot.core.star.node_star import NodeResult, NodeStar

if TYPE_CHECKING:
    from astrbot.core.platform.astr_message_event import AstrMessageEvent


class T2IStar(NodeStar):
    """Text-to-image."""

    def __init__(self, context, config: dict | None = None):
        super().__init__(context, config)
        self.callback_api_base = None
        self.t2i_active_template = None

    async def process(self, event: AstrMessageEvent) -> NodeResult:
        config = self.context.get_config()
        self.t2i_active_template = config.get("t2i_active_template", "base")
        self.callback_api_base = config.get("callback_api_base", "")
        node_config = event.node_config or {}
        word_threshold = node_config.get("word_threshold", 150)
        strategy = node_config.get("strategy", "remote")
        active_template = node_config.get("active_template", "")
        use_file_service = node_config.get("use_file_service", False)

        result = event.get_result()
        if not result:
            return NodeResult.SKIP

        # 先收集流式内容（如果有）
        await self.collect_stream(event)

        if not result.chain:
            return NodeResult.SKIP

        # use_t2i_ 控制逻辑：
        # - False: 明确禁用，跳过
        # - True: 强制启用，跳过长度检查
        # - None: 根据文本长度自动判断
        if result.use_t2i_ is False:
            return NodeResult.SKIP

        parts = []
        for comp in result.chain:
            if isinstance(comp, Plain):
                parts.append("\n\n" + comp.text)
            else:
                break
        plain_str = "".join(parts)

        if not plain_str:
            return NodeResult.SKIP

        # 仅当 use_t2i_ 不是强制启用时，检查长度阈值
        if result.use_t2i_:
            try:
                threshold = max(int(word_threshold), 50)
            except Exception:
                threshold = 150

            if len(plain_str) <= threshold:
                return NodeResult.SKIP

        render_start = time.time()
        try:
            if not active_template:
                active_template = self.t2i_active_template
            url = await html_renderer.render_t2i(
                plain_str,
                return_url=True,
                use_network=strategy == "remote",
                template_name=active_template,
            )
        except Exception:
            logger.error(traceback.format_exc())
            logger.error("文本转图片失败，使用文本发送。")
            return NodeResult.SKIP

        if time.time() - render_start > 3:
            logger.warning("文本转图片耗时超过 3 秒。可以使用 /t2i 关闭。")

        if url:
            if url.startswith("http"):
                result.chain = [Image.fromURL(url)]
            elif use_file_service and self.callback_api_base:
                token = await file_token_service.register_file(url)
                url = f"{self.callback_api_base}/api/file/{token}"
                logger.debug(f"已注册：{url}")
                result.chain = [Image.fromURL(url)]
            else:
                result.chain = [Image.fromFileSystem(url)]

            event.set_node_output(result)
            return NodeResult.CONTINUE

        return NodeResult.SKIP
