from __future__ import annotations

import argparse
import sys
from pathlib import Path

from os_core import EngineeringOSError, load_yaml, validate_task


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate one Codex Engineering OS Task Contract.")
    parser.add_argument("task", type=Path)
    parser.add_argument("--repo-root", type=Path)
    args = parser.parse_args()

    repo_root = (args.repo_root or Path(__file__).resolve().parents[2]).resolve()
    task_path = args.task if args.task.is_absolute() else repo_root / args.task
    try:
        task = load_yaml(task_path)
        risk_rules = load_yaml(repo_root / "governance/RISK_RULES.yaml")
        gate_policy = load_yaml(repo_root / "governance/GATE_POLICY.yaml")
        errors = validate_task(task, risk_rules, gate_policy, repo_root)
    except EngineeringOSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"PASS: {task['id']} contract v{task['contract_version']} ({task['status']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
