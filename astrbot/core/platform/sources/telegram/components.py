from typing import Any

from telegram import (
    CallbackGame,
    CopyTextButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LinkPreviewOptions,
    LoginUrl,
    SwitchInlineQueryChosenChat,
    WebAppInfo,
)

from astrbot.api.message_components import BaseMessageComponent

TELEGRAM_CALLBACK_DATA_MAX_BYTES = 64


class TelegramInlineButton(BaseMessageComponent):
    """Telegram inline keyboard button component."""

    type: str = "telegram_inline_button"
    text: str
    url: str | None = None
    callback_data: str | None = None
    login_url: Any = None
    web_app: Any = None
    switch_inline_query: str | None = None
    switch_inline_query_current_chat: str | None = None
    switch_inline_query_chosen_chat: Any = None
    copy_text: Any = None
    callback_game: Any = None
    pay: bool | None = None
    style: str | None = None
    icon_custom_emoji_id: str | None = None

    def __init__(
        self,
        text: str,
        *,
        url: str | None = None,
        callback_data: str | None = None,
        login_url: LoginUrl | str | None = None,
        web_app: WebAppInfo | str | None = None,
        switch_inline_query: str | None = None,
        switch_inline_query_current_chat: str | None = None,
        switch_inline_query_chosen_chat: SwitchInlineQueryChosenChat
        | dict
        | None = None,
        copy_text: CopyTextButton | str | None = None,
        callback_game: CallbackGame | None = None,
        pay: bool | None = None,
        style: str | None = None,
        icon_custom_emoji_id: str | None = None,
    ) -> None:
        super().__init__(
            text=text,
            url=url,
            callback_data=callback_data,
            login_url=login_url,
            web_app=web_app,
            switch_inline_query=switch_inline_query,
            switch_inline_query_current_chat=switch_inline_query_current_chat,
            switch_inline_query_chosen_chat=switch_inline_query_chosen_chat,
            copy_text=copy_text,
            callback_game=callback_game,
            pay=pay,
            style=style,
            icon_custom_emoji_id=icon_custom_emoji_id,
        )
        self._validate_action()

    def _action_values(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "callback_data": self.callback_data,
            "login_url": self.login_url,
            "web_app": self.web_app,
            "switch_inline_query": self.switch_inline_query,
            "switch_inline_query_current_chat": self.switch_inline_query_current_chat,
            "switch_inline_query_chosen_chat": self.switch_inline_query_chosen_chat,
            "copy_text": self.copy_text,
            "callback_game": self.callback_game,
            "pay": self.pay,
        }

    def _validate_action(self) -> None:
        actions = {
            key: value
            for key, value in self._action_values().items()
            if value is not None and value is not False
        }
        if len(actions) != 1:
            raise ValueError(
                "Telegram inline button requires exactly one optional action.",
            )

        if self.callback_data is None:
            return

        callback_data_length = len(self.callback_data.encode("utf-8"))
        if not 1 <= callback_data_length <= TELEGRAM_CALLBACK_DATA_MAX_BYTES:
            raise ValueError(
                "Telegram inline button callback_data must be 1-64 UTF-8 bytes.",
            )

    def to_telegram_button(self) -> InlineKeyboardButton:
        payload = self._action_values()
        if isinstance(self.login_url, str):
            payload["login_url"] = LoginUrl(self.login_url)
        if isinstance(self.web_app, str):
            payload["web_app"] = WebAppInfo(self.web_app)
        if isinstance(self.switch_inline_query_chosen_chat, dict):
            payload["switch_inline_query_chosen_chat"] = SwitchInlineQueryChosenChat(
                **self.switch_inline_query_chosen_chat,
            )
        if isinstance(self.copy_text, str):
            payload["copy_text"] = CopyTextButton(self.copy_text)

        button_payload = {
            key: value for key, value in payload.items() if value is not None
        }
        if self.style is not None:
            button_payload["style"] = self.style
        if self.icon_custom_emoji_id is not None:
            button_payload["icon_custom_emoji_id"] = self.icon_custom_emoji_id

        return InlineKeyboardButton(
            text=self.text,
            **button_payload,
        )


class TelegramInlineKeyboard(BaseMessageComponent):
    """Telegram inline keyboard component."""

    type: str = "telegram_inline_keyboard"
    rows: list[list[Any]]

    def __init__(
        self,
        rows: list[list[TelegramInlineButton | InlineKeyboardButton]],
    ) -> None:
        super().__init__(rows=rows)

    def to_telegram_markup(self) -> InlineKeyboardMarkup:
        keyboard: list[list[InlineKeyboardButton]] = []
        for row in self.rows:
            keyboard.append(
                [
                    button.to_telegram_button()
                    if isinstance(button, TelegramInlineButton)
                    else button
                    for button in row
                ],
            )
        return InlineKeyboardMarkup(keyboard)


class TelegramMessageOptions(BaseMessageComponent):
    """Telegram send options for text rendering and link previews."""

    type: str = "telegram_message_options"
    parse_mode: str | None = None
    link_preview_is_disabled: bool | None = None
    link_preview_url: str | None = None
    link_preview_prefer_small_media: bool | None = None
    link_preview_prefer_large_media: bool | None = None
    link_preview_show_above_text: bool | None = None

    def __init__(
        self,
        *,
        parse_mode: str | None = None,
        link_preview_is_disabled: bool | None = None,
        link_preview_url: str | None = None,
        link_preview_prefer_small_media: bool | None = None,
        link_preview_prefer_large_media: bool | None = None,
        link_preview_show_above_text: bool | None = None,
    ) -> None:
        super().__init__(
            parse_mode=parse_mode,
            link_preview_is_disabled=link_preview_is_disabled,
            link_preview_url=link_preview_url,
            link_preview_prefer_small_media=link_preview_prefer_small_media,
            link_preview_prefer_large_media=link_preview_prefer_large_media,
            link_preview_show_above_text=link_preview_show_above_text,
        )

    def to_link_preview_options(self) -> LinkPreviewOptions | None:
        if not any(
            value is not None
            for value in (
                self.link_preview_is_disabled,
                self.link_preview_url,
                self.link_preview_prefer_small_media,
                self.link_preview_prefer_large_media,
                self.link_preview_show_above_text,
            )
        ):
            return None

        return LinkPreviewOptions(
            is_disabled=self.link_preview_is_disabled,
            url=self.link_preview_url,
            prefer_small_media=self.link_preview_prefer_small_media,
            prefer_large_media=self.link_preview_prefer_large_media,
            show_above_text=self.link_preview_show_above_text,
        )
