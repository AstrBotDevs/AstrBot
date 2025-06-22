import discord
from typing import List
from astrbot.api.message_components import BaseMessageComponent


# Discord专用组件
class DiscordEmbed(BaseMessageComponent):
    """Discord Embed消息组件"""

    type: str = "discord_embed"

    def __init__(
        self,
        title: str = None,
        description: str = None,
        color: int = None,
        url: str = None,
        thumbnail: str = None,
        image: str = None,
        footer: str = None,
        fields: List[dict] = None,
    ):
        self.title = title
        self.description = description
        self.color = color
        self.url = url
        self.thumbnail = thumbnail
        self.image = image
        self.footer = footer
        self.fields = fields or []

    def to_discord_embed(self) -> discord.Embed:
        """转换为Discord Embed对象"""
        embed = discord.Embed()

        if self.title:
            embed.title = self.title
        if self.description:
            embed.description = self.description
        if self.color:
            embed.color = self.color
        if self.url:
            embed.url = self.url
        if self.thumbnail:
            embed.set_thumbnail(url=self.thumbnail)
        if self.image:
            embed.set_image(url=self.image)
        if self.footer:
            embed.set_footer(text=self.footer)

        for field in self.fields:
            embed.add_field(
                name=field.get("name", ""),
                value=field.get("value", ""),
                inline=field.get("inline", False),
            )

        return embed


class DiscordButton(BaseMessageComponent):
    """Discord按钮组件"""

    type: str = "discord_button"

    def __init__(
        self,
        label: str,
        custom_id: str = None,
        style: str = "primary",
        emoji: str = None,
        url: str = None,
        disabled: bool = False,
    ):
        self.label = label
        self.custom_id = custom_id
        self.style = style
        self.emoji = emoji
        self.url = url
        self.disabled = disabled

class DiscordReference(BaseMessageComponent):
    """Discord引用组件"""
    type: str = "discord_reference"
    def __init__(self, message_id: str, channel_id: str):
        self.message_id = message_id
        self.channel_id = channel_id


class DiscordView(BaseMessageComponent):
    """Discord视图组件，包含按钮和选择菜单"""

    type: str = "discord_view"

    def __init__(
        self, components: List[BaseMessageComponent] = None, timeout: float = None
    ):
        self.components = components or []
        self.timeout = timeout


    def to_discord_view(self) -> discord.ui.View:
        """转换为Discord View对象"""
        view = discord.ui.View(timeout=self.timeout)

        for component in self.components:
            if isinstance(component, DiscordButton):
                button_style = getattr(
                    discord.ButtonStyle, component.style, discord.ButtonStyle.primary
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
