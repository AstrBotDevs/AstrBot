from astrbot.core import astrbot_config


def get_github_api_auth_header(url: str):
    if not url.startswith("https://api.github.com"):
        return {}
    token = astrbot_config.get("github_api_token")
    return {"Authorization": f"Bearer {token}"} if token else {}
