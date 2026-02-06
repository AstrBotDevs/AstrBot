"""NodeStar — 可注册到 Pipeline Chain 的 Star

NodeStar 是 Star 的子类，具有以下特性：
1. 继承 Star 的所有能力（通过 self.context 访问系统服务）
2. 可注册到 Pipeline Chain 中作为处理节点
3. 支持多链多配置（通过 event.chain_config）

使用方式：
```python
class MyNode(NodeStar):
    async def process(self, event) -> NodeResult:
        # 通过 self.context 访问系统服务
        provider = self.get_chat_provider(event)
        # 处理逻辑...
        return NodeResult.CONTINUE
```

注意：node_name 从 metadata.yaml 的 name 字段获取，不可通过类属性定义。
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any

from astrbot.core import logger

from .star_base import Star

if TYPE_CHECKING:
    from astrbot.core.platform.astr_message_event import AstrMessageEvent
    from astrbot.core.provider.provider import Provider, STTProvider, TTSProvider


class NodeResult(Enum):
    """Node 执行结果，控制 Pipeline 流程"""

    CONTINUE = "continue"
    """继续执行下一个 Node"""
    STOP = "stop"
    """停止链路处理"""
    WAIT = "wait"
    """暂停链路，等待下一条消息再从当前Node恢复"""
    SKIP = "skip"
    """跳过当前 Node（条件不满足时使用）"""


class NodeStar(Star):
    """可注册到 Pipeline Chain 的 Star

    通过 event.chain_config 支持多链多配置。
    """

    def __init__(self, context, config: dict | None = None):
        super().__init__(context, config)
        self.initialized_chain_ids: set[str] = set()

    async def node_initialize(self) -> None:
        """节点初始化

        在节点首次处理消息前调用（按 chain_id 懒初始化）。
        可通过 self.context 访问系统服务。
        """
        pass

    async def process(
        self,
        event: AstrMessageEvent,
    ) -> NodeResult:
        """处理消息

        Args:
            event: 消息事件

        Returns:
            NodeResult: 流程控制语义

        Note:
            - 通过 self.context 访问系统服务（Provider、DB、Platform 等）
            - 通过 event.chain_config 获取链级别配置
            - 通过 event.node_config 获取节点配置
            - 通过 event.get_extra()/set_extra() 进行节点间通信
        """
        raise NotImplementedError

    def set_node_output(self, event: AstrMessageEvent, output: Any) -> None:
        """Unified node output API for chaining and sending."""
        event.set_node_output(output)

    async def get_node_input(
        self,
        event: AstrMessageEvent,
        *,
        strategy: str = "last",
        names: str | list[str] | None = None,
    ) -> Any:
        """Get upstream node output with optional merge strategy."""
        return await event.get_node_input(strategy=strategy, names=names)

    # -------------------- Chain-aware Provider 便捷方法 -------------------- #

    def get_chat_provider(self, event: AstrMessageEvent) -> Provider | None:
        """获取聊天 Provider（优先使用链配置的 provider_id）"""
        selected_provider = event.get_extra("selected_provider")
        if isinstance(selected_provider, str) and selected_provider:
            prov = self.context.get_provider_by_id(selected_provider)
            if isinstance(prov, Provider):
                return prov
            if prov is not None:
                logger.warning(
                    "selected_provider is not a chat provider: %s",
                    selected_provider,
                )

        chain_config = event.chain_config
        if chain_config and chain_config.chat_provider_id:
            prov = self.context.get_provider_by_id(chain_config.chat_provider_id)
            if isinstance(prov, Provider):
                return prov
            if prov is not None:
                logger.warning(
                    "chain chat_provider_id is not a chat provider: %s",
                    chain_config.chat_provider_id,
                )

        return self.context.get_using_provider(umo=event.unified_msg_origin)

    def get_tts_provider(self, event: AstrMessageEvent) -> TTSProvider | None:
        """获取 TTS Provider（优先使用链配置的 provider_id）"""
        chain_config = event.chain_config
        if chain_config and chain_config.tts_provider_id:
            prov = self.context.get_provider_by_id(chain_config.tts_provider_id)
            if prov:
                return prov  # type: ignore

        return self.context.get_using_tts_provider(umo=event.unified_msg_origin)

    def get_stt_provider(self, event: AstrMessageEvent) -> STTProvider | None:
        """获取 STT Provider（优先使用链配置的 provider_id）"""
        chain_config = event.chain_config
        if chain_config and chain_config.stt_provider_id:
            prov = self.context.get_provider_by_id(chain_config.stt_provider_id)
            if prov:
                return prov  # type: ignore

        return self.context.get_using_stt_provider(umo=event.unified_msg_origin)

    # -------------------- 流式消息处理 -------------------- #

    @staticmethod
    async def collect_stream(event: AstrMessageEvent) -> str | None:
        """将流式结果收集为完整文本

        对于不兼容流式的节点（如 TTS、T2I），可在 process 开头调用此方法。

        Returns:
            收集到的完整文本，如果没有流式结果则返回 None
        """
        from astrbot.core.message.components import Plain
        from astrbot.core.message.message_event_result import (
            ResultContentType,
            collect_streaming_result,
        )

        result = event.get_result()
        if not result:
            return None

        if result.result_content_type != ResultContentType.STREAMING_RESULT:
            return None

        if result.async_stream is None:
            return None

        await collect_streaming_result(result)

        # Reconstruct text from collected chain
        parts: list[str] = [
            comp.text for comp in result.chain if isinstance(comp, Plain)
        ]
        collected_text = "".join(parts)
        return collected_text
