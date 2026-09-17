"""Run the real 2^3 image experiment only when production factor flips exist.

The current checkout does not expose independent A, B, and C experiment
switches. This runner therefore refuses to fabricate a matrix and emits an
auditable blocked manifest until each factor is supplied by a real checkout.
"""

from __future__ import annotations

import argparse
import itertools
import json
import subprocess
from pathlib import Path


def git_identity(repo: Path) -> dict[str, str]:
    """Return commit and dirty diff identity for a checkout."""
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True
    ).strip()
    diff = subprocess.check_output(["git", "diff", "--binary"], cwd=repo)
    import hashlib

    return {
        "commit": commit,
        "working_tree_diff_sha256": hashlib.sha256(diff).hexdigest(),
    }


def main() -> int:
    """Validate factor provenance and write a blocked or runnable plan."""
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--baseline-repo", type=Path, required=True)
    parser.add_argument("--candidate-repo", type=Path, required=True)
    parser.add_argument("--factor-entrypoint", type=Path)
    args = parser.parse_args()
    factors = {
        "A": "unavailable: no independent production source-preparation entrypoint supplied",
        "B": "unavailable: no independent production storage/lazy-materialization entrypoint supplied",
        "C": "unavailable: no independent production compression-algorithm entrypoint supplied",
    }
    entrypoint_ok = (
        args.factor_entrypoint is not None and args.factor_entrypoint.is_file()
    )
    plan = {
        "status": "blocked" if not entrypoint_ok else "requires_factor_contract",
        "experiment": "real-2^3-factorial",
        "factors": factors,
        "combinations": ["".join(bits) for bits in itertools.product("0A", repeat=0)],
        "baseline": git_identity(args.baseline_repo),
        "candidate": git_identity(args.candidate_repo),
        "warmup_scope": "sdk_send_only; not warm history",
        "reason": "Do not execute or label combinations until A/B/C independently select real production paths.",
    }
    plan["combinations"] = [
        "".join(bits) for bits in itertools.product("0A", "0B", "0C")
    ]
    args.output.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": plan["status"], "output": str(args.output)}))
    return 0 if plan["status"] == "blocked" else 2


if __name__ == "__main__":
    raise SystemExit(main())
