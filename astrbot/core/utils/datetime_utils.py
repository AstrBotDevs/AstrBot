import uuid
from datetime import datetime, timezone


def generate_timestamp_id() -> str:
    """Generate a compact timestamp-based identifier.

    Returns:
        The local time in ``YYYYMMDDHHMMSSmmm`` format followed by four random
        hexadecimal characters.
    """
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")[:-3]
    return f"{timestamp}_{uuid.uuid4().hex[:4]}"


def normalize_datetime_utc(dt: datetime | None) -> datetime | None:
    """Normalize datetime values to UTC.

    Naive datetimes are interpreted as UTC to match SQLite storage behavior.
    """
    if dt is None:
        return None
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def to_utc_isoformat(dt: datetime | None) -> str | None:
    normalized = normalize_datetime_utc(dt)
    if normalized is None:
        return None
    return normalized.isoformat()


def to_utc_timestamp(dt: datetime | None) -> float | None:
    normalized = normalize_datetime_utc(dt)
    if normalized is None:
        return None
    return normalized.timestamp()
