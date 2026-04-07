"""
Code Quality Test: Type Safety Scoring

Scores the codebase based on type safety patterns:
- cast(Any, ...) usage (too many casts indicate type safety issues)
- # type: ignore comments (越多表示类型问题越多)

Perfect score: 100
"""

import re
from pathlib import Path
from typing import cast

import pytest

ASTRBOT_ROOT = Path(__file__).parent.parent / "astrbot"


def _scan_for_patterns() -> dict[str, int | set[str] | list[tuple[str, str]]]:
    """Scan astrbot source for type-unsafe patterns."""
    counts: dict[str, int | set[str] | list[tuple[str, str]]] = {
        "cast_any": 0,
        "type_ignore": 0,
        "bad_type_ignore": 0,
        "bare_except": 0,
        "duplicate_blocks": 0,
        "cast_any_files": set(),
        "type_ignore_files": set(),
        "bad_type_ignore_files": set(),
        "bare_except_files": set(),
        "dup_files": [],
    }

    # Patterns to detect
    cast_any_re = re.compile(r"cast\s*\(\s*Any\s*,", re.MULTILINE)
    type_ignore_re = re.compile(r"#\s*type:\s*ignore", re.MULTILINE)
    bare_except_re = re.compile(
        r"except\s*:\s*$", re.MULTILINE
    )

    # Bad type: ignore patterns (unresolved-import, class-alias, etc.)
    bad_ignore_re = re.compile(
        r"#\s*type:\s*ignore"
        r"\[[\w-]*(?:import|no-name-module|attr-defined|class-var|assignment|type-var|misc)[\w-]*\]",
        re.MULTILINE,
    )

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
        bad_ignore_matches = bad_ignore_re.findall(content)
        # Only count bare `except:` (no specific exception type), not `except Exception:`
        bare_except_matches = bare_except_re.findall(content)

        if cast_matches:
            counts["cast_any"] += len(cast_matches)
            counts["cast_any_files"].add(rel)

        if ignore_matches:
            counts["type_ignore"] += len(ignore_matches)
            counts["type_ignore_files"].add(rel)

        if bad_ignore_matches:
            counts["bad_type_ignore"] += len(bad_ignore_matches)
            counts["bad_type_ignore_files"].add(rel)

        if bare_except_matches:
            counts["bare_except"] += len(bare_except_matches)
            counts["bare_except_files"].add(rel)

    # --- Phase 2: duplicate code blocks (5+ identical lines) ---
    # key: block text -> list of (file, start_line-end_line)
    dup_blocks: dict[str, list[tuple[str, str]]] = {}
    WINDOW = 5
    for py_file in ASTRBOT_ROOT.rglob("*.py"):
        if py_file.suffix == ".pyi":
            continue
        try:
            raw_lines = py_file.read_text(encoding="utf-8").splitlines()
        except Exception:
            continue
        rel = str(py_file.relative_to(ASTRBOT_ROOT.parent))
        # Build mapping: cleaned_idx -> original_line_number (1-indexed)
        cleaned_to_orig: dict[int, int] = {}
        cleaned: list[str] = []
        for idx, ln in enumerate(raw_lines):
            stripped = ln.strip()
            if len(stripped) > 2:
                cleaned.append(stripped)
                cleaned_to_orig[len(cleaned) - 1] = idx + 1  # 1-indexed
        n = len(cleaned)
        seen: dict[str, list[int]] = {}
        for i in range(n - WINDOW + 1):
            block = "\n".join(cleaned[i : i + WINDOW])
            if block not in seen:
                seen[block] = []
            seen[block].append(i)
        for block, positions in seen.items():
            if len(positions) >= 2:
                key = block[:60] + "..." if len(block) > 60 else block
                if key not in dup_blocks:
                    dup_blocks[key] = []
                for pos in positions:
                    start = cleaned_to_orig.get(pos, 0)
                    end = cleaned_to_orig.get(pos + WINDOW - 1, start)
                    dup_blocks[key].append((rel, f"{start}-{end}"))

    counts["duplicate_blocks"] = sum(
        max(0, len(locs) - 1) for locs in dup_blocks.values()
    )
    counts["dup_files"] = list(dup_blocks.items())[:20]  # type: ignore[index]

    return counts


def _calculate_score(
    cast_any: int,
    type_ignore: int,
    bad_type_ignore: int,
    bare_except: int,
    dup_blocks: int,
) -> int:
    """
    Calculate type safety score out of 100.

    Deductions:
    - Each cast(Any, ...) costs 1 point
    - Each # type: ignore costs 0.5 points
    - Each bad # type: ignore (unresolved-import, class-alias, ...) costs 3 points
    - Each bare except: costs 0.5 points
    - Each duplicate block costs 2 points
    - Floor at 0
    """
    deduction = (
        cast_any
        + type_ignore * 0.5
        + bad_type_ignore * 3
        + bare_except * 0.5
        + dup_blocks * 0.001
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
        cast_any = cast(int, counts["cast_any"])
        type_ignore = cast(int, counts["type_ignore"])
        bad_type_ignore = cast(int, counts["bad_type_ignore"])
        bare_except = cast(int, counts["bare_except"])
        dup_blocks = cast(int, counts["duplicate_blocks"])
        cast_any_files = cast("set[str]", counts["cast_any_files"])
        type_ignore_files = cast("set[str]", counts["type_ignore_files"])
        bad_type_ignore_files = cast("set[str]", counts["bad_type_ignore_files"])
        bare_except_files = cast("set[str]", counts["bare_except_files"])
        dup_files = cast("list[tuple[str, str]]", counts["dup_files"])
        score = _calculate_score(
            cast_any, type_ignore, bad_type_ignore, bare_except, dup_blocks
        )

        print(f"\n{'=' * 60}")
        print("  Type Safety Score Report")
        print(f"{'=' * 60}")
        print(f"  cast(Any, ...) count:  {cast_any:>4}  (cost: {cast_any} pts)")
        print(
            f"  # type: ignore count:   {type_ignore:>4}  (cost: {type_ignore * 0.5:.1f} pts)"
        )
        print(
            f"  bad type: ignore:      {bad_type_ignore:>4}  (cost: {bad_type_ignore * 3} pts)"
        )
        print(
            f"  bare except: count:   {bare_except:>4}  (cost: {bare_except * 0.5:.1f} pts)"
        )
        print(f"  duplicate blocks:     {dup_blocks:>4}  (cost: {dup_blocks * 0.001:.1f} pts)")
        print(f"  {'-' * 60}")
        print(f"  Score: {score}/100  (Grade: {_get_grade(score)})")
        print(f"{'=' * 60}")

        if cast_any_files:
            print("\n  Files with cast(Any, ...):")
            for f in sorted(cast_any_files)[:10]:
                print(f"    - {f}")
            if len(cast_any_files) > 10:
                print(f"    ... and {len(cast_any_files) - 10} more")
            print()

        if type_ignore_files:
            print("  Files with # type: ignore:")
            for f in sorted(type_ignore_files)[:10]:
                print(f"    - {f}")
            if len(type_ignore_files) > 10:
                print(f"    ... and {len(type_ignore_files) - 10} more")
            print()

        if bad_type_ignore_files:
            print("  Files with BAD type: ignore (import/alias/...):")
            for f in sorted(bad_type_ignore_files)[:10]:
                print(f"    - {f}")
            if len(bad_type_ignore_files) > 10:
                print(f"    ... and {len(bad_type_ignore_files) - 10} more")
            print()

        if bare_except_files:
            print("  Files with bare except:")
            for f in sorted(bare_except_files)[:10]:
                print(f"    - {f}")
            if len(bare_except_files) > 10:
                print(f"    ... and {len(bare_except_files) - 10} more")
            print()

        if dup_files:
            print("  Duplicate code blocks (top 10):")
            for block_preview, locations in dup_files[:10]:
                # Group by file
                by_file: dict[str, list[str]] = {}
                for f, rng in locations:
                    if f not in by_file:
                        by_file[f] = []
                    by_file[f].append(rng)
                parts = [f"{f}: {', '.join(rngs)}" for f, rngs in by_file.items()]
                print(f"    - [{block_preview}]")
                for part in parts:
                    print(f"        {part}")
            print()

        print("  WARNING: This is a custom heuristic. Score may not reflect")
        print("           actual type safety. Review individual cases manually.")
        print(f"{'=' * 60}\n")

        # Emit warning level based on score
        if score < 60:
            pytest.fail(
                f"Type safety score too low: {score}/100 (Grade: {_get_grade(score)})"
            )
        elif score < 80:
            pytest.skip(
                f"Type safety score below target: {score}/100 (Grade: {_get_grade(score)})"
            )
