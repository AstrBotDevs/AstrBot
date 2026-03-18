"""SDK-local rich message result objects.

本模块定义消息事件的结果对象，用于构建和返回富文本/多媒体消息。

核心类：
- MessageChain: 消息组件列表，支持同步/异步序列化为协议 payload
- MessageEventResult: 事件处理结果，包含类型标记和消息链
- EventResultType: 结果类型枚举（EMPTY / CHAIN）

辅助函数：
- coerce_message_chain: 将多种输入格式统一转换为 MessageChain，
  支持 MessageEventResult、MessageChain、单个组件或组件列表
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .message_components import (
    At,
    AtAll,
    BaseMessageComponent,
    File,
    Plain,
    Reply,
    build_media_component_from_url,
    component_to_payload,
    component_to_payload_sync,
    is_message_component,
    payloads_to_components,
)


class EventResultType(str, Enum):
    EMPTY = "empty"
    CHAIN = "chain"


@dataclass(slots=True)
class MessageChain:
    components: list[BaseMessageComponent] = field(default_factory=list)

    def append(self, component: BaseMessageComponent) -> MessageChain:
        self.components.append(component)
        return self

    def extend(self, components: list[BaseMessageComponent]) -> MessageChain:
        self.components.extend(components)
        return self

    def __iter__(self):
        return iter(self.components)

    def __len__(self) -> int:
        return len(self.components)

    def to_payload(self) -> list[dict[str, Any]]:
        return [component_to_payload_sync(component) for component in self.components]

    async def to_payload_async(self) -> list[dict[str, Any]]:
        return [await component_to_payload(component) for component in self.components]

    def get_plain_text(self, with_other_comps_mark: bool = False) -> str:
        texts: list[str] = []
        for component in self.components:
            if isinstance(component, Plain):
                texts.append(component.text)
            elif with_other_comps_mark:
                texts.append(f"[{component.__class__.__name__}]")
        return " ".join(texts)

    def plain_text(self, with_other_comps_mark: bool = False) -> str:
        return self.get_plain_text(with_other_comps_mark=with_other_comps_mark)


@dataclass(slots=True)
class MessageEventResult:
    type: EventResultType = EventResultType.EMPTY
    chain: MessageChain = field(default_factory=MessageChain)

    def to_payload(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "chain": self.chain.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> MessageEventResult:
        result_type_raw = str(payload.get("type", EventResultType.EMPTY.value))
        try:
            result_type = EventResultType(result_type_raw)
        except ValueError:
            result_type = EventResultType.EMPTY
        chain_payload = payload.get("chain")
        components = (
            payloads_to_components(chain_payload)
            if isinstance(chain_payload, list)
            else []
        )
        return cls(type=result_type, chain=MessageChain(components))


@dataclass(slots=True)
class MessageBuilder:
    components: list[BaseMessageComponent] = field(default_factory=list)

    def text(self, content: str) -> MessageBuilder:
        self.components.append(Plain(content, convert=False))
        return self

    def at(self, user_id: str) -> MessageBuilder:
        self.components.append(At(user_id))
        return self

    def at_all(self) -> MessageBuilder:
        self.components.append(AtAll())
        return self

    def image(self, url: str) -> MessageBuilder:
        self.components.append(build_media_component_from_url(url, kind="image"))
        return self

    def record(self, url: str) -> MessageBuilder:
        self.components.append(build_media_component_from_url(url, kind="record"))
        return self

    def video(self, url: str) -> MessageBuilder:
        self.components.append(build_media_component_from_url(url, kind="video"))
        return self

    def file(self, name: str, *, file: str = "", url: str = "") -> MessageBuilder:
        self.components.append(File(name=name, file=file, url=url))
        return self

    def reply(self, **kwargs: Any) -> MessageBuilder:
        self.components.append(Reply(**kwargs))
        return self

    def append(self, component: BaseMessageComponent) -> MessageBuilder:
        self.components.append(component)
        return self

    def extend(self, components: list[BaseMessageComponent]) -> MessageBuilder:
        self.components.extend(components)
        return self

    def build(self) -> MessageChain:
        return MessageChain(list(self.components))


def coerce_message_chain(value: Any) -> MessageChain | None:
    if isinstance(value, MessageEventResult):
        return value.chain
    if isinstance(value, MessageChain):
        return value
    if is_message_component(value):
        return MessageChain([value])
    if isinstance(value, (list, tuple)) and all(
        is_message_component(item) for item in value
    ):
        return MessageChain(list(value))
    return None


__all__ = [
    "EventResultType",
    "MessageChain",
    "MessageBuilder",
    "MessageEventResult",
    "coerce_message_chain",
]
