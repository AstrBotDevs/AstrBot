import importlib.metadata as importlib_metadata
import logging
import os
import re
import shlex
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import SpecifierSet
from packaging.version import InvalidVersion, Version

from astrbot.core.utils.astrbot_path import get_astrbot_site_packages_path
from astrbot.core.utils.runtime_env import is_packaged_desktop_runtime

logger = logging.getLogger("astrbot")


class RequirementsPrecheckFailed(Exception):
    """Raised when the pre-check of requirements fails."""

    pass


@dataclass(frozen=True)
class ParsedPackageInput:
    specs: tuple[str, ...]
    requirement_names: frozenset[str]


def canonicalize_distribution_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).strip("-").lower()


def strip_inline_requirement_comment(raw_input: str) -> str:
    if raw_input.lstrip().startswith("#"):
        return ""
    return re.split(r"[ \t]+#", raw_input, maxsplit=1)[0].strip()


def _specifier_contains_version(specifier: SpecifierSet, version: str) -> bool:
    try:
        parsed_version = Version(version)
    except InvalidVersion:
        return False
    return specifier.contains(parsed_version, prereleases=True)


def _looks_like_local_path_reference(token: str) -> bool:
    candidate = token.strip()
    if not candidate:
        return False
    return candidate in {".", ".."} or candidate.startswith(
        ("./", "../", "/", "~/", ".\\", "..\\", "\\")
    )


def looks_like_direct_reference(token: str) -> bool:
    candidate = token.strip()
    if not candidate:
        return False
    return (
        _looks_like_local_path_reference(candidate)
        or candidate.startswith("git+")
        or "://" in candidate
    )


def extract_requirement_name(raw_requirement: str) -> str | None:
    line = raw_requirement.split("#", 1)[0].strip()
    if not line:
        return None
    if line.startswith(("-r", "--requirement", "-c", "--constraint")):
        return None

    egg_match = re.search(r"#egg=([A-Za-z0-9_.-]+)", raw_requirement)
    if egg_match:
        return canonicalize_distribution_name(egg_match.group(1))

    if line.startswith("-"):
        return None

    candidate = re.split(r"[<>=!~;\s\[]", line, maxsplit=1)[0].strip()
    if not candidate:
        return None
    return canonicalize_distribution_name(candidate)


def _parse_editable_or_direct_name(target: str) -> str | None:
    name = extract_requirement_name(target)
    if not name:
        return None
    if "#egg=" in target or not looks_like_direct_reference(target):
        return name
    return None


def _parse_requirement_line(
    line: str,
) -> tuple[str, SpecifierSet | None] | None:
    if line.startswith(("-c", "--constraint")):
        return None

    try:
        req = Requirement(line)
    except InvalidRequirement:
        tokens = shlex.split(line)
        if not tokens:
            return None

        editable_target: str | None = None
        if tokens[0] in {"-e", "--editable"} and len(tokens) > 1:
            editable_target = tokens[1]
        elif tokens[0].startswith("--editable="):
            editable_target = tokens[0].split("=", 1)[1]

        if editable_target:
            name = _parse_editable_or_direct_name(editable_target)
            if name:
                return name, None

        name = _parse_editable_or_direct_name(line)
        if name:
            return name, None

        return None

    if req.marker and not req.marker.evaluate():
        return None

    return canonicalize_distribution_name(req.name), (req.specifier or None)


def _extract_requirement_names_from_package_tokens(tokens: list[str]) -> frozenset[str]:
    requirement_names: set[str] = set()
    skip_next_for: str | None = None

    for token in tokens:
        if skip_next_for:
            if skip_next_for == "editable":
                name = _parse_editable_or_direct_name(token)
                if name:
                    requirement_names.add(name)
            skip_next_for = None
            continue

        if token in {"-e", "--editable"}:
            skip_next_for = "editable"
            continue

        if token in {
            "-i",
            "--index-url",
            "--extra-index-url",
            "-f",
            "--find-links",
            "--trusted-host",
            "-r",
            "--requirement",
            "-c",
            "--constraint",
        }:
            skip_next_for = "option-value"
            continue

        if token.startswith(("--editable=",)):
            editable_target = token.split("=", 1)[1]
            name = _parse_editable_or_direct_name(editable_target)
            if name:
                requirement_names.add(name)
            continue

        if token.startswith(
            (
                "--index-url=",
                "--extra-index-url=",
                "--find-links=",
                "--trusted-host=",
                "--requirement=",
                "--constraint=",
            )
        ):
            continue

        if (
            (token.startswith("-i") and token != "-i")
            or (token.startswith("-f") and token != "-f")
            or token == "--no-index"
        ):
            continue

        if token.startswith("-"):
            continue

        name = _parse_editable_or_direct_name(token)
        if name:
            requirement_names.add(name)

    return frozenset(requirement_names)


def parse_package_install_input(raw_input: str) -> ParsedPackageInput:
    specs: list[str] = []
    requirement_names: set[str] = set()
    normalized = raw_input.strip()
    if not normalized:
        return ParsedPackageInput(specs=(), requirement_names=frozenset())

    for raw_line in normalized.splitlines():
        line = strip_inline_requirement_comment(raw_line)
        if not line:
            continue

        try:
            req = Requirement(line)
        except InvalidRequirement:
            tokens = shlex.split(line)
            if not tokens:
                continue
            specs.extend(tokens)
            requirement_names.update(
                _extract_requirement_names_from_package_tokens(tokens)
            )
            continue

        specs.append(line)
        requirement_names.add(canonicalize_distribution_name(req.name))

    return ParsedPackageInput(
        specs=tuple(specs),
        requirement_names=frozenset(requirement_names),
    )


def _iter_requirement_lines(
    requirements_path: str,
    _visited: set[str] | None = None,
) -> Iterator[str]:
    visited = _visited or set()
    resolved_path = os.path.realpath(requirements_path)
    if resolved_path in visited:
        logger.warning(
            "检测到循环依赖的 requirements 包含: %s，将跳过该文件", resolved_path
        )
        return
    visited.add(resolved_path)

    with open(resolved_path, encoding="utf-8") as f:
        for raw_line in f:
            line = strip_inline_requirement_comment(raw_line)
            if not line:
                continue

            tokens = shlex.split(line)
            if not tokens:
                continue

            nested: str | None = None
            if tokens[0] in {"-r", "--requirement"} and len(tokens) > 1:
                nested = tokens[1]
            elif tokens[0].startswith("--requirement="):
                nested = tokens[0].split("=", 1)[1]

            if nested:
                if not os.path.isabs(nested):
                    nested = os.path.join(os.path.dirname(resolved_path), nested)
                yield from _iter_requirement_lines(nested, _visited=visited)
                continue

            yield line


def iter_requirements(
    requirements_path: str | None = None,
    lines: Iterable[str] | None = None,
) -> Iterator[tuple[str, SpecifierSet | None]]:
    if lines is None:
        if requirements_path is None:
            raise ValueError("Either requirements_path or lines must be provided")
        lines = _iter_requirement_lines(requirements_path)

    for line in lines:
        parsed = _parse_requirement_line(line)
        if parsed is not None:
            yield parsed


def extract_requirement_names(requirements_path: str) -> set[str]:
    try:
        return {
            name for name, _ in iter_requirements(requirements_path=requirements_path)
        }
    except Exception as exc:
        logger.warning("读取依赖文件失败，跳过冲突检测: %s", exc)
        return set()


def get_requirement_check_paths() -> list[str]:
    paths = list(sys.path)
    if is_packaged_desktop_runtime():
        target_site_packages = get_astrbot_site_packages_path()
        if os.path.isdir(target_site_packages):
            paths.insert(0, target_site_packages)
    return paths


def _canonical_distribution_identity(distribution) -> tuple[str | None, str | None]:
    distribution_name = (
        distribution.metadata["Name"] if "Name" in distribution.metadata else None
    )
    if not distribution_name:
        return None, None
    return canonicalize_distribution_name(distribution_name), distribution.version


def collect_installed_distribution_versions(paths: list[str]) -> dict[str, str] | None:
    installed: dict[str, str] = {}
    try:
        for distribution in importlib_metadata.distributions(path=paths):
            distribution_name, version = _canonical_distribution_identity(distribution)
            if not distribution_name or not version:
                continue
            installed.setdefault(distribution_name, version)
    except Exception as exc:
        logger.warning("读取已安装依赖失败，跳过缺失依赖预检查: %s", exc)
        return None
    return installed


def _load_requirement_lines_for_precheck(
    requirements_path: str,
) -> tuple[bool, list[str] | None]:
    try:
        requirement_lines = list(_iter_requirement_lines(requirements_path))
    except Exception as exc:
        logger.warning(
            "预检查缺失依赖失败，将回退到完整安装: %s (%s)",
            requirements_path,
            exc,
        )
        return False, None

    fallback_line = next(
        (
            line
            for line in requirement_lines
            if (
                (
                    line.startswith(("-e ", "--editable ", "--editable="))
                    and "#egg=" not in line
                )
                or (
                    _parse_requirement_line(line) is None
                    and looks_like_direct_reference(line)
                )
            )
        ),
        None,
    )
    if fallback_line is not None:
        logger.warning(
            "预检查缺失依赖失败，将回退到完整安装: unresolved direct reference in %s: %s",
            requirements_path,
            fallback_line,
        )
        return False, None

    return True, requirement_lines


def find_missing_requirements(requirements_path: str) -> set[str] | None:
    can_precheck, requirement_lines = _load_requirement_lines_for_precheck(
        requirements_path
    )
    if not can_precheck or requirement_lines is None:
        return None

    required = list(iter_requirements(lines=requirement_lines))
    if not required:
        return set()

    installed = collect_installed_distribution_versions(get_requirement_check_paths())
    if installed is None:
        return None

    missing: set[str] = set()
    for name, specifier in required:
        installed_version = installed.get(name)
        if not installed_version:
            missing.add(name)
            continue
        if specifier and not _specifier_contains_version(specifier, installed_version):
            missing.add(name)

    return missing


def find_missing_requirements_or_raise(requirements_path: str) -> set[str]:
    missing = find_missing_requirements(requirements_path)
    if missing is None:
        raise RequirementsPrecheckFailed(f"预检查失败: {requirements_path}")
    return missing
