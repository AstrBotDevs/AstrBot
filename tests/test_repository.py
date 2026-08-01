import pytest

from astrbot.core.repository import (
    GitHubRepository,
    normalize_repository_url,
    parse_repository_url,
)


def test_github_repository_resolves_branch_with_slashes() -> None:
    repository = GitHubRepository.parse(
        "https://github.com/AstrBotDevs/AstrBot.git/tree/feature/updater"
    )

    assert repository.owner == "AstrBotDevs"
    assert repository.name == "AstrBot"
    assert repository.branch == "feature/updater"
    assert repository.archive_url == (
        "https://github.com/AstrBotDevs/AstrBot/archive/refs/heads/feature/updater.zip"
    )


def test_non_github_http_repository_uses_git_transport() -> None:
    repository = parse_repository_url("https://gitee.com/astrbot/demo.git")

    assert repository.provider == "gitee.com"
    assert repository.owner == "astrbot"
    assert repository.name == "demo"
    assert repository.transport == "git"


def test_github_ssh_repository_uses_git_transport() -> None:
    repository = parse_repository_url("git@github.com:AstrBotDevs/AstrBot.git")

    assert repository.provider == "github.com"
    assert repository.owner == "AstrBotDevs"
    assert repository.name == "AstrBot"
    assert repository.transport == "git"


def test_repository_normalization_accepts_github_shorthand() -> None:
    assert (
        normalize_repository_url("AstrBotDevs/AstrBot")
        == "https://github.com/AstrBotDevs/AstrBot"
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://gitee.com/astrbot/demo",
        "https://example.com/astrbot/demo",
    ],
)
def test_github_repository_rejects_other_hosts(url: str) -> None:
    with pytest.raises(ValueError, match="Invalid GitHub repository URL"):
        GitHubRepository.parse(url)


@pytest.mark.parametrize(
    "url",
    [
        "file:///tmp/plugin",
        "ext::sh -c dangerous",
        "https://example.com/plugin.zip",
        "https://user:secret@example.com/owner/plugin.git",
    ],
)
def test_repository_parser_rejects_unsafe_or_non_repository_urls(url: str) -> None:
    with pytest.raises(ValueError):
        parse_repository_url(url)
