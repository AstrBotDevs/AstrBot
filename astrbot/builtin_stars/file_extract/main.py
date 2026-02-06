"""文件提取节点 - 将消息中的 File 组件转换为文本"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from astrbot.core import logger
from astrbot.core.message.components import File, Plain, Reply
from astrbot.core.star.node_star import NodeResult, NodeStar

if TYPE_CHECKING:
    from astrbot.core.platform.astr_message_event import AstrMessageEvent


class FileExtractNode(NodeStar):
    """文件提取节点

    用户可手动添加到 Chain 中，在 Agent 节点之前运行。
    负责：
    1. 提取消息中 File 组件的文本内容
    2. 将 File 替换为 Plain（提取的文本）
    3. 后续节点无需感知文件提取，只看到纯文本

    支持两种提取模式（通过 provider 配置）：
    - local: 使用本地解析器（无需 API，支持 pdf/docx/xlsx/md/txt）
    - moonshotai: 使用 Moonshot AI API
    """

    async def process(self, event: AstrMessageEvent) -> NodeResult:
        node_config = event.node_config or {}
        provider = node_config.get("provider", "moonshotai")
        moonshotai_api_key = node_config.get("moonshotai_api_key", "")

        message = event.message_obj.message
        replaced = await self._replace_files(message, provider, moonshotai_api_key)

        # 处理引用消息中的文件
        for comp in message:
            if isinstance(comp, Reply) and comp.chain:
                replaced += await self._replace_files(
                    comp.chain, provider, moonshotai_api_key
                )

        if replaced:
            # 重建 message_str
            parts = []
            for comp in message:
                if isinstance(comp, Plain):
                    parts.append(comp.text)
            event.message_str = "".join(parts)
            event.message_obj.message_str = event.message_str
            logger.debug(f"File extraction: replaced {replaced} File component(s)")

            # Write output to ctx for downstream nodes
            event.set_node_output(event.message_str)

            return NodeResult.CONTINUE

        return NodeResult.SKIP

    async def _replace_files(
        self, components: list, provider: str, moonshotai_api_key: str
    ) -> int:
        """遍历组件列表，将 File 替换为 Plain，返回替换数量"""
        replaced = 0
        for idx, comp in enumerate(components):
            if not isinstance(comp, File):
                continue
            try:
                file_path = await comp.get_file()
                file_name = comp.name or os.path.basename(file_path)
                content = await self._extract_content(
                    file_path, provider, moonshotai_api_key
                )
                if content:
                    components[idx] = Plain(f"[File: {file_name}]\n{content}\n[/File]")
                    replaced += 1
            except Exception as e:
                logger.warning(f"Failed to extract file {comp.name}: {e}")
        return replaced

    async def _extract_content(
        self, file_path: str, provider: str, moonshotai_api_key: str
    ) -> str | None:
        """提取单个文件的文本内容"""
        if provider == "local":
            return await self._extract_local(file_path)
        elif provider == "moonshotai":
            return await self._extract_moonshotai(file_path, moonshotai_api_key)
        else:
            logger.error(f"Unsupported file extract provider: {provider}")
            return None

    async def _extract_local(self, file_path: str) -> str | None:
        """使用本地解析器提取文件内容"""
        ext = os.path.splitext(file_path)[1].lower()

        try:
            parser = await self._select_parser(ext)
        except ValueError as e:
            logger.warning(f"Local parser not available for {ext}: {e}")
            return None

        try:
            with open(file_path, "rb") as f:
                file_content = f.read()
            result = await parser.parse(file_content, os.path.basename(file_path))
            return result.text
        except Exception as e:
            logger.warning(f"Local parsing failed for {file_path}: {e}")
            return None

    @staticmethod
    async def _select_parser(ext: str):
        """根据文件扩展名选择解析器"""
        if ext == ".pdf":
            from astrbot.core.knowledge_base.parsers.pdf_parser import PDFParser

            return PDFParser()
        else:
            from astrbot.core.knowledge_base.parsers.markitdown_parser import (
                MarkitdownParser,
            )

            return MarkitdownParser()

    @staticmethod
    async def _extract_moonshotai(
        file_path: str, moonshotai_api_key: str
    ) -> str | None:
        """使用 Moonshot AI API 提取文件内容"""
        from astrbot.core.utils.file_extract import extract_file_moonshotai

        if not moonshotai_api_key:
            logger.error("Moonshot AI API key for file extract is not set")
            return None
        try:
            return await extract_file_moonshotai(file_path, moonshotai_api_key)
        except Exception as e:
            logger.warning(f"Moonshot AI extraction failed: {e}")
            return None
