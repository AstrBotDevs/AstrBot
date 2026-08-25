import discord

from astrbot.api.message_components import (
    ActionRow,
    BaseMessageComponent,
    ButtonStyle,
    CallbackAction,
    UrlAction,
)
from astrbot.core.platform.button_interaction import encode_button_callback


def action_rows_to_discord_view(
    action_rows: list[ActionRow],
) -> discord.ui.View:
    """Convert common action rows to a Discord view.

    Args:
        action_rows: Common action rows to render.

    Returns:
        A Discord view containing the supported buttons.

    Raises:
        ValueError: If the rows exceed Discord's component limits.
    """
    if len(action_rows) > 5:
        raise ValueError("Discord messages support at most five action rows.")

    view = discord.ui.View(timeout=None)
    style_mapping = {
        ButtonStyle.DEFAULT: discord.ButtonStyle.secondary,
        ButtonStyle.PRIMARY: discord.ButtonStyle.primary,
        ButtonStyle.SUCCESS: discord.ButtonStyle.success,
        ButtonStyle.DANGER: discord.ButtonStyle.danger,
    }

    for row_index, action_row in enumerate(action_rows):
        if len(action_row.buttons) > 5:
            raise ValueError("Discord action rows support at most five buttons.")
        for button in action_row.buttons:
            label = button.label[:80]
            if isinstance(button.action, UrlAction):
                item = discord.ui.Button(
                    label=label,
                    style=discord.ButtonStyle.link,
                    url=button.action.url,
                    row=row_index,
                )
            elif isinstance(button.action, CallbackAction):
                custom_id = encode_button_callback(button.id, button.action.data)
                if len(custom_id) > 100:
                    raise ValueError(
                        f"Discord button callback payload exceeds 100 characters: {button.id}"
                    )
                item = discord.ui.Button(
                    label=label,
                    style=style_mapping[button.style],
                    custom_id=custom_id,
                    row=row_index,
                )
            else:
                continue
            view.add_item(item)

    return view


# Discord专用组件
class DiscordEmbed(BaseMessageComponent):
    """Discord Embed消息组件"""

    type: str = "discord_embed"

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
        custom_id: str | None = None,
        style: str = "primary",
        emoji: str | None = None,
        url: str | None = None,
        disabled: bool = False,
    ) -> None:
        self.label = label
        self.custom_id = custom_id
        self.style = style
        self.emoji = emoji
        self.url = url
        self.disabled = disabled


class DiscordReference(BaseMessageComponent):
    """Discord引用组件"""

    type: str = "discord_reference"

    def __init__(self, message_id: str, channel_id: str) -> None:
        self.message_id = message_id
        self.channel_id = channel_id


class DiscordView(BaseMessageComponent):
    """Discord视图组件，包含按钮和选择菜单"""

    type: str = "discord_view"

    def __init__(
        self,
        components: list[BaseMessageComponent] | None = None,
        timeout: float | None = None,
    ) -> None:
        self.components = components or []
        self.timeout = timeout

    def to_discord_view(self) -> discord.ui.View:
        """转换为Discord View对象"""
        view = discord.ui.View(timeout=self.timeout)

        for component in self.components:
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
