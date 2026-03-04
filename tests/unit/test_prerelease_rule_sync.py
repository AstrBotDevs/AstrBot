from pathlib import Path
import re

from astrbot.core.zip_updator import PRERELEASE_TAG_REGEX


def test_prerelease_rule_is_synced_with_dashboard():
    repo_root = Path(__file__).resolve().parents[2]
    vue_path = repo_root / "dashboard/src/layouts/full/vertical-header/VerticalHeader.vue"
    content = vue_path.read_text(encoding="utf-8")

    match = re.search(r"const PRE_RELEASE_TAG_REGEX = /(.+?)/i;", content)
    assert match is not None
    assert match.group(1) == PRERELEASE_TAG_REGEX.pattern
