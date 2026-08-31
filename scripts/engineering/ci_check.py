from __future__ import annotations

import argparse
import sys
from pathlib import Path

from os_core import (
    EngineeringOSError,
    changed_files,
    load_yaml,
    validate_consistency,
    validate_task,
    yaml_at_ref,
)


CONTRACT_SEMANTIC_FIELDS = (
    "id",
    "kind",
    "goal",
    "current_behavior",
    "expected_behavior",
    "non_goals",
    "invariants",
    "acceptance_criteria",
    "open_questions",
    "scope",
    "change_impact",
    "risk",
    "technical_direction",
    "execution_plan",
    "dispatch",
)


def task_files(repo_root: Path) -> list[Path]:
    return sorted(
        path
        for path in (repo_root / "docs/engineering/tasks").glob("T*.yaml")
        if path.name != "TEMPLATE.yaml"
    )


def is_lifecycle_bookkeeping(path: str) -> bool:
    return (
        path == "docs/engineering/HANDOFF.md"
        or path.startswith("docs/engineering/evidence/")
        or (path.startswith("docs/engineering/tasks/T") and path.endswith(".yaml"))
    )


def validate_contract_semantics(task: dict, old_task: dict | None) -> list[str]:
    if old_task is None or task.get("contract_version") != old_task.get("contract_version"):
        return []
    changed = [field for field in CONTRACT_SEMANTIC_FIELDS if task.get(field) != old_task.get(field)]
    if not changed:
        return []
    return [
        "Contract semantics changed without incrementing contract_version: "
        + ", ".join(changed)
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="GitHub CI entry point for Engineering OS checks.")
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument("--base-ref")
    parser.add_argument("--head-ref", default="HEAD")
    args = parser.parse_args()
    repo_root = (args.repo_root or Path(__file__).resolve().parents[2]).resolve()

    try:
        risk_rules = load_yaml(repo_root / "governance/RISK_RULES.yaml")
        gate_policy = load_yaml(repo_root / "governance/GATE_POLICY.yaml")
        tasks = task_files(repo_root)
        errors: list[str] = []
        for path in tasks:
            task = load_yaml(path)
            errors.extend(f"{path.name}: {error}" for error in validate_task(task, risk_rules, gate_policy, repo_root))

        if args.base_ref:
            files = changed_files(repo_root, args.base_ref, args.head_ref)
            changed_tasks = [path for path in files if path.startswith("docs/engineering/tasks/T") and path.endswith(".yaml")]
            if files and len(changed_tasks) != 1:
                errors.append("Each pull request must change exactly one formal Task Contract")
            elif changed_tasks:
                task_path = repo_root / changed_tasks[0]
                task = load_yaml(task_path)
                old_task = yaml_at_ref(repo_root, args.base_ref, changed_tasks[0])
                errors.extend(validate_consistency(task, files, old_task))
                errors.extend(validate_contract_semantics(task, old_task))
                if any(not is_lifecycle_bookkeeping(path) for path in files) and task.get("status") != "MERGE_READY":
                    errors.append(
                        "Implementation-substantive pull requests require Task Contract status "
                        f"MERGE_READY; found {task.get('status')}"
                    )
    except EngineeringOSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"PASS: validated {len(tasks)} formal task contract(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
