from astrbot.core.lang import t
#!/usr/bin/env python3
"""
Auto-generate changelog from git commits using LLM.
Usage: python scripts/generate_changelog.py [--version VERSION]
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path


def get_latest_tag():
    """Get the latest git tag."""
    result = subprocess.run(
        ["git", "describe", "--tags", "--abbrev=0"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def get_commits_since_tag(tag):
    """Get all commit messages since the specified tag."""
    result = subprocess.run(
        ["git", "log", f"{tag}..HEAD", "--pretty=format:%H|%s|%b"],
        capture_output=True,
        text=True,
        check=True,
    )
    commits = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split("|", 2)
        if len(parts) >= 2:
            commit_hash = parts[0]
            subject = parts[1]
            body = parts[2] if len(parts) > 2 else ""
            commits.append({"hash": commit_hash[:7], "subject": subject, "body": body})
    return commits


def extract_issue_number(text):
    """Extract issue number from commit message."""
    # Match #1234 or (#1234)
    match = re.search(r"#(\d+)", text)
    return match.group(1) if match else None


def call_llm_for_changelog(commits, version):
    """Call LLM to generate changelog from commits."""
    try:
        # Try to use OpenAI API or other LLM providers
        import openai

        # Build prompt
        commits_text = "\n".join([f"- {c['subject']}" for c in commits])

        prompt = f"""Based on the following git commit messages, generate a changelog document in BOTH Chinese and English.

Commit messages:
{commits_text}

Please organize the changes into these categories:
- 新增 (New Features)
- 修复 (Bug Fixes)
- 优化 (Improvements)
- 其他 (Others)

Format requirements:
1. Start with Chinese version under "## What's Changed"
2. Follow with English version under "## What's Changed (EN)"
3. Use markdown format with proper bullet points
4. Keep descriptions concise and user-friendly
5. If a commit mentions an issue number (#1234), include it in the format ([#1234](https://github.com/AstrBotDevs/AstrBot/issues/1234))

Example format:
## What's Changed

### 新增
- 支持某某功能 ([#1234](https://github.com/AstrBotDevs/AstrBot/issues/1234))

### 修复
- 修复某某问题

## What's Changed (EN)

### New Features
- Add support for something ([#1234](https://github.com/AstrBotDevs/AstrBot/issues/1234))

### Bug Fixes
- Fix something
"""

        client = openai.OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        )

        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4"),
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant that generates well-structured changelogs.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )

        return response.choices[0].message.content

    except ImportError:
        print(
            t("msg-a79937ef")
        )
        return generate_simple_changelog(commits)
    except Exception as e:
        print(t("msg-090bfd36", e=e))
        print(t("msg-a3ac9130"))
        return generate_simple_changelog(commits)


def generate_simple_changelog(commits):
    """Generate a simple changelog without LLM."""
    sections = {
        "feat": ("新增", "New Features", []),
        "fix": ("修复", "Bug Fixes", []),
        "perf": ("优化", "Improvements", []),
        "docs": ("文档", "Documentation", []),
        "refactor": ("重构", "Refactoring", []),
        "test": ("测试", "Tests", []),
        "chore": ("其他", "Chore", []),
        "other": ("其他", "Others", []),
    }

    # Categorize commits by conventional commit type
    for commit in commits:
        subject = commit["subject"]
        issue_num = extract_issue_number(subject)
        issue_link = (
            f" ([#{issue_num}](https://github.com/AstrBotDevs/AstrBot/issues/{issue_num}))"
            if issue_num
            else ""
        )

        # Detect conventional commit type
        matched = False
        for prefix in ["feat", "fix", "perf", "docs", "refactor", "test", "chore"]:
            if subject.lower().startswith(f"{prefix}:") or subject.lower().startswith(
                f"{prefix}("
            ):
                # Remove prefix for display
                clean_subject = re.sub(
                    r"^[a-z]+(\([^)]+\))?:\s*", "", subject, flags=re.IGNORECASE
                )
                sections[prefix][2].append(f"- {clean_subject}{issue_link}")
                matched = True
                break

        if not matched:
            sections["other"][2].append(f"- {subject}{issue_link}")

    # Build Chinese version
    changelog_zh = "## What's Changed\n\n"
    for section_key in ["feat", "fix", "perf", "docs", "refactor", "test", "other"]:
        zh_title, _, items = sections[section_key]
        if items:
            changelog_zh += f"### {zh_title}\n\n"
            changelog_zh += "\n".join(items) + "\n\n"

    # Build English version
    changelog_en = "## What's Changed (EN)\n\n"
    for section_key in ["feat", "fix", "perf", "docs", "refactor", "test", "other"]:
        _, en_title, items = sections[section_key]
        if items:
            changelog_en += f"### {en_title}\n\n"
            changelog_en += "\n".join(items) + "\n\n"

    return changelog_zh + changelog_en


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate changelog from git commits")
    parser.add_argument(
        "--version", help="Version number for the changelog (e.g., v4.13.3)"
    )
    parser.add_argument(
        "--use-llm",
        action="store_true",
        help="Use LLM to generate changelog (requires OpenAI API key)",
    )
    args = parser.parse_args()

    # Get latest tag
    try:
        latest_tag = get_latest_tag()
        print(t("msg-6f1011c5", latest_tag=latest_tag))
    except subprocess.CalledProcessError:
        print(t("msg-8c7f64d7"))
        sys.exit(1)

    # Get commits since tag
    commits = get_commits_since_tag(latest_tag)
    if not commits:
        print(t("msg-a89fa0eb", latest_tag=latest_tag))
        sys.exit(0)

    print(t("msg-846ebecf", res=len(commits), latest_tag=latest_tag))

    # Determine version
    if args.version:
        version = args.version
    else:
        # Auto-increment patch version
        match = re.match(r"v(\d+)\.(\d+)\.(\d+)", latest_tag)
        if match:
            major, minor, patch = map(int, match.groups())
            version = f"v{major}.{minor}.{patch + 1}"
        else:
            print(t("msg-9ad686af", latest_tag=latest_tag))
            version = "vX.X.X"

    print(t("msg-f5d43a54", version=version))

    # Generate changelog
    if args.use_llm:
        changelog_content = call_llm_for_changelog(commits, version)
    else:
        changelog_content = generate_simple_changelog(commits)

    # Save to file
    changelog_dir = Path(__file__).parent.parent / "changelogs"
    changelog_dir.mkdir(exist_ok=True)
    changelog_file = changelog_dir / f"{version}.md"

    with open(changelog_file, "w", encoding="utf-8") as f:
        f.write(changelog_content)

    print(t("msg-e54756e8", changelog_file=changelog_file))
    print(t("msg-82be6c98"))
    print("=" * 80)
    print(t("msg-321ac5b1", changelog_content=changelog_content))
    print("=" * 80)


if __name__ == "__main__":
    main()
