import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import quote, unquote, urlparse

__all__ = [
    "GitUnavailableError",
    "GitHubRepository",
    "RepositoryReference",
    "normalize_repository_url",
    "parse_repository_url",
]

_SCP_GIT_URL_PATTERN = re.compile(
    r"^git@(?P<host>[A-Za-z0-9.-]+):(?P<path>[^?#\s]+)$",
    re.IGNORECASE,
)


class GitUnavailableError(RuntimeError):
    """Raised when a Git transport is requested but Git is unavailable."""


@dataclass(frozen=True, slots=True)
class RepositoryReference:
    """Identify a repository and an optional source branch.

    Args:
        provider: Repository hosting provider name.
        owner: Repository owner or namespace.
        name: Repository name.
        branch: Explicit source branch, if present in the URL.
        transport: Transfer mechanism used to obtain the repository contents.
    """

    provider: str
    owner: str
    name: str
    branch: str | None = None
    transport: Literal["archive", "git"] = "archive"


@dataclass(frozen=True, slots=True)
class GitHubRepository:
    """Represent a public GitHub repository available through ZIP endpoints.

    Args:
        owner: GitHub repository owner.
        name: GitHub repository name.
        branch: Explicit or resolved source branch.
    """

    owner: str
    name: str
    branch: str | None = None

    @classmethod
    def parse(cls, url: str) -> "GitHubRepository":
        """Parse a public GitHub repository URL.

        Args:
            url: HTTP(S) GitHub URL, optionally ending in ``.git`` or a tree
                branch.

        Returns:
            Parsed GitHub repository.

        Raises:
            ValueError: If the URL is not a public GitHub repository URL.
        """
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in {
            "github.com",
            "www.github.com",
        }:
            raise ValueError("Invalid GitHub repository URL")

        parts = [unquote(part) for part in parsed.path.strip("/").split("/") if part]
        if len(parts) < 2:
            raise ValueError("Invalid GitHub repository URL")

        owner = parts[0]
        name = parts[1].removesuffix(".git")
        branch = None
        if len(parts) > 2:
            if parts[2] != "tree" or len(parts) < 4:
                raise ValueError("Invalid GitHub repository URL")
            branch = "/".join(parts[3:])

        if not owner or not name or owner in {".", ".."} or name in {".", ".."}:
            raise ValueError("Invalid GitHub repository URL")
        return cls(owner, name, branch)

    @property
    def default_branch_api_url(self) -> str:
        """Return the GitHub repository metadata API URL."""
        owner = quote(self.owner, safe="")
        name = quote(self.name, safe="")
        return f"https://api.github.com/repos/{owner}/{name}"

    @property
    def archive_url(self) -> str:
        """Return the source ZIP URL for the resolved branch.

        Raises:
            ValueError: If the source branch has not been resolved.
        """
        if not self.branch:
            raise ValueError("GitHub source branch has not been resolved")
        owner = quote(self.owner, safe="")
        name = quote(self.name, safe="")
        branch = quote(self.branch, safe="/")
        return f"https://github.com/{owner}/{name}/archive/refs/heads/{branch}.zip"

    def revision_archive_url(
        self,
        revision: str,
    ) -> str:
        """Return the ZIP URL for an exact GitHub revision.

        Args:
            revision: Commit hash or another exact GitHub revision.

        Returns:
            GitHub source ZIP URL.
        """
        owner = quote(self.owner, safe="")
        name = quote(self.name, safe="")
        encoded_revision = quote(revision, safe="")
        return f"https://github.com/{owner}/{name}/archive/{encoded_revision}.zip"

    def raw_file_url(self, path: str) -> str:
        """Return a raw file URL in the resolved branch.

        Args:
            path: Repository-relative file path.

        Returns:
            GitHub raw file URL.

        Raises:
            ValueError: If the source branch has not been resolved.
        """
        if not self.branch:
            raise ValueError("GitHub source branch has not been resolved")
        owner = quote(self.owner, safe="")
        name = quote(self.name, safe="")
        branch = quote(self.branch, safe="/")
        encoded_path = quote(path.lstrip("/"), safe="/")
        return (
            f"https://raw.githubusercontent.com/{owner}/{name}/{branch}/{encoded_path}"
        )


def normalize_repository_url(url: str) -> str:
    """Normalize a repository locator without changing its transport.

    Args:
        url: GitHub shorthand, HTTP(S), SSH, or SCP-style Git locator.

    Returns:
        A repository locator suitable for the selected transport.

    Raises:
        ValueError: If the locator is empty or uses an unsafe transport.
    """
    normalized = str(url or "").strip().rstrip("/")
    if not normalized or any(character.isspace() for character in normalized):
        raise ValueError("Invalid repository URL")
    if _SCP_GIT_URL_PATTERN.fullmatch(normalized):
        return normalized

    parsed = urlparse(normalized)
    if parsed.scheme:
        if parsed.scheme.lower() not in {"http", "https", "ssh"}:
            raise ValueError("Unsupported repository transport")
        if not parsed.hostname or parsed.query or parsed.fragment:
            raise ValueError("Invalid repository URL")
        if parsed.scheme.lower() in {"http", "https"} and parsed.username:
            raise ValueError("Repository URLs must not contain credentials")
        return normalized

    parts = [part for part in normalized.split("/") if part]
    if len(parts) == 2 and "." not in parts[0]:
        return f"https://github.com/{normalized}"
    if len(parts) >= 3 and "." in parts[0]:
        return f"https://{normalized}"
    raise ValueError("Invalid repository URL")


def parse_repository_url(url: str) -> RepositoryReference:
    """Parse a repository locator without exposing its transfer implementation.

    Args:
        url: GitHub shorthand, HTTP(S), SSH, or SCP-style Git locator.

    Returns:
        Provider-neutral repository identity and required transport.

    Raises:
        ValueError: If the URL is unsupported or invalid.
    """
    normalized = normalize_repository_url(url)
    scp_match = _SCP_GIT_URL_PATTERN.fullmatch(normalized)
    if scp_match:
        host = scp_match.group("host").lower()
        parts = [part for part in scp_match.group("path").strip("/").split("/") if part]
    else:
        parsed = urlparse(normalized)
        host = str(parsed.hostname or "").lower()
        if parsed.scheme.lower() in {"http", "https"} and host in {
            "github.com",
            "www.github.com",
        }:
            repository = GitHubRepository.parse(normalized)
            return RepositoryReference(
                provider="github",
                owner=repository.owner,
                name=repository.name,
                branch=repository.branch,
            )
        parts = [unquote(part) for part in parsed.path.strip("/").split("/") if part]

    if len(parts) < 2 or parts[-1].lower().endswith(".zip"):
        raise ValueError("Invalid Git repository URL")
    owner = "/".join(parts[:-1])
    name = parts[-1].removesuffix(".git")
    if not owner or not name or any(part in {".", ".."} for part in parts):
        raise ValueError("Invalid Git repository URL")
    return RepositoryReference(
        provider=host.removeprefix("www."),
        owner=owner,
        name=name,
        transport="git",
    )
