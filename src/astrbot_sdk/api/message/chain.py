from . import components as Comp
from dataclasses import dataclass, field


@dataclass
class MessageChain:
    """MessageChain 描述了一整条消息中带有的所有组件。
    现代消息平台的一条富文本消息中可能由多个组件构成，如文本、图片、At 等，并且保留了顺序。

    Attributes:
        `chain` (list): 用于顺序存储各个组件。
        `use_t2i_` (bool): 用于标记是否使用文本转图片服务。默认为 None，即跟随用户的设置。当设置为 True 时，将会使用文本转图片服务。

    """

    chain: list[Comp.BaseMessageComponent] = field(default_factory=list)
    use_t2i_: bool | None = None  # None 为跟随用户设置
    type: str | None = None
    """消息链承载的消息的类型。可选，用于让消息平台区分不同业务场景的消息链。"""

    def message(self, message: str):
        """添加一条文本消息到消息链 `chain` 中。

        Example:
            CommandResult().message("Hello ").message("world!")
            # 输出 Hello world!

        """
        self.chain.append(Comp.Plain(text=message))
        return self

    def at(self, name: str, qq: str):
        """添加一条 At 消息到消息链 `chain` 中。

        Example:
            CommandResult().at("张三", "12345678910")
            # 输出 @张三

        """
        self.chain.append(Comp.At(user_id=qq, user_name=name))
        return self

    def at_all(self):
        """添加一条 AtAll 消息到消息链 `chain` 中。

        Example:
            CommandResult().at_all()
            # 输出 @所有人

        """
        self.chain.append(Comp.AtAll())
        return self

    def error(self, message: str):
        """[Deprecated] 添加一条错误消息到消息链 `chain` 中

        Example:
            CommandResult().error("解析失败")

        """
        self.chain.append(Comp.Plain(text=message))
        return self

    def url_image(self, url: str):
        """添加一条图片消息（https 链接）到消息链 `chain` 中。

        Note:
            如果需要发送本地图片，请使用 `file_image` 方法。

        Example:
            CommandResult().image("https://example.com/image.jpg")

        """
        self.chain.append(Comp.Image(file=url))
        return self

    def file_image(self, path: str):
        """添加一条图片消息（本地文件路径）到消息链 `chain` 中。

        Note:
            如果需要发送网络图片，请使用 `url_image` 方法。

        Example:
            CommandResult().file_image("image.jpg")
        """
        self.chain.append(Comp.Image(file=path))
        return self

    def base64_image(self, base64_str: str):
        """添加一条图片消息（base64 编码字符串）到消息链 `chain` 中。

        Example:
            CommandResult().base64_image("iVBORw0KGgoAAAANSUhEUgAAAAUA...")
        """
        self.chain.append(Comp.Image(file=base64_str))
        return self

    def use_t2i(self, use_t2i: bool):
        """设置是否使用文本转图片服务。

        Args:
            use_t2i (bool): 是否使用文本转图片服务。默认为 None，即跟随用户的设置。当设置为 True 时，将会使用文本转图片服务。

        """
        self.use_t2i_ = use_t2i
        return self

    def get_plain_text(self) -> str:
        """获取纯文本消息。这个方法将获取 chain 中所有 Plain 组件的文本并拼接成一条消息。空格分隔。"""
        return " ".join(
            [comp.text for comp in self.chain if isinstance(comp, Comp.Plain)]
        )

    def squash_plain(self):
        """将消息链中的所有 Plain 消息段聚合到第一个 Plain 消息段中。"""
        if not self.chain:
            return None

        new_chain = []
        first_plain = None
        plain_texts = []

        for comp in self.chain:
            if isinstance(comp, Comp.Plain):
                if first_plain is None:
                    first_plain = comp
                    new_chain.append(comp)
                plain_texts.append(comp.text)
            else:
                new_chain.append(comp)

        if first_plain is not None:
            first_plain.text = "".join(plain_texts)

        self.chain = new_chain
        return self
