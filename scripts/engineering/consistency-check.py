from __future__ import annotations

import argparse
import sys
from pathlib import Path

from os_core import (
    EngineeringOSError,
    changed_files,
    load_yaml,
    normalize_path,
    validate_consistency,
    yaml_at_ref,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check task scope, governance protection, and state transition.")
    parser.add_argument("task", type=Path)
    parser.add_argument("--base-ref", required=True)
    parser.add_argument("--head-ref", default="HEAD")
    parser.add_argument("--repo-root", type=Path)
    args = parser.parse_args()

    repo_root = (args.repo_root or Path(__file__).resolve().parents[2]).resolve()
    task_path = args.task if args.task.is_absolute() else repo_root / args.task
    relative_task = normalize_path(task_path.resolve().relative_to(repo_root))
    try:
        task = load_yaml(task_path)
        files = changed_files(repo_root, args.base_ref, args.head_ref)
        old_task = yaml_at_ref(repo_root, args.base_ref, relative_task)
        errors = validate_consistency(task, files, old_task)
    except (EngineeringOSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"PASS: {task['id']} scope and transition are consistent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
