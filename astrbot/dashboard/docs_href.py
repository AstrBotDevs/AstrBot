"""Same-origin documentation paths served under ``/help``."""

DOCS_MOUNT = "/help"


def docs_href(path: str = "", *, english: bool = False) -> str:
    """Return a WebUI documentation path.

    Args:
        path: Page path relative to the docs root, with or without a
            leading slash. An empty path returns the locale index.
        english: When True, prefix the English locale tree.

    Returns:
        An absolute path on the Dashboard origin, such as
        ``/help/faq.html`` or ``/help/en/faq.html``.
    """
    clean = path.strip().lstrip("/")
    prefix = f"{DOCS_MOUNT}/en" if english else DOCS_MOUNT
    if not clean:
        return f"{prefix}/"
    return f"{prefix}/{clean}"
