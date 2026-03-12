from astrbot.core import astrbot_config


def get_github_api_auth_header():
    token = astrbot_config["github_api_token"]
    return {"Authorization": f"Bearer {token}"}
