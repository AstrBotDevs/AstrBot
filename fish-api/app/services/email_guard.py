"""Block common mailbox typos at registration."""

from fastapi import HTTPException, status

# domain typo -> suggested correct domain
_BLOCKED_TYPO_DOMAINS: dict[str, str] = {
    "gmai.com": "gmail.com",
    "gmial.com": "gmail.com",
    "gmal.com": "gmail.com",
    "gamil.com": "gmail.com",
    "gnail.com": "gmail.com",
    "hotmial.com": "hotmail.com",
    "hotmal.com": "hotmail.com",
    "outlok.com": "outlook.com",
    "outllok.com": "outlook.com",
    "qq.co": "qq.com",
}


def assert_registration_email_ok(email: str) -> None:
    """Reject registrations that look like common email domain typos.

    Args:
        email: Normalized lowercase email.

    Raises:
        HTTPException: When the domain is a known typo.
    """
    parts = email.rsplit("@", 1)
    if len(parts) != 2:
        return
    domain = parts[1].lower()
    suggested = _BLOCKED_TYPO_DOMAINS.get(domain)
    if suggested is None:
        return
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"邮箱域名「{domain}」像是写错了，请用 {suggested}",
    )
