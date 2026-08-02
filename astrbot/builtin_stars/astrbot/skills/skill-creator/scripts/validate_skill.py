"""Validate the structure and frontmatter of an AstrBot Skill."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import yaml

SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def validate_skill(skill_dir: Path) -> tuple[list[str], list[str]]:
    """Validate a Skill directory.

    Args:
        skill_dir: Directory containing the Skill to validate.

    Returns:
        A pair containing validation errors and non-blocking warnings.
    """
    errors: list[str] = []
    warnings: list[str] = []
    skill_dir = skill_dir.expanduser().resolve(strict=False)
    skill_name = skill_dir.name

    if len(skill_name) > 64 or not SKILL_NAME_RE.fullmatch(skill_name):
        errors.append(
            "directory name must be at most 64 characters and use lowercase "
            "letters, digits, and single hyphen separators"
        )

    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        return [*errors, "SKILL.md is missing"], warnings

    try:
        content = skill_md.read_text(encoding="utf-8")
    except UnicodeError:
        return [*errors, "SKILL.md must be valid UTF-8"], warnings

    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return [*errors, "SKILL.md must begin with YAML frontmatter"], warnings

    try:
        frontmatter_end = next(
            index
            for index, line in enumerate(lines[1:], start=1)
            if line.strip() == "---"
        )
    except StopIteration:
        return [*errors, "YAML frontmatter is not closed"], warnings

    try:
        metadata = yaml.safe_load("\n".join(lines[1:frontmatter_end])) or {}
    except yaml.YAMLError as exc:
        return [*errors, f"invalid YAML frontmatter: {exc}"], warnings

    if not isinstance(metadata, dict):
        errors.append("frontmatter must be a YAML mapping")
        metadata = {}

    name = metadata.get("name")
    description = metadata.get("description")
    if name != skill_name:
        errors.append("frontmatter name must match the Skill directory name")
    if not isinstance(description, str) or not description.strip():
        errors.append("frontmatter description must be a non-empty string")

    extra_keys = sorted(set(metadata) - {"name", "description"})
    if extra_keys:
        warnings.append(
            "frontmatter contains optional keys not used for AstrBot discovery: "
            + ", ".join(extra_keys)
        )

    if not "\n".join(lines[frontmatter_end + 1 :]).strip():
        errors.append("SKILL.md body must not be empty")

    extra_docs = [
        name
        for name in ("README.md", "INSTALLATION_GUIDE.md", "QUICK_REFERENCE.md")
        if skill_dir.joinpath(name).exists()
    ]
    if extra_docs:
        warnings.append(
            "remove redundant process documentation: " + ", ".join(extra_docs)
        )

    return errors, warnings


def main() -> int:
    """Run Skill validation and print a concise result.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill_directory", type=Path)
    args = parser.parse_args()

    errors, warnings = validate_skill(args.skill_directory)
    for warning in warnings:
        print(f"warning: {warning}")
    for error in errors:
        print(f"error: {error}")

    if errors:
        return 1
    print(f"valid: {args.skill_directory}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
