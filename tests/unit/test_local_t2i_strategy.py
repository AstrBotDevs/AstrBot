from unittest.mock import MagicMock, patch

from PIL import Image

from astrbot.core.utils.t2i.local_strategy import HeaderElement, InlineCodeElement


def test_header_element_render_wraps_long_headers():
    image = Image.new("RGB", (800, 600), "white")
    draw = MagicMock()
    element = HeaderElement("# A very long header")

    with patch(
        "astrbot.core.utils.t2i.local_strategy.TextMeasurer.split_text_to_fit_width",
        return_value=["A very long", "header"],
    ):
        new_y = element.render(image, draw, x=20, y=30, image_width=320, font_size=26)

    text_calls = [call.args[1] for call in draw.text.call_args_list]
    assert text_calls == ["A very long", "header"]
    draw.line.assert_called_once()
    assert new_y > 30


def test_inline_code_element_wraps_and_draws_each_line():
    image = Image.new("RGB", (800, 600), "white")
    draw = MagicMock()
    element = InlineCodeElement("some very long inline code")

    with patch(
        "astrbot.core.utils.t2i.local_strategy.TextMeasurer.split_text_to_fit_width",
        return_value=["some very long", "inline code"],
    ), patch(
        "astrbot.core.utils.t2i.local_strategy.TextMeasurer.get_text_size",
        side_effect=[(120, 26), (90, 26)],
    ):
        height = element.calculate_height(image_width=200, font_size=26)
        new_y = element.render(image, draw, x=20, y=40, image_width=200, font_size=26)

    assert height == (26 + 16) * 2
    assert draw.rounded_rectangle.call_count == 2
    text_calls = [call.args[1] for call in draw.text.call_args_list]
    assert text_calls == ["some very long", "inline code"]
    assert new_y == 40 + height
