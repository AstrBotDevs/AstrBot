"""Policies shared by WeChat enterprise and official-account adapters."""


def split_weixin_text(plain: str, max_length: int) -> list[str]:
    """Split at the last supported punctuation within each platform limit."""
    if max_length <= 0:
        raise ValueError("max_length must be positive")
    if len(plain) <= max_length:
        return [plain]
    result: list[str] = []
    start = 0
    punctuation = frozenset("｡!?.\n;")
    while start < len(plain):
        if start + max_length >= len(plain):
            result.append(plain[start:])
            break
        end = start + max_length
        cut_position = end
        for index in range(end, start, -1):
            if plain[index - 1] in punctuation:
                cut_position = index
                break
        result.append(plain[start:cut_position])
        start = cut_position
    return result


def normalize_weixin_api_base(api_base_url: str) -> str:
    """Keep the cgi-bin API suffix and trailing slash expected by wechatpy."""
    api_base_url = api_base_url.removesuffix("/")
    if not api_base_url.endswith("/cgi-bin"):
        api_base_url += "/cgi-bin"
    if not api_base_url.endswith("/"):
        api_base_url += "/"
    return api_base_url
