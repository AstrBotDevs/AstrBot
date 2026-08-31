import astrbot.api.message_components as Comp
from astrbot.core.platform.sources.misskey.misskey_utils import serialize_message_chain


def test_misskey_serializes_url_buttons_as_mfm_links():
    text, has_at = serialize_message_chain(
        [
            Comp.Plain("Resources: "),
            Comp.ActionRow(
                buttons=[
                    Comp.Button(
                        id="docs",
                        label="Docs",
                        action=Comp.UrlAction(url="https://example.com/docs"),
                    ),
                    Comp.Button(
                        id="status",
                        label="Status",
                        action=Comp.UrlAction(url="https://status.example.com"),
                    ),
                ],
            ),
        ],
    )

    assert text == (
        "Resources: [Docs](https://example.com/docs) | "
        "[Status](https://status.example.com)"
    )
    assert has_at is False


def test_misskey_callback_buttons_use_row_fallback_text():
    text, has_at = serialize_message_chain(
        [
            Comp.ActionRow(
                buttons=[
                    Comp.Button(
                        id="confirm",
                        label="Confirm",
                        action=Comp.CallbackAction(data={"request_id": "req-1"}),
                    ),
                ],
                fallback_text="Reply with 'confirm' to continue.",
            ),
        ],
    )

    assert text == "Reply with 'confirm' to continue."
    assert has_at is False


def test_misskey_callback_buttons_fall_back_to_plain_labels():
    text, _ = serialize_message_chain(
        [
            Comp.Button(
                id="confirm",
                label="Confirm",
                action=Comp.CallbackAction(),
            ),
        ],
    )

    assert text == "Confirm"


def test_misskey_does_not_serialize_inbound_interactions():
    text, _ = serialize_message_chain(
        [
            Comp.ButtonInteraction(
                action_id="confirm",
                interaction_id="interaction-1",
            ),
        ],
    )

    assert text == ""
