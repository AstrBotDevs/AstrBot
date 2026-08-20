"""Regression coverage for local container build entry points."""

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_compose(name: str) -> dict:
    with (REPO_ROOT / name).open(encoding="utf-8") as file:
        loaded = yaml.safe_load(file)
    assert isinstance(loaded, dict)
    return loaded


@pytest.mark.parametrize("compose_name", ["compose.yml", "compose-with-napcat.yml"])
def test_compose_keeps_astrbot_as_a_local_source_build(compose_name: str) -> None:
    """Compose deployments must build this checkout instead of pulling upstream."""
    compose = _load_compose(compose_name)
    astrbot = compose["services"]["astrbot"]

    assert astrbot["image"] == "astrbot:local"
    assert astrbot["build"]["context"] == "."
    assert astrbot["build"]["dockerfile"] == "Dockerfile"
    assert "./data:/AstrBot/data" in astrbot["volumes"]


@pytest.mark.parametrize("compose_name", ["compose.yml", "compose-with-napcat.yml"])
def test_compose_docs_service_uses_the_local_docs_image(compose_name: str) -> None:
    """Documentation uses the checked-out Dockerfile and remains read-only."""
    compose = _load_compose(compose_name)
    docs = compose["services"]["docs"]

    assert docs["image"] == "astrbot-docs:local"
    assert docs["build"] == {
        "context": ".",
        "dockerfile": "Dockerfile.docs",
    }
    assert docs["read_only"] is True
    assert docs["security_opt"] == ["no-new-privileges:true"]
    assert docs["tmpfs"] == ["/tmp:mode=1777"]


def test_runtime_image_copies_changelogs() -> None:
    """Dashboard changelog APIs read ``changelogs/`` from the application root."""
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    runtime_section = dockerfile.rsplit("\nFROM ", 1)[1]

    assert (
        "COPY --from=builder /AstrBot/changelogs /AstrBot/changelogs" in runtime_section
    )


def test_docs_dockerfile_builds_from_the_locked_docs_workspace() -> None:
    """The docs image must install from the lockfile before building static assets."""
    dockerfile = (REPO_ROOT / "Dockerfile.docs").read_text(encoding="utf-8")

    assert "FROM node:26.5.0-alpine@sha256:" in dockerfile
    assert " AS builder" in dockerfile
    assert "COPY docs/package.json docs/pnpm-lock.yaml ./" in dockerfile
    assert "pnpm fetch --frozen-lockfile" in dockerfile
    assert "pnpm install --frozen-lockfile --offline" in dockerfile
    assert "pnpm run docs:build" in dockerfile
    assert "FROM nginxinc/nginx-unprivileged:1.29.8-alpine@sha256:" in dockerfile
    assert "COPY docs/nginx.conf /etc/nginx/nginx.conf" in dockerfile
    assert (
        "COPY --from=builder /src/.vitepress/dist/ /usr/share/nginx/html/" in dockerfile
    )


def test_ci_validates_compose_and_dockerfile_build_syntax() -> None:
    """Keep Docker's own parser and Compose normalization in the CI gate."""
    workflow = (REPO_ROOT / ".github/workflows/code-format.yml").read_text(
        encoding="utf-8"
    )

    for command in (
        "docker compose -f compose.yml config --quiet",
        "docker compose -f compose-with-napcat.yml config --quiet",
        "docker compose --dry-run -f compose.yml build astrbot",
        "docker build --check --file Dockerfile.docs .",
        "docker build --check --file Dockerfile .",
    ):
        assert command in workflow

    assert "dockerfile: Dockerfile.docs" in workflow
