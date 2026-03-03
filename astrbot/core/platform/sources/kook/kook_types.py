import json
from dataclasses import field
from enum import IntEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.dataclasses import dataclass


class KookApiPaths:
    """Kook Api 路径"""

    BASE_URL = "https://www.kookapp.cn"
    API_VERSION_PATH = "/api/v3"

    # 初始化相关
    USER_ME = f"{BASE_URL}{API_VERSION_PATH}/user/me"
    GATEWAY_INDEX = f"{BASE_URL}{API_VERSION_PATH}/gateway/index"

    # 消息相关
    ASSET_CREATE = f"{BASE_URL}{API_VERSION_PATH}/asset/create"
    ## 频道消息
    CHANNEL_MESSAGE_CREATE = f"{BASE_URL}{API_VERSION_PATH}/message/create"
    ## 私聊消息
    DIRECT_MESSAGE_CREATE = f"{BASE_URL}{API_VERSION_PATH}/direct-message/create"


# 定义参见kook事件结构文档: https://developer.kookapp.cn/doc/event/event-introduction
class KookMessageType(IntEnum):
    TEXT = 1
    IMAGE = 2
    VIDEO = 3
    FILE = 4
    AUDIO = 8
    KMARKDOWN = 9
    CARD = 10
    SYSTEM = 255


ThemeType = Literal[
    "primary", "success", "danger", "warning", "info", "secondary", "none", "invisible"
]
"""主题，可选的值为：primary, success, danger, warning, info, secondary, none.默认为 primary，为 none 时不显示侧边框。"""
SizeType = Literal["xs", "sm", "md", "lg"]
"""大小，可选值为：xs, sm, md, lg, 一般默认为 lg"""

SectionMode = Literal["left", "right"]
CountdownMode = Literal["day", "hour", "second"]


class KookCardColor(str):
    """16 进制色值"""


class KookCardModelBase:
    """卡片模块基类"""

    type: str


@dataclass
class PlainTextElement(KookCardModelBase):
    content: str
    type: str = "plain-text"
    emoji: bool = True


@dataclass
class KmarkdownElement(KookCardModelBase):
    content: str
    type: str = "kmarkdown"


@dataclass
class ImageElement(KookCardModelBase):
    src: str
    type: str = "image"
    alt: str = ""
    size: SizeType = "lg"
    circle: bool = False
    fallbackUrl: str | None = None


@dataclass
class ButtonElement(KookCardModelBase):
    text: str
    type: str = "button"
    theme: ThemeType = "primary"
    value: str = ""
    """当为 link 时，会跳转到 value 代表的链接;
当为 return-val 时，系统会通过系统消息将消息 id,点击用户 id 和 value 发回给发送者，发送者可以根据自己的需求进行处理,消息事件参见button 点击事件。私聊和频道内均可使用按钮点击事件。"""
    click: Literal["", "link", "return-val"] = ""
    """click 代表用户点击的事件,默认为""，代表无任何事件。"""


AnyElement = PlainTextElement | KmarkdownElement | ImageElement | ButtonElement | str


@dataclass
class ParagraphStructure(KookCardModelBase):
    fields: list[PlainTextElement | KmarkdownElement]
    type: str = "paragraph"
    cols: int = 1
    """范围是 1-3 , 移动端忽略此参数"""


@dataclass
class HeaderModule(KookCardModelBase):
    text: PlainTextElement
    type: str = "header"


@dataclass
class SectionModule(KookCardModelBase):
    text: PlainTextElement | KmarkdownElement | ParagraphStructure
    type: str = "section"
    mode: SectionMode = "left"
    accessory: ImageElement | ButtonElement | None = None


@dataclass
class ImageGroupModule(KookCardModelBase):
    """1 到多张图片的组合"""

    elements: list[ImageElement]
    type: str = "image-group"


@dataclass
class ContainerModule(KookCardModelBase):
    """1 到多张图片的组合，与图片组模块(ImageGroupModule)不同，图片并不会裁切为正方形。多张图片会纵向排列。"""

    elements: list[ImageElement]
    type: str = "container"


@dataclass
class ActionGroupModule(KookCardModelBase):
    elements: list[ButtonElement]
    type: str = "action-group"


@dataclass
class ContextModule(KookCardModelBase):
    elements: list[PlainTextElement | KmarkdownElement | ImageElement]
    """最多包含10个元素"""
    type: str = "context"


@dataclass
class DividerModule(KookCardModelBase):
    type: str = "divider"


@dataclass
class FileModule(KookCardModelBase):
    src: str
    title: str = ""
    type: Literal["file", "audio", "video"] = "file"
    cover: str | None = None
    """cover 仅音频有效, 是音频的封面图"""


@dataclass
class CountdownModule(KookCardModelBase):
    """startTime 和 endTime 为毫秒时间戳，startTime 和 endTime 不能小于服务器当前时间戳。"""

    endTime: int
    """毫秒时间戳"""
    type: str = "countdown"
    startTime: int | None = None
    """毫秒时间戳, 仅当mode为second才有这个字段"""
    mode: CountdownMode = "day"
    """mode 主要是倒计时的样式"""


@dataclass
class InviteModule(KookCardModelBase):
    code: str
    """邀请链接或者邀请码"""
    type: str = "invite"


# 所有模块的联合类型
AnyModule = (
    HeaderModule
    | SectionModule
    | ImageGroupModule
    | ContainerModule
    | ActionGroupModule
    | ContextModule
    | DividerModule
    | FileModule
    | CountdownModule
    | InviteModule
)


class KookCardMessage(BaseModel):
    """卡片定义文档详见 : https://developer.kookapp.cn/doc/cardmessage
    此类型不能直接to_json后发送,因为kook要求卡片容器json顶层必须是**列表**
    若要发送卡片消息，请使用KookCardMessageContainer
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)
    type: str = "card"
    theme: ThemeType | None = None
    size: SizeType | None = None
    color: KookCardColor | None = None
    modules: list[AnyModule] = field(default_factory=list)
    """单个 card 模块数量不限制，但是一条消息中所有卡片的模块数量之和最多是 50"""

    def add_module(self, module: AnyModule):
        self.modules.append(module)

    def to_dict(self, exclude_none: bool = True):
        """exclude_none：去掉值为 None 字段，保留结构"""
        return self.model_dump(exclude_none=exclude_none)

    def to_json(self, indent: int | None = None, ensure_ascii: bool = True):
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=ensure_ascii)


class KookCardMessageContainer(list[KookCardMessage]):
    """卡片消息容器(列表),此类型可以直接to_json后发送出去"""

    def append(self, object: KookCardMessage) -> None:
        return super().append(object)

    def to_json(self, indent: int | None = None, ensure_ascii: bool = True) -> str:
        return json.dumps(
            [i.to_dict() for i in self], indent=indent, ensure_ascii=ensure_ascii
        )


@dataclass
class OrderMessage:
    index: int
    text: str
    type: KookMessageType
    reply_id: str | int = ""
