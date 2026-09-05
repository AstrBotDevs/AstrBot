"""Initialize a minimal AstrBot Skill directory."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
RESOURCE_DIRS = {"scripts", "references", "assets"}


def parse_resources(value: str) -> list[str]:
    """Parse and validate a comma-separated resource directory list.

    Args:
        value: Comma-separated resource directory names.

    Returns:
        Deduplicated resource directory names in input order.

    Raises:
        argparse.ArgumentTypeError: If an unsupported directory is requested.
    """
    resources = list(
        dict.fromkeys(item.strip() for item in value.split(",") if item.strip())
    )
    invalid = [item for item in resources if item not in RESOURCE_DIRS]
    if invalid:
        choices = ", ".join(sorted(RESOURCE_DIRS))
        raise argparse.ArgumentTypeError(
            f"Unsupported resource directory: {', '.join(invalid)}. Choose from: {choices}."
        )
    return resources


def main() -> int:
    """Create a Skill folder with frontmatter and requested resource directories.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", help="Lowercase hyphenated Skill name.")
    parser.add_argument(
        "--path",
        required=True,
        type=Path,
        help="Parent directory that will contain the Skill folder.",
    )
    parser.add_argument(
        "--description",
        required=True,
        help="What the Skill does and when it should trigger.",
    )
    parser.add_argument(
        "--resources",
        default=[],
        type=parse_resources,
        help="Optional comma-separated list: scripts,references,assets.",
    )
    args = parser.parse_args()

    if len(args.name) > 64 or not SKILL_NAME_RE.fullmatch(args.name):
        parser.error(
            "name must be at most 64 characters and contain only lowercase letters, "
            "digits, and single hyphen separators"
        )

    description = args.description.strip()
    if not description:
        parser.error("description must not be empty")

    skill_dir = args.path.expanduser().resolve(strict=False) / args.name
    if skill_dir.exists():
        parser.error(f"target already exists: {skill_dir}")

    skill_dir.mkdir(parents=True)
    for resource in args.resources:
        skill_dir.joinpath(resource).mkdir()

    title = " ".join(part.capitalize() for part in args.name.split("-"))
    quoted_description = json.dumps(description, ensure_ascii=False)
    skill_dir.joinpath("SKILL.md").write_text(
        "---\n"
        f"name: {args.name}\n"
        f"description: {quoted_description}\n"
        "---\n\n"
        f"# {title}\n\n"
        "Describe the workflow as direct, actionable instructions.\n",
        encoding="utf-8",
    )
    print(skill_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
