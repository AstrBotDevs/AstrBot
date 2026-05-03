import discord

from astrbot.api.message_components import BaseMessageComponent


# Discord专用组件
class DiscordEmbed(BaseMessageComponent):
    """Discord Embed消息组件"""

    type: str = "discord_embed"
    title: str | None = None
    description: str | None = None
    color: int | None = None
    url: str | None = None
    thumbnail: str | None = None
    image: str | None = None
    footer: str | None = None
    fields: list[dict] | None = None

    def __init__(
        self,
        title: str | None = None,
        description: str | None = None,
        color: int | None = None,
        url: str | None = None,
        thumbnail: str | None = None,
        image: str | None = None,
        footer: str | None = None,
        fields: list[dict] | None = None,
    ) -> None:
        super().__init__(
            title=title,
            description=description,
            color=color,
            url=url,
            thumbnail=thumbnail,
            image=image,
            footer=footer,
            fields=fields or [],
        )

    def empty(self) -> bool:
        return not (
            any(
                bool(value)
                for value in (
                    self.title,
                    self.description,
                    self.url,
                    self.thumbnail,
                    self.image,
                    self.footer,
                    self.fields,
                )
            )
            or self.color is not None
        )

    def to_discord_embed(self) -> discord.Embed:
        """转换为Discord Embed对象"""
        embed = discord.Embed()

        if self.title:
            embed.title = self.title
        if self.description:
            embed.description = self.description
        if self.color is not None:
            embed.color = self.color
        if self.url:
            embed.url = self.url
        if self.thumbnail:
            embed.set_thumbnail(url=self.thumbnail)
        if self.image:
            embed.set_image(url=self.image)
        if self.footer:
            embed.set_footer(text=self.footer)

        for field in self.fields or []:
            embed.add_field(
                name=field.get("name", ""),
                value=field.get("value", ""),
                inline=field.get("inline", False),
            )

        return embed


class DiscordButton(BaseMessageComponent):
    """Discord按钮组件"""

    type: str = "discord_button"
    label: str
    custom_id: str | None = None
    style: str = "primary"
    emoji: str | None = None
    url: str | None = None
    disabled: bool = False

    def __init__(
        self,
        label: str,
        custom_id: str | None = None,
        style: str = "primary",
        emoji: str | None = None,
        url: str | None = None,
        disabled: bool = False,
    ) -> None:
        super().__init__(
            label=label,
            custom_id=custom_id,
            style=style,
            emoji=emoji,
            url=url,
            disabled=disabled,
        )

    def empty(self) -> bool:
        return not bool(self.label or self.url or self.custom_id or self.emoji)


class DiscordReference(BaseMessageComponent):
    """Discord引用组件"""

    type: str = "discord_reference"
    message_id: str
    channel_id: str

    def __init__(self, message_id: str, channel_id: str) -> None:
        super().__init__(message_id=message_id, channel_id=channel_id)

    def empty(self) -> bool:
        return not bool(self.message_id and self.channel_id)


class DiscordView(BaseMessageComponent):
    """Discord视图组件，包含按钮和选择菜单"""

    type: str = "discord_view"
    components: list[BaseMessageComponent] | None = None
    timeout: float | None = None

    def __init__(
        self,
        components: list[BaseMessageComponent] | None = None,
        timeout: float | None = None,
    ) -> None:
        super().__init__(components=components or [], timeout=timeout)

    def empty(self) -> bool:
        return not bool(self.components)

    def to_discord_view(self) -> discord.ui.View:
        """转换为Discord View对象"""
        view = discord.ui.View(timeout=self.timeout)

        for component in self.components or []:
            if isinstance(component, DiscordButton):
                button_style = getattr(
                    discord.ButtonStyle,
                    component.style,
                    discord.ButtonStyle.primary,
                )

                if component.url:
                    # URL按钮
                    button = discord.ui.Button(
                        label=component.label,
                        style=discord.ButtonStyle.link,
                        url=component.url,
                        emoji=component.emoji,
                        disabled=component.disabled,
                    )
                else:
                    # 普通按钮
                    button = discord.ui.Button(
                        label=component.label,
                        style=button_style,
                        custom_id=component.custom_id,
                        emoji=component.emoji,
                        disabled=component.disabled,
                    )

                view.add_item(button)

        return view
