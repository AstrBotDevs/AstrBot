from app.core.config import settings
from app.models.user import User


def admin_email_set() -> set[str]:
    """Configured operator emails (lowercase)."""
    return {
        part.strip().lower()
        for part in settings.admin_emails.split(",")
        if part.strip()
    }


def resolve_role_for_email(email: str) -> str:
    """Map a new or logging-in user to customer or admin."""
    if email.lower() in admin_email_set():
        return "admin"
    return "customer"


def sync_user_role(user: User) -> None:
    """Apply FISH_ADMIN_EMAILS to the user row (e.g. on login)."""
    user.role = resolve_role_for_email(user.email)
