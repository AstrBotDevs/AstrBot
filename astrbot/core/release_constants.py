import re

NIGHTLY_TAG = "nightly"
GITHUB_REPO_SLUG = "AstrBotDevs/AstrBot"
GITHUB_RELEASE_API = f"https://api.github.com/repos/{GITHUB_REPO_SLUG}/releases"
GITHUB_ARCHIVE_BASE = f"https://github.com/{GITHUB_REPO_SLUG}/archive"
PRERELEASE_TAG_REGEX = re.compile(
    rf"[\-_.]?(alpha|beta|rc|dev|{re.escape(NIGHTLY_TAG)}|pre|preview)[\-_.]?\d*$",
    re.IGNORECASE,
)
