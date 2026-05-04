import json
from enum import Enum, IntEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class KookApiPaths:
    """Kook Api 路径"""

    BASE_URL = "https://www.kookapp.cn"
    API_VERSION_PATH = "/api/v3"

    # 初始化相关
    USER_ME = f"{BASE_URL}{API_VERSION_PATH}/user/me"
    USER_VIEW = f"{BASE_URL}{API_VERSION_PATH}/user/view"
    GATEWAY_INDEX = f"{BASE_URL}{API_VERSION_PATH}/gateway/index"

    # 消息相关
    ASSET_CREATE = f"{BASE_URL}{API_VERSION_PATH}/asset/create"
    ## 频道消息
    CHANNEL_MESSAGE_CREATE = f"{BASE_URL}{API_VERSION_PATH}/message/create"
    ## 私聊消息
    DIRECT_MESSAGE_CREATE = f"{BASE_URL}{API_VERSION_PATH}/direct-message/create"


class KookMentionTagName(str, Enum):
    """用来匹配 `(tagName)value(tagName)` 格式里的tagName , 例如: `(met)all(met)`
    定义参见KMarkdown语法文档: https://developer.kookapp.cn/doc/kmarkdown"""

    MENTION = "met"
    ROLE = "rol"


class KookMessageType(IntEnum):
    """定义参见kook事件结构文档: https://developer.kookapp.cn/doc/event/event-introduction"""

    TEXT = 1
    IMAGE = 2
    VIDEO = 3
    FILE = 4
    AUDIO = 8
    KMARKDOWN = 9
    CARD = 10
    SYSTEM = 255


class KookModuleType(str, Enum):
    PLAIN_TEXT = "plain-text"
    KMARKDOWN = "kmarkdown"
    IMAGE = "image"
    BUTTON = "button"
    HEADER = "header"
    SECTION = "section"
    IMAGE_GROUP = "image-group"
    CONTAINER = "container"
    ACTION_GROUP = "action-group"
    CONTEXT = "context"
    DIVIDER = "divider"
    FILE = "file"
    AUDIO = "audio"
    VIDEO = "video"
    COUNTDOWN = "countdown"
    INVITE = "invite"
    CARD = "card"


class KookRoleExtraType(str, Enum):
    """定义参见kook事件结构文档: https://developer.kookapp.cn/doc/event/event-introduction"""

    ADDED_ROLE = "added_role"
    DELETED_ROLE = "deleted_role"
    UPDATED_ROLE = "updated_role"


ThemeType = Literal[
    "primary", "success", "danger", "warning", "info", "secondary", "none", "invisible"
]
"""主题，可选的值为：primary, success, danger, warning, info, secondary, none.默认为 primary，为 none 时不显示侧边框。"""
SizeType = Literal["xs", "sm", "md", "lg"]
"""大小，可选值为：xs, sm, md, lg, 一般默认为 lg"""

SectionMode = Literal["left", "right"]
CountdownMode = Literal["day", "hour", "second"]


class KookBaseReceiveDataClass(BaseModel):
    """接收数据基类,`to_dict`/`to_json`默认保证尽量json原样输出"""

    model_config = ConfigDict(
        extra="allow",
        arbitrary_types_allowed=True,
        populate_by_name=True,
    )

    @classmethod
    def from_dict(cls, raw_data: dict):
        return cls.model_validate(raw_data)

    @classmethod
    def from_json(cls, raw_data: str | bytes | bytearray):
        return cls.model_validate_json(raw_data)

    def to_dict(
        self,
        mode: Literal["json", "python"] | str = "json",
        by_alias=True,
        exclude_none=False,
        exclude_unset=True,
    ) -> dict:
        """默认配置预期场景为尽量原样输出,若需要使用此数据类发送json数据,
        请`exclude_none=True, exclude_unset=False`"""
        return self.model_dump(
            by_alias=by_alias,
            exclude_none=exclude_none,
            mode=mode,
            exclude_unset=exclude_unset,
        )

    def to_json(
        self,
        indent: int | None = None,
        ensure_ascii=False,
        by_alias=True,
        exclude_none=False,
        exclude_unset=True,
    ) -> str:
        """默认配置预期场景为尽量原样输出,若需要使用此数据类发送json数据,
        请`exclude_none=True, exclude_unset=False`"""
        return self.model_dump_json(
            indent=indent,
            ensure_ascii=ensure_ascii,
            by_alias=by_alias,
            exclude_none=exclude_none,
            exclude_unset=exclude_unset,
        )


class KookBaseSendDataClass(KookBaseReceiveDataClass):
    """发送数据基类,`to_dict`/`to_json`保证默认输出内容格式包含接口格式所需最简格式内容"""

    def to_dict(
        self,
        mode: Literal["json", "python"] | str = "json",
        by_alias=True,
        exclude_none=True,
        exclude_unset=False,
    ) -> dict:
        """默认配置预期场景为发送数据,若需要使用此数据类接收数据并尽量原样json输出,
        请`exclude_none=False, exclude_unset=True`"""
        return self.model_dump(
            by_alias=by_alias,
            exclude_none=exclude_none,
            mode=mode,
            exclude_unset=exclude_unset,
        )

    def to_json(
        self,
        indent: int | None = None,
        ensure_ascii=False,
        by_alias=True,
        exclude_none=True,
        exclude_unset=False,
    ) -> str:
        """默认配置预期场景为发送数据,若需要使用此数据类接收数据并尽量原样json输出,
        请`exclude_none=False, exclude_unset=True`"""
        return self.model_dump_json(
            indent=indent,
            ensure_ascii=ensure_ascii,
            by_alias=by_alias,
            exclude_none=exclude_none,
            exclude_unset=exclude_unset,
        )


class KookCardModelBase(KookBaseSendDataClass):
    """卡片模块基类"""

    type: str


class PlainTextElement(KookCardModelBase):
    content: str
    type: Literal[KookModuleType.PLAIN_TEXT] = KookModuleType.PLAIN_TEXT
    emoji: bool = True


class KmarkdownElement(KookCardModelBase):
    content: str
    type: Literal[KookModuleType.KMARKDOWN] = KookModuleType.KMARKDOWN


class ImageElement(KookCardModelBase):
    src: str
    type: Literal[KookModuleType.IMAGE] = KookModuleType.IMAGE
    alt: str = ""
    size: SizeType = "lg"
    circle: bool = False
    fallbackUrl: str | None = None


class ButtonElement(KookCardModelBase):
    text: str
    type: Literal[KookModuleType.BUTTON] = KookModuleType.BUTTON
    theme: ThemeType = "primary"
    value: str = ""
    """当为 link 时，会跳转到 value 代表的链接;
当为 return-val 时，系统会通过系统消息将消息 id,点击用户 id 和 value 发回给发送者，发送者可以根据自己的需求进行处理,消息事件参见button 点击事件。私聊和频道内均可使用按钮点击事件。"""
    click: Literal["", "link", "return-val"] = ""
    """click 代表用户点击的事件,默认为""，代表无任何事件。"""


AnyElement = PlainTextElement | KmarkdownElement | ImageElement | ButtonElement | str


class ParagraphStructure(KookCardModelBase):
    fields: list[PlainTextElement | KmarkdownElement]
    type: Literal["paragraph"] = "paragraph"
    cols: int = 1
    """范围是 1-3 , 移动端忽略此参数"""


class HeaderModule(KookCardModelBase):
    text: PlainTextElement
    type: Literal[KookModuleType.HEADER] = KookModuleType.HEADER


class SectionModule(KookCardModelBase):
    text: PlainTextElement | KmarkdownElement | ParagraphStructure
    type: Literal[KookModuleType.SECTION] = KookModuleType.SECTION
    mode: SectionMode = "left"
    accessory: ImageElement | ButtonElement | None = None


class ImageGroupModule(KookCardModelBase):
    """1 到多张图片的组合"""

    elements: list[ImageElement]
    type: Literal[KookModuleType.IMAGE_GROUP] = KookModuleType.IMAGE_GROUP


class ContainerModule(KookCardModelBase):
    """1 到多张图片的组合，与图片组模块(ImageGroupModule)不同，图片并不会裁切为正方形。多张图片会纵向排列。"""

    elements: list[ImageElement]
    type: Literal[KookModuleType.CONTAINER] = KookModuleType.CONTAINER


class ActionGroupModule(KookCardModelBase):
    """用来放按钮的模块"""

    elements: list[ButtonElement]
    type: Literal[KookModuleType.ACTION_GROUP] = KookModuleType.ACTION_GROUP


class ContextModule(KookCardModelBase):
    elements: list[PlainTextElement | KmarkdownElement | ImageElement]
    """最多包含10个元素"""
    type: Literal[KookModuleType.CONTEXT] = KookModuleType.CONTEXT


class DividerModule(KookCardModelBase):
    """展示分割线用的"""

    type: Literal[KookModuleType.DIVIDER] = KookModuleType.DIVIDER


class FileModule(KookCardModelBase):
    src: str
    title: str = ""
    type: Literal[KookModuleType.FILE, KookModuleType.AUDIO, KookModuleType.VIDEO] = (
        KookModuleType.FILE
    )
    cover: str | None = None
    """cover 仅音频有效, 是音频的封面图"""


class CountdownModule(KookCardModelBase):
    """startTime 和 endTime 为毫秒时间戳，startTime 和 endTime 不能小于服务器当前时间戳。"""

    endTime: int
    """毫秒时间戳"""
    type: Literal[KookModuleType.COUNTDOWN] = KookModuleType.COUNTDOWN
    startTime: int | None = None
    """毫秒时间戳, 仅当mode为second才有这个字段"""
    mode: CountdownMode = "day"
    """mode 主要是倒计时的样式"""


class InviteModule(KookCardModelBase):
    code: str
    """邀请链接或者邀请码"""
    type: Literal[KookModuleType.INVITE] = KookModuleType.INVITE


# 所有模块的联合类型
AnyModule = Annotated[
    HeaderModule
    | SectionModule
    | ImageGroupModule
    | ContainerModule
    | ActionGroupModule
    | ContextModule
    | DividerModule
    | FileModule
    | CountdownModule
    | InviteModule,
    Field(discriminator="type"),
]


class KookCardMessage(KookBaseSendDataClass):
    """卡片定义文档详见 : https://developer.kookapp.cn/doc/cardmessage
    适用于发送单个卡片消息
    将此消息类型放入`Json`的data字段进行卡片消息发送,适配器会自动添加顶层的列表
    若要发送多个卡片消息，推荐使用KookCardMessageContainer进行卡片消息组装

    使用方法：
    ```python
    chain = []
    chain.append(
            Json(
                data=KookCardMessage(
                    theme="info",
                    size="lg",
                    modules=[
                        HeaderModule(text=PlainTextElement(content="test1")),
                    ],
                ).to_dict()
            )
        )
    yield event.chain_result(chain)
    ```
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)
    type: Literal[KookModuleType.CARD] = KookModuleType.CARD
    theme: ThemeType | None = None
    size: SizeType | None = None
    color: str | None = None
    """16 进制色值"""
    modules: list[AnyModule] = Field(default_factory=list)
    """单个 card 模块数量不限制，但是一条消息中所有卡片的模块数量之和最多是 50"""

    def add_module(self, module: AnyModule):
        self.modules.append(module)


class KookCardMessageContainer(list[KookCardMessage]):
    """卡片消息容器(列表),可放入多个卡片消息(KookCardMessage)

    使用方法:
    ```python
    chain = []
        chain.append(
            Json(
                data=KookCardMessageContainer(
                    [
                        KookCardMessage(
                            theme="info",
                            size="lg",
                            modules=[
                                HeaderModule(text=PlainTextElement(content="test1")),
                            ],
                        )
                    ]
                ).to_dict()
            )
        )
        yield event.chain_result(chain)
    ```
    """

    def append(self, object: KookCardMessage) -> None:
        return super().append(object)

    def to_dict(
        self,
        by_alias=True,
        exclude_none=True,
        exclude_unset=False,
    ) -> list[dict]:
        """默认配置预期场景为发送数据,若需要使用此数据类接收数据并尽量原样json输出,
        请`exclude_none=False, exclude_unset=True`"""
        return [
            i.to_dict(
                by_alias=by_alias,
                exclude_none=exclude_none,
                exclude_unset=exclude_unset,
            )
            for i in self
        ]

    def to_json(
        self,
        indent: int | None = None,
        ensure_ascii: bool = True,
        by_alias=True,
        exclude_none=True,
        exclude_unset=False,
    ) -> str:
        """默认配置预期场景为发送数据,若需要使用此数据类接收数据并尽量原样json输出,
        请`exclude_none=False, exclude_unset=True`"""
        return json.dumps(
            [
                i.to_dict(
                    by_alias=by_alias,
                    exclude_none=exclude_none,
                    exclude_unset=exclude_unset,
                )
                for i in self
            ],
            indent=indent,
            ensure_ascii=ensure_ascii,
        )

    @classmethod
    def from_dict(cls, raw_data: list[dict[str, Any]]):
        return cls(KookCardMessage.from_dict(item) for item in raw_data)


class OrderMessage(BaseModel):
    index: int
    text: str
    type: KookMessageType
    reply_id: str | int = ""


class KookMessageSignal(IntEnum):
    """KOOK WebSocket 信令类型
    ws文档: https://developer.kookapp.cn/doc/websocket"""

    MESSAGE = 0
    """server->client  消息(s包含聊天和通知消息)"""
    HELLO = 1
    """server->client  客户端连接 ws 时, 服务端返回握手结果"""
    PING = 2
    """client->server  心跳，ping"""
    PONG = 3
    """server->client  心跳，pong"""
    RESUME = 4
    """client->server  resume, 恢复会话"""
    RECONNECT = 5
    """server->client  reconnect, 要求客户端断开当前连接重新连接"""
    RESUME_ACK = 6
    """server->client  resume ack"""


class KookChannelType(str, Enum):
    GROUP = "GROUP"
    PERSON = "PERSON"
    BROADCAST = "BROADCAST"


class KookAuthor(KookBaseReceiveDataClass):
    id: str
    username: str
    identify_num: str
    nickname: str
    bot: bool
    online: bool
    avatar: str | None = None
    vip_avatar: str | None = None
    status: int
    roles: list[int] = Field(default_factory=list)


class KookMarkdownMentionPart(KookBaseReceiveDataClass):
    """
    文档参考: https://developer.kookapp.cn/doc/event/message
    """

    id: str
    username: str
    full_name: str
    avatar: str


class KookMarkdownMentionRolePart(KookBaseReceiveDataClass):
    """
    文档参考: https://developer.kookapp.cn/doc/event/message
    """

    role_id: int
    name: str
    color: int
    color_type: int
    color_map: list[Any]
    position: int | None = None
    hoist: int | None = None
    mentionable: int | None = None
    permissions: int | None = None


class KookKMarkdown(KookBaseReceiveDataClass):
    raw_content: str
    mention_part: list[KookMarkdownMentionPart] = Field(default_factory=list)
    mention_role_part: list[KookMarkdownMentionRolePart] = Field(default_factory=list)


class KookRole(KookBaseReceiveDataClass):
    """服务器角色对象数据结构"""

    role_id: int = Field(alias="role_id")
    name: str | None = None
    color: int | None = None
    position: int | None = None
    hoist: int | None = 0  # 是否在成员列表中单独展示
    mentionable: int | None = 0  # 是否允许所有人提到该角色
    permissions: int | None = None


class KookRoleEventBody(KookBaseReceiveDataClass):
    """
    服务器角色相关事件 (added_role, updated_role, deleted_role) 的 Body 部分
    文档参考: https://developer.kookapp.cn/doc/event/guild-role
    """

    role_id: int | None = None  # 在 deleted_role 中通常只给 ID
    name: str | None = None
    color: int | None = None
    position: int | None = None
    hoist: int | None = None
    mentionable: int | None = None
    permissions: int | None = None
    # 有些事件会将完整的 role 对象包裹在 body 里
    # 如果是 added_role 且需要处理更完整的结构，可以扩展


class KookExtra(KookBaseReceiveDataClass):
    """事件结构定义
    文档参考 : https://developer.kookapp.cn/doc/event/event-introduction"""

    type: KookRoleExtraType | str | int
    """当 type 非系统消息(255)时, type为int

    当 type 为系统消息(255)时, type为str
    """

    code: str | None = None
    body: KookRole | dict[str, Any] | None = None
    author: KookAuthor | None = None
    kmarkdown: KookKMarkdown | None = None
    last_msg_content: str | None = None
    mention: list[str] = Field(default_factory=list)
    mention_all: bool = False
    mention_here: bool = False
    guild_id: str | None = None
    guild_type: int | None = None
    channel_name: str | None = None
    visible_only: str | None = None
    mention_no_at: list | None = None
    mention_roles: list[int] | None = None
    nav_channels: list | None = None
    emoji: list | None = None
    preview_content: str | None = None
    channel_type: int | None = None
    send_msg_device: int | None = None

    @field_validator("type", mode="before")
    @classmethod
    def parse_type(cls, value):
        """优先尝试匹配枚举，失败则保留原值"""
        if isinstance(value, str):
            if value in {e.value for e in KookRoleExtraType}:
                return KookRoleExtraType(value)

        return value


class KookMessageEventData(KookBaseReceiveDataClass):
    signal: Literal[KookMessageSignal.MESSAGE] = Field(
        KookMessageSignal.MESSAGE, exclude=True
    )
    """only for type hint"""

    channel_type: KookChannelType
    type: KookMessageType
    target_id: str
    author_id: str
    content: str | dict[str, Any]  # 道具消息时这里是dict
    msg_id: str
    msg_timestamp: int
    nonce: str
    from_type: int
    extra: KookExtra


class KookHelloEventData(KookBaseReceiveDataClass):
    signal: Literal[KookMessageSignal.HELLO] = Field(
        KookMessageSignal.HELLO, exclude=True
    )
    """only for type hint"""

    code: int
    session_id: str


class KookPingEventData(KookBaseReceiveDataClass):
    signal: Literal[KookMessageSignal.PING] = Field(
        KookMessageSignal.PING, exclude=True
    )
    """only for type hint"""


class KookPongEventData(KookBaseReceiveDataClass):
    signal: Literal[KookMessageSignal.PONG] = Field(
        KookMessageSignal.PONG, exclude=True
    )
    """only for type hint"""


class KookResumeEventData(KookBaseReceiveDataClass):
    signal: Literal[KookMessageSignal.RESUME] = Field(
        KookMessageSignal.RESUME, exclude=True
    )
    """only for type hint"""


class KookReconnectEventData(KookBaseReceiveDataClass):
    signal: Literal[KookMessageSignal.RECONNECT] = Field(
        KookMessageSignal.RECONNECT, exclude=True
    )
    """only for type hint"""

    code: int
    err: str


class KookResumeAckEventData(KookBaseReceiveDataClass):
    signal: Literal[KookMessageSignal.RESUME_ACK] = Field(
        KookMessageSignal.RESUME_ACK, exclude=True
    )
    """only for type hint"""

    session_id: str


class KookWebsocketEvent(KookBaseReceiveDataClass):
    """KOOK WebSocket 原始推送结构"""

    signal: KookMessageSignal = Field(
        ..., validation_alias="s", serialization_alias="s"
    )
    """信令类型"""
    data: Annotated[
        KookMessageEventData
        | KookHelloEventData
        | KookPingEventData
        | KookPongEventData
        | KookResumeEventData
        | KookReconnectEventData
        | KookResumeAckEventData
        | None,
        Field(discriminator="signal"),
    ] = Field(None, validation_alias="d", serialization_alias="d")
    """数据事件主体,对应原字段是'd'"""
    sn: int | None = None
    """消息序号 , 用来确定消息顺序和ws重连时使用  
    详见ws连接流程文档: https://developer.kookapp.cn/doc/websocket#%E8%BF%9E%E6%8E%A5%E6%B5%81%E7%A8%8B"""  # noqa: W291

    @model_validator(mode="before")
    @classmethod
    def _inject_signal_into_data(cls, data: Any) -> Any:
        """在解析前，把外层的 s 同步到内层的 d 中，供 discriminator 使用"""
        if isinstance(data, dict):
            s_value = data.get("s")
            d_value = data.get("d")
            if s_value is not None and isinstance(d_value, dict):
                d_value["signal"] = s_value
        return data


class KookUserTag(KookBaseReceiveDataClass):
    color: str
    bg_color: str
    text: str


class KookApiResponseBase(KookBaseReceiveDataClass):
    code: int
    message: str
    data: dict  # 就算请求失败了也是空dict

    def success(self) -> bool:
        return self.code == 0


class KookUserMeData(KookBaseReceiveDataClass):
    """USER_ME 接口返回的 'data' 字段主体"""

    id: str
    username: str
    identify_num: str
    nickname: str
    bot: bool
    online: bool
    status: int
    bot_status: int
    avatar: str
    vip_avatar: str | None = None
    banner: str | None = None
    roles: list[Any] = Field(default_factory=list)
    is_vip: bool
    vip_amp: bool
    wealth_level: int
    mobile_verified: bool
    client_id: str
    tag_info: KookUserTag | None = None


class KookUserMeResponse(KookApiResponseBase):
    """USER_ME 完整响应结构"""

    data: KookUserMeData


class KookUserMeViewData(KookBaseReceiveDataClass):
    """USER_ME 接口返回的 'data' 字段主体"""

    class KookTagInfo(KookBaseReceiveDataClass):
        color: str
        bg_color: str
        text: str

    id: str
    username: str
    identify_num: str
    online: bool
    os: str
    status: int
    avatar: str
    vip_avatar: str
    banner: str
    nickname: str
    roles: list[int]
    is_vip: bool
    vip_amp: bool
    bot: bool
    kpm_vip: str | None = None
    wealth_level: int
    bot_status: int
    tag_info: KookTagInfo
    mobile_verified: bool
    is_sys: bool
    client_id: str
    verified: bool
    joined_at: int
    active_time: int


class KookUserViewResponse(KookApiResponseBase):
    """USER_VIEW 完整响应结构"""

    data: KookUserMeViewData


class KookGatewayIndexData(KookBaseReceiveDataClass):
    url: str


class KookGatewayIndexResponse(KookApiResponseBase):
    """USER_ME 完整响应结构"""

    data: KookGatewayIndexData
