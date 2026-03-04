import re
from pathlib import Path

from astrbot.core.zip_updator import PRERELEASE_TAG_REGEX


def test_prerelease_rule_is_synced_with_dashboard():
    repo_root = Path(__file__).resolve().parents[2]
    vue_path = (
        repo_root / "dashboard/src/layouts/full/vertical-header/VerticalHeader.vue"
    )
    content = vue_path.read_text(encoding="utf-8")

    match = re.search(
        r"const\s+PRE_RELEASE_TAG_REGEX\s*=\s*/(.+?)/([a-z]*)\s*;?",
        content,
    )
    assert match is not None
    vue_pattern, vue_flags = match.groups()
    assert vue_pattern == PRERELEASE_TAG_REGEX.pattern
    assert ("i" in vue_flags) == bool(PRERELEASE_TAG_REGEX.flags & re.IGNORECASE)


def test_prerelease_rule_matches_expected_examples():
    prerelease_tags = (
        "v1.2.3-alpha.1",
        "v1.2.3-beta",
        "v1.2.3-rc1",
        "v1.2.3-dev",
        "v1.2.3-nightly",
        "v1.2.3-pre",
        "v1.2.3-preview",
        "v1.2.3-ALPHA",
        "v1.2.3-Beta.1",
        "v1.2.3-NIGHTLY",
    )
    stable_tags = (
        "v1.2.3",
        "v1.2.3+build.1",
        "v1.2.3-release",
        "v1.2.3-alphaish",
        "v1.2.3-previewed",
    )

    for tag in prerelease_tags:
        assert PRERELEASE_TAG_REGEX.search(tag) is not None

    for tag in stable_tags:
        assert PRERELEASE_TAG_REGEX.search(tag) is None
