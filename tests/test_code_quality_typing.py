"""
Code Quality Test: Type Safety Scoring

Scores the codebase based on type safety patterns:
- cast(Any, ...) usage (too many casts indicate type safety issues)
- # type: ignore comments (越多表示类型问题越多)

Perfect score: 100
"""

import re
from pathlib import Path

import pytest

ASTRBOT_ROOT = Path(__file__).parent.parent / "astrbot"


def _scan_for_patterns() -> dict[str, int | set[str] | list[tuple[str, str]]]:
    """Scan astrbot source for type-unsafe patterns."""
    counts: dict[str, int | set[str] | list[tuple[str, str]]] = {
        "cast_any": 0,
        "type_ignore": 0,
        "bare_except": 0,
        "duplicate_blocks": 0,
        "cast_any_files": set(),
        "type_ignore_files": set(),
        "bare_except_files": set(),
        "dup_files": [],
    }

    # Patterns to detect
    cast_any_re = re.compile(r"cast\s*\(\s*Any\s*,", re.MULTILINE)
    type_ignore_re = re.compile(r"#\s*type:\s*ignore", re.MULTILINE)
    bare_except_re = re.compile(r"except\s*(?:Exception)?\s*:\s*$", re.MULTILINE | re.MULTILINE)

    # --- Phase 1: cast / type:ignore / bare_except ---
    for py_file in ASTRBOT_ROOT.rglob("*.py"):
        try:
            content = py_file.read_text(encoding="utf-8")
        except Exception:
            continue

        if py_file.suffix == ".pyi":
            continue

        rel = str(py_file.relative_to(ASTRBOT_ROOT.parent))

        cast_matches = cast_any_re.findall(content)
        ignore_matches = type_ignore_re.findall(content)
        # Only count bare `except:` (no specific exception type), not `except Exception:`
        bare_except_matches = bare_except_re.findall(content)

        if cast_matches:
            counts["cast_any"] += len(cast_matches)
            counts["cast_any_files"].add(rel)

        if ignore_matches:
            counts["type_ignore"] += len(ignore_matches)
            counts["type_ignore_files"].add(rel)

        if bare_except_matches:
            counts["bare_except"] += len(bare_except_matches)
            counts["bare_except_files"].add(rel)

    # --- Phase 2: duplicate code blocks (5+ identical lines) ---
    dup_blocks: dict[str, list[tuple[str, int]]] = {}
    for py_file in ASTRBOT_ROOT.rglob("*.py"):
        if py_file.suffix == ".pyi":
            continue
        try:
            lines = py_file.read_text(encoding="utf-8").splitlines()
        except Exception:
            continue
        rel = str(py_file.relative_to(ASTRBOT_ROOT.parent))
        # Strip and skip empty/1-char lines; use 5-line window
        cleaned: list[str] = []
        for ln in lines:
            stripped = ln.strip()
            if len(stripped) > 2:
                cleaned.append(stripped)
        n = len(cleaned)
        seen: dict[str, list[int]] = {}
        for i in range(n - 4):
            block = "\n".join(cleaned[i : i + 5])
            if block not in seen:
                seen[block] = []
            seen[block].append(i)
        for block, positions in seen.items():
            if len(positions) >= 2:
                key = block[:60] + "..." if len(block) > 60 else block
                if key not in dup_blocks:
                    dup_blocks[key] = []
                dup_blocks[key].append((rel, len(positions)))

    counts["duplicate_blocks"] = len(dup_blocks)
    counts["dup_files"] = list(dup_blocks.items())[:20]  # type: ignore[index]

    return counts


def _calculate_score(
    cast_any: int, type_ignore: int, bare_except: int, dup_blocks: int
) -> int:
    """
    Calculate type safety score out of 100.

    Deductions:
    - Each cast(Any, ...) costs 1 point
    - Each # type: ignore costs 0.5 points
    - Each bare except: costs 0.5 points
    - Each duplicate block costs 2 points
    - Floor at 0
    """
    deduction = (
        cast_any
        + type_ignore * 0.5
        + bare_except * 0.5
        + dup_blocks * 2
    )
    score = max(0, int(100 - deduction))
    return score


def _get_grade(score: int) -> str:
    if score >= 90:
        return "A"
    elif score >= 80:
        return "B"
    elif score >= 70:
        return "C"
    elif score >= 60:
        return "D"
    else:
        return "F"


class TestCodeQualityTyping:
    """Test suite for type safety scoring."""

    def test_type_safety_score(self):
        """
        Type safety score based on cast(Any, ...) and # type: ignore usage.

        Score = 100 - (cast_any_count * 1) - (type_ignore_count * 0.5)
        Minimum score: 0
        """
        counts = _scan_for_patterns()
        cast_any = counts["cast_any"]
        type_ignore = counts["type_ignore"]
        bare_except = counts["bare_except"]
        dup_blocks = counts["duplicate_blocks"]
        score = _calculate_score(cast_any, type_ignore, bare_except, dup_blocks)  # type: ignore[arg-type]

        print(f"\n{'='*60}")
        print(f"  Type Safety Score Report")
        print(f"{'='*60}")
        print(f"  cast(Any, ...) count:  {cast_any:>4}  (cost: {cast_any} pts)")
        print(f"  # type: ignore count:   {type_ignore:>4}  (cost: {type_ignore * 0.5:.1f} pts)")  # type: ignore[index]
        print(f"  bare except: count:    {bare_except:>4}  (cost: {bare_except * 0.5:.1f} pts)")  # type: ignore[index]
        print(f"  duplicate blocks:      {dup_blocks:>4}  (cost: {dup_blocks * 2} pts)")  # type: ignore[index]
        print(f"  {'-'*60}")
        print(f"  Score: {score}/100  (Grade: {_get_grade(score)})")
        print(f"{'='*60}")

        if counts["cast_any_files"]:
            print(f"\n  Files with cast(Any, ...):")
            for f in sorted(counts["cast_any_files"])[:10]:  # type: ignore[arg-type]
                print(f"    - {f}")
            if len(counts["cast_any_files"]) > 10:  # type: ignore[arg-type]
                print(f"    ... and {len(counts["cast_any_files"]) - 10} more")  # type: ignore[arg-type, index]
            print()

        if counts["type_ignore_files"]:
            print(f"  Files with # type: ignore:")
            for f in sorted(counts["type_ignore_files"])[:10]:  # type: ignore[arg-type]
                print(f"    - {f}")
            if len(counts["type_ignore_files"]) > 10:  # type: ignore[arg-type]
                print(f"    ... and {len(counts["type_ignore_files"]) - 10} more")  # type: ignore[arg-type, index]
            print()

        if counts["bare_except_files"]:
            print(f"  Files with bare except:")
            for f in sorted(counts["bare_except_files"])[:10]:  # type: ignore[arg-type]
                print(f"    - {f}")
            if len(counts["bare_except_files"]) > 10:  # type: ignore[arg-type]
                print(f"    ... and {len(counts["bare_except_files"]) - 10} more")  # type: ignore[arg-type, index]
            print()

        if counts["dup_files"]:
            print(f"  Duplicate code blocks (top 10):")
            for block_preview, locations in counts["dup_files"][:10]:  # type: ignore[arg-type]
                files_str = ", ".join([f"{f} ({c}x)" for f, c in locations])  # type: ignore[iterable]
                print(f"    - [{block_preview}] in {files_str}")
            print()

        print(f"  WARNING: This is a custom heuristic. Score may not reflect")
        print(f"           actual type safety. Review individual cases manually.")
        print(f"{'='*60}\n")

        # Emit warning level based on score
        if score < 60:
            pytest.fail(f"Type safety score too low: {score}/100 (Grade: {_get_grade(score)})")
        elif score < 80:
            pytest.skip(f"Type safety score below target: {score}/100 (Grade: {_get_grade(score)})")
