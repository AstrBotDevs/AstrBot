"""Delivery targets stored in an active cron job payload."""


def get_delivery_sessions(payload: dict) -> list[str]:
    """Read ordered, unique delivery sessions, including legacy jobs.

    Args:
        payload: The job payload, or a set of requested delivery fields.

    Returns:
        The delivery sessions, with the agent context session first.
    """
    sessions = payload.get("sessions")
    if not isinstance(sessions, list):
        sessions = [payload.get("session")]
    return list(
        dict.fromkeys(s.strip() for s in sessions if isinstance(s, str) and s.strip())
    )
