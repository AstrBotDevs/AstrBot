from collections.abc import Mapping


def normalize_headers(headers: object) -> dict[str, str]:
    if not isinstance(headers, dict):
        return {}
    return {str(key): str(value) for key, value in headers.items()}


def apply_default_headers(
    headers: dict[str, str],
    default_headers: Mapping[str, str],
) -> dict[str, str]:
    merged_headers = dict(headers)
    for default_name, default_value in default_headers.items():
        existing_name = next(
            (
                header_name
                for header_name in merged_headers
                if header_name.lower() == default_name.lower()
            ),
            None,
        )
        if existing_name is None:
            merged_headers[default_name] = default_value
            continue
        if merged_headers[existing_name].strip():
            continue
        merged_headers.pop(existing_name)
        merged_headers[default_name] = default_value
    return merged_headers
