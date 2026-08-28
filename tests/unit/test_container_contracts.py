"""Regression coverage for local container build entry points."""

import re
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


def _is_unprivileged(service: dict) -> bool:
    return service.get("privileged") in (None, False)


def test_default_compose_astrbot_is_unprivileged() -> None:
    """Default `docker compose up` must not run AstrBot as privileged."""
    compose = _load_compose("compose.yml")
    astrbot = compose["services"]["astrbot"]
    assert _is_unprivileged(astrbot)
    assert not any(
        "docker.sock" in str(volume) for volume in astrbot.get("volumes", [])
    )


def test_compose_computer_profile_mounts_docker_sock() -> None:
    """Computer-tool Docker access is an explicit Compose profile."""
    compose = _load_compose("compose.yml")
    computer = compose["services"]["computer"]
    assert computer["profiles"] == ["computer"]
    assert "./data:/AstrBot/data" in computer["volumes"]
    assert "/var/run/docker.sock:/var/run/docker.sock" in computer["volumes"]
    assert _is_unprivileged(computer)
    assert computer["image"] == "astrbot:local"


def test_napcat_compose_keeps_astrbot_unprivileged_and_napcat_privileged() -> None:
    compose = _load_compose("compose-with-napcat.yml")
    astrbot = compose["services"]["astrbot"]
    napcat = compose["services"]["napcat"]
    assert _is_unprivileged(astrbot)
    assert "/var/run/docker.sock:/var/run/docker.sock" in astrbot["volumes"]
    assert napcat["privileged"] is True


@pytest.mark.parametrize("compose_name", ["compose.yml", "compose-with-napcat.yml"])
def test_compose_does_not_ship_a_separate_docs_service(compose_name: str) -> None:
    """Documentation is bundled into the Dashboard at /help/, not a sidecar."""
    compose = _load_compose(compose_name)
    assert "docs" not in compose["services"]
    rendered = yaml.safe_dump(compose)
    assert "6186" not in rendered
    assert "Dockerfile.docs" not in rendered


def test_dockerfile_playwright_version_matches_requirements() -> None:
    """Image Playwright must match the locked runtime specifier, not downgrade it."""
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    docker_match = re.search(
        r"^    PLAYWRIGHT_VERSION=([0-9]+\.[0-9]+\.[0-9]+) \\$",
        dockerfile,
        re.MULTILINE,
    )
    assert docker_match is not None
    docker_version = docker_match.group(1)

    requirements = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
    req_match = re.search(
        r"^playwright>=([0-9]+\.[0-9]+\.[0-9]+)$",
        requirements,
        re.MULTILINE,
    )
    assert req_match is not None
    assert docker_version == req_match.group(1)
    assert docker_version.startswith("1.62.")


def test_runtime_image_copies_changelogs() -> None:
    """Dashboard changelog APIs read ``changelogs/`` from the application root."""
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    runtime_section = dockerfile.rsplit("\nFROM ", 1)[1]

    assert (
        "COPY --from=builder /AstrBot/changelogs /AstrBot/changelogs" in runtime_section
    )


def test_dockerfile_builds_docs_into_dashboard_help() -> None:
    """The runtime image must bundle VitePress output under the WebUI help path."""
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "ASTRBOT_DOCS_BASE=/help/ pnpm run docs:build" in dockerfile
    assert (
        "cp -a /AstrBot/docs/.vitepress/dist/. /AstrBot/astrbot/dashboard/dist/help/"
        in dockerfile
    )
    assert (
        "cp -a /AstrBot/docs/.vitepress/dist/. /AstrBot/dashboard/dist/help/"
        in dockerfile
    )
    assert not (REPO_ROOT / "Dockerfile.docs").exists()


def test_ci_validates_compose_and_dockerfile_build_syntax() -> None:
    """Keep Docker's own parser and Compose normalization in the CI gate."""
    workflow = (REPO_ROOT / ".github/workflows/code-format.yml").read_text(
        encoding="utf-8"
    )

    for command in (
        "docker compose -f compose.yml config --quiet",
        "docker compose -f compose-with-napcat.yml config --quiet",
        "docker compose --dry-run -f compose.yml build astrbot",
        "docker build --check --file Dockerfile .",
    ):
        assert command in workflow

    assert "Dockerfile.docs" not in workflow


def test_makefile_builds_docs_into_dashboard_help() -> None:
    """Local production builds must use the in-app /help/ base path."""
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")

    assert "build-docs: build-dashboard" in makefile
    assert "ASTRBOT_DOCS_BASE=/help/ $(PNPM) run docs:build" in makefile
    assert "Dockerfile.docs" not in makefile


def test_docs_ci_builds_with_help_base() -> None:
    workflow = (REPO_ROOT / ".github/workflows/build-docs.yml").read_text(
        encoding="utf-8"
    )

    assert "ASTRBOT_DOCS_BASE: /help/" in workflow
