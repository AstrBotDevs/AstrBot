from typing import Any

from telegram import (
    CallbackGame,
    CopyTextButton,
    ForceReply,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InlineQueryResultAudio,
    InlineQueryResultCachedAudio,
    InlineQueryResultCachedDocument,
    InlineQueryResultCachedGif,
    InlineQueryResultCachedMpeg4Gif,
    InlineQueryResultCachedPhoto,
    InlineQueryResultCachedSticker,
    InlineQueryResultCachedVideo,
    InlineQueryResultCachedVoice,
    InlineQueryResultContact,
    InlineQueryResultDocument,
    InlineQueryResultGame,
    InlineQueryResultGif,
    InlineQueryResultLocation,
    InlineQueryResultMpeg4Gif,
    InlineQueryResultPhoto,
    InlineQueryResultsButton,
    InlineQueryResultVenue,
    InlineQueryResultVideo,
    InlineQueryResultVoice,
    InputTextMessageContent,
    KeyboardButton,
    LinkPreviewOptions,
    LoginUrl,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    SwitchInlineQueryChosenChat,
    WebAppInfo,
)

from astrbot.api.message_components import BaseMessageComponent

TELEGRAM_CALLBACK_DATA_MAX_BYTES = 64

TELEGRAM_INLINE_QUERY_RESULT_TYPES: dict[str, type] = {
    "article": InlineQueryResultArticle,
    "audio": InlineQueryResultAudio,
    "cached_audio": InlineQueryResultCachedAudio,
    "cached_document": InlineQueryResultCachedDocument,
    "cached_gif": InlineQueryResultCachedGif,
    "cached_mpeg4_gif": InlineQueryResultCachedMpeg4Gif,
    "cached_photo": InlineQueryResultCachedPhoto,
    "cached_sticker": InlineQueryResultCachedSticker,
    "cached_video": InlineQueryResultCachedVideo,
    "cached_voice": InlineQueryResultCachedVoice,
    "contact": InlineQueryResultContact,
    "document": InlineQueryResultDocument,
    "game": InlineQueryResultGame,
    "gif": InlineQueryResultGif,
    "location": InlineQueryResultLocation,
    "mpeg4_gif": InlineQueryResultMpeg4Gif,
    "photo": InlineQueryResultPhoto,
    "venue": InlineQueryResultVenue,
    "video": InlineQueryResultVideo,
    "voice": InlineQueryResultVoice,
}


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
            key: value
            for key, value in payload.items()
            if value is not None and value is not False
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


class TelegramKeyboardButton(BaseMessageComponent):
    """Telegram reply-keyboard button component."""

    type: str = "telegram_keyboard_button"
    text: str
    request_contact: bool | None = None
    request_location: bool | None = None
    request_poll: Any = None
    web_app: Any = None
    request_chat: Any = None
    request_users: Any = None
    style: str | None = None
    icon_custom_emoji_id: str | None = None

    def __init__(
        self,
        text: str,
        *,
        request_contact: bool | None = None,
        request_location: bool | None = None,
        request_poll: Any = None,
        web_app: WebAppInfo | str | None = None,
        request_chat: Any = None,
        request_users: Any = None,
        style: str | None = None,
        icon_custom_emoji_id: str | None = None,
    ) -> None:
        super().__init__(
            text=text,
            request_contact=request_contact,
            request_location=request_location,
            request_poll=request_poll,
            web_app=web_app,
            request_chat=request_chat,
            request_users=request_users,
            style=style,
            icon_custom_emoji_id=icon_custom_emoji_id,
        )

    def to_telegram_button(self) -> KeyboardButton:
        web_app = (
            WebAppInfo(self.web_app) if isinstance(self.web_app, str) else self.web_app
        )
        return KeyboardButton(
            text=self.text,
            request_contact=self.request_contact,
            request_location=self.request_location,
            request_poll=self.request_poll,
            web_app=web_app,
            request_chat=self.request_chat,
            request_users=self.request_users,
            style=self.style,
            icon_custom_emoji_id=self.icon_custom_emoji_id,
        )


class TelegramInputTextMessageContent(BaseMessageComponent):
    """Telegram inline-query text message content component."""

    type: str = "telegram_input_text_message_content"
    message_text: str
    parse_mode: str | None = None
    entities: Any = None
    link_preview_options: Any = None
    disable_web_page_preview: bool | None = None
    api_kwargs: dict[str, Any] | None = None

    def __init__(
        self,
        message_text: str,
        *,
        parse_mode: str | None = None,
        entities: Any = None,
        link_preview_options: Any = None,
        disable_web_page_preview: bool | None = None,
        api_kwargs: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message_text=message_text,
            parse_mode=parse_mode,
            entities=entities,
            link_preview_options=link_preview_options,
            disable_web_page_preview=disable_web_page_preview,
            api_kwargs=api_kwargs,
        )

    def to_telegram_content(self) -> InputTextMessageContent:
        return InputTextMessageContent(
            message_text=self.message_text,
            parse_mode=self.parse_mode,
            entities=self.entities,
            link_preview_options=self.link_preview_options,
            disable_web_page_preview=self.disable_web_page_preview,
            api_kwargs=self.api_kwargs,
        )


class TelegramInlineQueryResult(BaseMessageComponent):
    """Telegram inline-query result component.

    ``result_type`` accepts every Bot API inline result type supported by
    python-telegram-bot 22.6+: article, audio, cached_audio, cached_document,
    cached_gif, cached_mpeg4_gif, cached_photo, cached_sticker, cached_video,
    cached_voice, contact, document, game, gif, location, mpeg4_gif, photo,
    venue, video, and voice.
    """

    type: str = "telegram_inline_query_result"
    result_type: str
    payload: dict[str, Any]

    def __init__(self, result_type: str, **payload: Any) -> None:
        super().__init__(result_type=result_type, payload=payload)

    def to_telegram_result(self):
        result_type = self.result_type.strip().lower()
        result_class = TELEGRAM_INLINE_QUERY_RESULT_TYPES.get(result_type)
        if result_class is None:
            supported = ", ".join(sorted(TELEGRAM_INLINE_QUERY_RESULT_TYPES))
            raise ValueError(
                f"Unsupported Telegram inline query result type: {self.result_type}. "
                f"Supported types: {supported}.",
            )
        return result_class(**_convert_telegram_payload(self.payload))


class TelegramInlineQueryResultsButton(BaseMessageComponent):
    """Telegram inline-query answer button component."""

    type: str = "telegram_inline_query_results_button"
    text: str
    web_app: Any = None
    start_parameter: str | None = None

    def __init__(
        self,
        text: str,
        *,
        web_app: WebAppInfo | str | None = None,
        start_parameter: str | None = None,
    ) -> None:
        super().__init__(
            text=text,
            web_app=web_app,
            start_parameter=start_parameter,
        )

    def to_telegram_button(self) -> InlineQueryResultsButton:
        web_app = (
            WebAppInfo(self.web_app) if isinstance(self.web_app, str) else self.web_app
        )
        return InlineQueryResultsButton(
            text=self.text,
            web_app=web_app,
            start_parameter=self.start_parameter,
        )


class TelegramReplyKeyboard(BaseMessageComponent):
    """Telegram custom reply keyboard component."""

    type: str = "telegram_reply_keyboard"
    rows: list[list[Any]]
    resize_keyboard: bool | None = None
    one_time_keyboard: bool | None = None
    selective: bool | None = None
    input_field_placeholder: str | None = None
    is_persistent: bool | None = None

    def __init__(
        self,
        rows: list[list[str | TelegramKeyboardButton | KeyboardButton]],
        *,
        resize_keyboard: bool | None = None,
        one_time_keyboard: bool | None = None,
        selective: bool | None = None,
        input_field_placeholder: str | None = None,
        is_persistent: bool | None = None,
    ) -> None:
        super().__init__(
            rows=rows,
            resize_keyboard=resize_keyboard,
            one_time_keyboard=one_time_keyboard,
            selective=selective,
            input_field_placeholder=input_field_placeholder,
            is_persistent=is_persistent,
        )

    def to_telegram_markup(self) -> ReplyKeyboardMarkup:
        keyboard: list[list[str | KeyboardButton]] = []
        for row in self.rows:
            keyboard.append(
                [
                    button.to_telegram_button()
                    if isinstance(button, TelegramKeyboardButton)
                    else button
                    for button in row
                ],
            )
        return ReplyKeyboardMarkup(
            keyboard,
            resize_keyboard=self.resize_keyboard,
            one_time_keyboard=self.one_time_keyboard,
            selective=self.selective,
            input_field_placeholder=self.input_field_placeholder,
            is_persistent=self.is_persistent,
        )


class TelegramRemoveKeyboard(BaseMessageComponent):
    """Telegram reply-keyboard removal component."""

    type: str = "telegram_remove_keyboard"
    selective: bool | None = None

    def __init__(self, *, selective: bool | None = None) -> None:
        super().__init__(selective=selective)

    def to_telegram_markup(self) -> ReplyKeyboardRemove:
        return ReplyKeyboardRemove(selective=self.selective)


class TelegramForceReply(BaseMessageComponent):
    """Telegram force-reply prompt component."""

    type: str = "telegram_force_reply"
    selective: bool | None = None
    input_field_placeholder: str | None = None

    def __init__(
        self,
        *,
        selective: bool | None = None,
        input_field_placeholder: str | None = None,
    ) -> None:
        super().__init__(
            selective=selective,
            input_field_placeholder=input_field_placeholder,
        )

    def to_telegram_markup(self) -> ForceReply:
        return ForceReply(
            selective=self.selective,
            input_field_placeholder=self.input_field_placeholder,
        )


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


class TelegramMediaGroupItem(BaseMessageComponent):
    """Telegram media group item for explicit album sending."""

    type: str = "telegram_media_group_item"
    media_type: str
    media: Any
    filename: str | None = None
    thumbnail: Any = None
    has_spoiler: bool | None = None
    show_caption_above_media: bool | None = None
    supports_streaming: bool | None = None
    disable_content_type_detection: bool | None = None
    duration: int | None = None
    performer: str | None = None
    title: str | None = None

    def __init__(
        self,
        media_type: str,
        media: Any,
        *,
        filename: str | None = None,
        thumbnail: Any = None,
        has_spoiler: bool | None = None,
        show_caption_above_media: bool | None = None,
        supports_streaming: bool | None = None,
        disable_content_type_detection: bool | None = None,
        duration: int | None = None,
        performer: str | None = None,
        title: str | None = None,
    ) -> None:
        normalized_media_type = media_type.strip().lower()
        if normalized_media_type not in {"photo", "video", "document", "audio"}:
            raise ValueError(
                "Telegram media group item type must be one of photo, video, document, or audio.",
            )
        super().__init__(
            media_type=normalized_media_type,
            media=media,
            filename=filename,
            thumbnail=thumbnail,
            has_spoiler=has_spoiler,
            show_caption_above_media=show_caption_above_media,
            supports_streaming=supports_streaming,
            disable_content_type_detection=disable_content_type_detection,
            duration=duration,
            performer=performer,
            title=title,
        )


class TelegramMediaGroup(BaseMessageComponent):
    """Explicit Telegram album component with common InputMedia options."""

    type: str = "telegram_media_group"
    items: list[TelegramMediaGroupItem]
    caption: str | None = None
    parse_mode: str | None = None

    def __init__(
        self,
        items: list[TelegramMediaGroupItem],
        *,
        caption: str | None = None,
        parse_mode: str | None = None,
    ) -> None:
        if not items:
            raise ValueError("TelegramMediaGroup requires at least one media item.")
        super().__init__(items=items, caption=caption, parse_mode=parse_mode)

    @staticmethod
    def photo(
        media: Any,
        *,
        filename: str | None = None,
        has_spoiler: bool | None = None,
        show_caption_above_media: bool | None = None,
    ) -> TelegramMediaGroupItem:
        return TelegramMediaGroupItem(
            "photo",
            media,
            filename=filename,
            has_spoiler=has_spoiler,
            show_caption_above_media=show_caption_above_media,
        )

    @staticmethod
    def video(
        media: Any,
        *,
        filename: str | None = None,
        thumbnail: Any = None,
        has_spoiler: bool | None = None,
        show_caption_above_media: bool | None = None,
        supports_streaming: bool | None = None,
    ) -> TelegramMediaGroupItem:
        return TelegramMediaGroupItem(
            "video",
            media,
            filename=filename,
            thumbnail=thumbnail,
            has_spoiler=has_spoiler,
            show_caption_above_media=show_caption_above_media,
            supports_streaming=supports_streaming,
        )

    @staticmethod
    def document(
        media: Any,
        *,
        filename: str | None = None,
        thumbnail: Any = None,
        disable_content_type_detection: bool | None = None,
    ) -> TelegramMediaGroupItem:
        return TelegramMediaGroupItem(
            "document",
            media,
            filename=filename,
            thumbnail=thumbnail,
            disable_content_type_detection=disable_content_type_detection,
        )

    @staticmethod
    def audio(
        media: Any,
        *,
        filename: str | None = None,
        thumbnail: Any = None,
        duration: int | None = None,
        performer: str | None = None,
        title: str | None = None,
    ) -> TelegramMediaGroupItem:
        return TelegramMediaGroupItem(
            "audio",
            media,
            filename=filename,
            thumbnail=thumbnail,
            duration=duration,
            performer=performer,
            title=title,
        )


def _convert_telegram_payload(value: Any) -> Any:
    if isinstance(value, TelegramInlineKeyboard):
        return value.to_telegram_markup()
    if isinstance(value, TelegramInputTextMessageContent):
        return value.to_telegram_content()
    if isinstance(value, TelegramInlineQueryResultsButton):
        return value.to_telegram_button()
    if isinstance(value, TelegramInlineQueryResult):
        return value.to_telegram_result()
    if isinstance(value, list):
        return [_convert_telegram_payload(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_convert_telegram_payload(item) for item in value)
    if isinstance(value, dict):
        return {key: _convert_telegram_payload(item) for key, item in value.items()}
    return value
