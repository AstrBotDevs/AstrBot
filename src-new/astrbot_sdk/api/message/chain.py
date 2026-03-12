"""旧版消息链兼容实现。"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import components as Comp


@dataclass(slots=True)
class MessageChain:
    chain: list[Comp.BaseMessageComponent] = field(default_factory=list)
    use_t2i_: bool | None = None
    type: str | None = None

    def message(self, message: str) -> "MessageChain":
        self.chain.append(Comp.Plain(text=message))
        return self

    def at(self, name: str, qq: str) -> "MessageChain":
        self.chain.append(Comp.At(user_id=qq, user_name=name))
        return self

    def at_all(self) -> "MessageChain":
        self.chain.append(Comp.AtAll())
        return self

    def error(self, message: str) -> "MessageChain":
        self.chain.append(Comp.Plain(text=message))
        return self

    def url_image(self, url: str) -> "MessageChain":
        self.chain.append(Comp.Image(file=url))
        return self

    def file_image(self, path: str) -> "MessageChain":
        self.chain.append(Comp.Image(file=path))
        return self

    def base64_image(self, base64_str: str) -> "MessageChain":
        self.chain.append(Comp.Image(file=base64_str))
        return self

    def use_t2i(self, use_t2i: bool) -> "MessageChain":
        self.use_t2i_ = use_t2i
        return self

    def get_plain_text(self) -> str:
        return " ".join(
            component.text
            for component in self.chain
            if isinstance(component, Comp.Plain)
        )

    def squash_plain(self) -> "MessageChain":
        if not self.chain:
            return self

        new_chain: list[Comp.BaseMessageComponent] = []
        first_plain: Comp.Plain | None = None
        plain_texts: list[str] = []

        for component in self.chain:
            if isinstance(component, Comp.Plain):
                if first_plain is None:
                    first_plain = component
                    new_chain.append(component)
                plain_texts.append(component.text)
            else:
                new_chain.append(component)

        if first_plain is not None:
            first_plain.text = "".join(plain_texts)

        self.chain = new_chain
        return self
