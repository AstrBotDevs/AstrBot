from astrbot.dashboard.docs_href import docs_href


def test_docs_href_defaults_to_zh_index() -> None:
    assert docs_href() == "/help/"
    assert docs_href("faq.html") == "/help/faq.html"
    assert docs_href("/platform/napcat.html") == "/help/platform/napcat.html"


def test_docs_href_english_prefix() -> None:
    assert docs_href(english=True) == "/help/en/"
    assert docs_href("faq.html", english=True) == "/help/en/faq.html"
    assert docs_href("/faq.html", english=True) == "/help/en/faq.html"
