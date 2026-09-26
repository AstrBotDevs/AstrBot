def format_exception(error: BaseException) -> str:
    """Return an exception type name plus its non-empty detail."""
    error_type = type(error).__name__
    detail = str(error).strip()
    if not detail:
        return error_type
    if detail.startswith(f"{error_type}:"):
        return detail
    return f"{error_type}: {detail}"
