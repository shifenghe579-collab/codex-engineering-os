from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any

from os_core import (
    MAIN_STATES,
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

MERGE_READY_INDEX = MAIN_STATES.index("MERGE_READY")
MERGED_INDEX = MAIN_STATES.index("MERGED")
READY_INDEX = MAIN_STATES.index("READY")


def task_files(repo_root: Path) -> list[Path]:
    return sorted(
        path
        for path in (repo_root / "docs/engineering/tasks").glob("T*.yaml")
        if path.name != "TEMPLATE.yaml"
    )


def _git(repo_root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise EngineeringOSError(f"git {' '.join(args)} failed: {detail}")
    return result


def resolve_commit(repo_root: Path, ref: str, label: str) -> str:
    result = _git(repo_root, "rev-parse", "--verify", f"{ref}^{{commit}}", check=False)
    if result.returncode != 0:
        raise EngineeringOSError(
            f"Required {label} commit is unavailable: {ref}; fetch complete, non-shallow history"
        )
    return result.stdout.strip()


def is_ancestor(repo_root: Path, ancestor: str, descendant: str) -> bool:
    result = _git(repo_root, "merge-base", "--is-ancestor", ancestor, descendant, check=False)
    if result.returncode not in {0, 1}:
        detail = result.stderr.strip() or result.stdout.strip()
        raise EngineeringOSError(
            f"Cannot determine Git ancestry for {ancestor} -> {descendant}: {detail}"
        )
    return result.returncode == 0


def paths_at_ref(repo_root: Path, ref: str, prefix: str) -> list[str]:
    result = _git(repo_root, "ls-tree", "-r", "--name-only", ref, "--", prefix)
    return [line.replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def task_paths_at_ref(repo_root: Path, ref: str) -> list[str]:
    return sorted(
        path
        for path in paths_at_ref(repo_root, ref, "docs/engineering/tasks")
        if path.startswith("docs/engineering/tasks/T")
        and path.endswith(".yaml")
        and not path.endswith("/TEMPLATE.yaml")
    )


def blob_oid(repo_root: Path, ref: str, path: str) -> str | None:
    result = _git(repo_root, "rev-parse", "--verify", f"{ref}:{path}", check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def is_task_recording_path(path: str, task_id: str) -> bool:
    return (
        path == "docs/engineering/HANDOFF.md"
        or path == f"docs/engineering/tasks/{task_id}.yaml"
        or path.startswith(f"docs/engineering/evidence/{task_id}/")
    )


def is_lifecycle_path(path: str, task_id: str) -> bool:
    return path in {
        "docs/engineering/HANDOFF.md",
        f"docs/engineering/tasks/{task_id}.yaml",
    }


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


def validate_evidence_refs_at_ref(
    repo_root: Path,
    task: dict[str, Any],
    head_ref: str,
) -> list[str]:
    errors: list[str] = []
    implementation_sha = task.get("git", {}).get("implementation_sha")
    candidate_sha = task.get("git", {}).get("integration_candidate_sha")
    for ref in task.get("evidence_refs", []):
        if not isinstance(ref, dict):
            errors.append("Each evidence_refs entry must be a mapping")
            continue
        path = ref.get("path")
        if not isinstance(path, str):
            errors.append("Evidence reference path must be text")
            continue
        evidence = yaml_at_ref(repo_root, head_ref, path)
        if evidence is None:
            errors.append(f"Evidence file does not exist at explicit head {head_ref}: {path}")
            continue
        if evidence.get("task") != task.get("id"):
            errors.append(f"Evidence {path} belongs to a different task")
        if evidence.get("contract_version") != task.get("contract_version"):
            errors.append(f"Evidence {path} uses a different contract version")
        expected_sha = candidate_sha if ref.get("type") in {"integration", "release"} else implementation_sha
        if expected_sha and evidence.get("subject_sha") != expected_sha:
            errors.append(f"Evidence {path} subject SHA does not match {expected_sha}")
        if ref.get("subject_sha") != evidence.get("subject_sha"):
            errors.append(f"Evidence reference SHA disagrees with {path}")
    return errors


def _added_or_unchanged(old: Any, new: Any) -> bool:
    return old is None and new is not None or old == new


def _appended_without_rewrite(old: Any, new: Any) -> bool:
    return isinstance(old, list) and isinstance(new, list) and new[: len(old)] == old


def validate_authorization_snapshot(
    repo_root: Path,
    task_path: str,
    final_task: dict[str, Any],
    subject_sha: str,
    head_sha: str,
) -> list[str]:
    errors: list[str] = []
    task_id = str(final_task.get("id"))
    subject_task = yaml_at_ref(repo_root, subject_sha, task_path)
    if subject_task is None:
        return [f"Authorization SHA {subject_sha} does not contain {task_path}"]
    if subject_task.get("id") != task_id:
        errors.append(f"Authorization SHA {subject_sha} contains a different Task id")
    if subject_task.get("contract_version") != final_task.get("contract_version"):
        errors.append(f"Authorization SHA {subject_sha} uses a different contract version")

    allowed_top_level = {"status", "git", "approvals", "evidence_refs"}
    frozen_changes = [
        field
        for field in sorted((set(subject_task) | set(final_task)) - allowed_top_level)
        if subject_task.get(field) != final_task.get(field)
    ]
    if frozen_changes:
        errors.append(
            f"Authorization snapshot at {subject_sha} changed frozen fields: "
            + ", ".join(frozen_changes)
        )

    subject_status = subject_task.get("status")
    if (
        subject_status not in MAIN_STATES
        or MAIN_STATES.index(subject_status) < READY_INDEX
        or MAIN_STATES.index(subject_status) > MERGE_READY_INDEX
        or final_task.get("status") != "MERGE_READY"
    ):
        errors.append(
            f"Status is not monotonic from authorization SHA {subject_sha} to MERGE_READY: "
            f"{subject_status} -> {final_task.get('status')}"
        )

    subject_git = subject_task.get("git") if isinstance(subject_task.get("git"), dict) else {}
    final_git = final_task.get("git") if isinstance(final_task.get("git"), dict) else {}
    expected_git_fields = {"base_sha", "implementation_sha", "integration_candidate_sha"}
    if set(subject_git) != expected_git_fields or set(final_git) != expected_git_fields:
        errors.append(f"Authorization SHA {subject_sha} changes the Git recording shape")
    if subject_git.get("base_sha") != final_git.get("base_sha"):
        errors.append(f"Authorization SHA {subject_sha} has a different git.base_sha")
    for field in ("implementation_sha", "integration_candidate_sha"):
        if not _added_or_unchanged(subject_git.get(field), final_git.get(field)):
            errors.append(f"{field} changed non-monotonically after authorization SHA {subject_sha}")

    subject_approvals = (
        subject_task.get("approvals") if isinstance(subject_task.get("approvals"), dict) else {}
    )
    final_approvals = final_task.get("approvals") if isinstance(final_task.get("approvals"), dict) else {}
    if set(subject_approvals) != set(final_approvals):
        errors.append(f"Authorization SHA {subject_sha} changes the approval recording shape")
    for field in ("requirement", "architecture", "risk"):
        if subject_approvals.get(field) != final_approvals.get(field):
            errors.append(f"{field} approval changed after authorization SHA {subject_sha}")
    for field in ("review", "acceptance"):
        if not _added_or_unchanged(subject_approvals.get(field), final_approvals.get(field)):
            errors.append(f"{field} approval changed non-monotonically after authorization SHA {subject_sha}")

    subject_refs = subject_task.get("evidence_refs")
    final_refs = final_task.get("evidence_refs")
    if not _appended_without_rewrite(subject_refs, final_refs):
        errors.append(f"Evidence references were rewritten after authorization SHA {subject_sha}")

    evidence_prefix = f"docs/engineering/evidence/{task_id}"
    for path in paths_at_ref(repo_root, subject_sha, evidence_prefix):
        if blob_oid(repo_root, subject_sha, path) != blob_oid(repo_root, head_sha, path):
            errors.append(f"Existing Evidence manifest changed after authorization SHA {subject_sha}: {path}")
    return errors


def validate_merge_ready_freshness(
    repo_root: Path,
    task_path: str,
    task: dict[str, Any],
    base_sha: str,
    head_sha: str,
) -> list[str]:
    errors: list[str] = []
    task_id = str(task.get("id"))
    declared_base = task.get("git", {}).get("base_sha")
    try:
        declared_base_sha = resolve_commit(repo_root, str(declared_base), "Task git.base_sha")
    except EngineeringOSError as exc:
        errors.append(str(exc))
        declared_base_sha = None
    if declared_base_sha is not None and declared_base_sha != base_sha:
        errors.append(
            f"Task git.base_sha {declared_base_sha} does not identify explicit PR base {base_sha}"
        )

    subject_values = [
        ("implementation_sha", task.get("git", {}).get("implementation_sha")),
        ("integration_candidate_sha", task.get("git", {}).get("integration_candidate_sha")),
    ]
    subject_values.extend(
        (f"Evidence {ref.get('path')}", ref.get("subject_sha"))
        for ref in task.get("evidence_refs", [])
        if isinstance(ref, dict) and ref.get("valid") is True
    )

    resolved_subjects: dict[str, str] = {}
    for label, value in subject_values:
        if not isinstance(value, str) or not value:
            errors.append(f"Missing authorization SHA for {label}")
            continue
        try:
            subject_sha = resolve_commit(repo_root, value, label)
        except EngineeringOSError as exc:
            errors.append(str(exc))
            continue
        resolved_subjects.setdefault(subject_sha, label)
        if not is_ancestor(repo_root, base_sha, subject_sha):
            errors.append(
                f"Explicit PR base {base_sha} is not an ancestor of {label} {subject_sha}; "
                "lineage is stale or history is incomplete/shallow"
            )
        if not is_ancestor(repo_root, subject_sha, head_sha):
            errors.append(
                f"{label} {subject_sha} is not an ancestor of explicit PR head {head_sha}; "
                "history is stale, unrelated, or incomplete/shallow"
            )
            continue
        later_paths = changed_files(repo_root, subject_sha, head_sha)
        unexpected = [path for path in later_paths if not is_task_recording_path(path, task_id)]
        if unexpected:
            errors.append(
                f"Substantive or unrelated changes follow {label} {subject_sha}: "
                + ", ".join(unexpected)
            )

    for subject_sha in resolved_subjects:
        errors.extend(
            validate_authorization_snapshot(repo_root, task_path, task, subject_sha, head_sha)
        )
    return errors


def validate_lifecycle_inheritance(
    repo_root: Path,
    task_path: str,
    task: dict[str, Any],
    old_task: dict[str, Any] | None,
    base_sha: str,
    head_sha: str,
) -> list[str]:
    if old_task is None:
        return [f"Lifecycle pull request base {base_sha} does not contain {task_path}"]
    errors: list[str] = []
    task_id = str(task.get("id"))
    old_frozen = {key: value for key, value in old_task.items() if key != "status"}
    new_frozen = {key: value for key, value in task.items() if key != "status"}
    if old_frozen != new_frozen:
        errors.append("Lifecycle pull request changed Task fields other than status")

    evidence_prefix = f"docs/engineering/evidence/{task_id}"
    base_evidence = paths_at_ref(repo_root, base_sha, evidence_prefix)
    head_evidence = paths_at_ref(repo_root, head_sha, evidence_prefix)
    if base_evidence != head_evidence:
        errors.append("Lifecycle pull request added or removed Evidence manifests")
    for path in sorted(set(base_evidence) & set(head_evidence)):
        if blob_oid(repo_root, base_sha, path) != blob_oid(repo_root, head_sha, path):
            errors.append(f"Lifecycle pull request rewrote inherited Evidence manifest: {path}")
    return errors


def validate_pull_request(
    repo_root: Path,
    base_ref: str,
    head_ref: str,
    risk_rules: dict[str, Any],
    gate_policy: dict[str, Any],
) -> tuple[int, list[str]]:
    base_sha = resolve_commit(repo_root, base_ref, "explicit PR base")
    head_sha = resolve_commit(repo_root, head_ref, "explicit PR head")
    if not is_ancestor(repo_root, base_sha, head_sha):
        raise EngineeringOSError(
            f"Explicit PR base {base_sha} is not an ancestor of explicit PR head {head_sha}; "
            "history is stale or incomplete/shallow"
        )

    files = changed_files(repo_root, base_sha, head_sha)
    task_paths = task_paths_at_ref(repo_root, head_sha)
    errors: list[str] = []
    tasks: dict[str, dict[str, Any]] = {}
    for path in task_paths:
        task = yaml_at_ref(repo_root, head_sha, path)
        if task is None:
            errors.append(f"Expected a Task mapping at explicit head {head_sha}: {path}")
            continue
        tasks[path] = task
        errors.extend(f"{Path(path).name}: {error}" for error in validate_task(task, risk_rules, gate_policy))
        errors.extend(
            f"{Path(path).name}: {error}"
            for error in validate_evidence_refs_at_ref(repo_root, task, head_sha)
        )

    changed_tasks = [
        path
        for path in files
        if path.startswith("docs/engineering/tasks/T") and path.endswith(".yaml")
    ]
    if files and len(changed_tasks) != 1:
        errors.append("Each pull request must change exactly one formal Task Contract")
        return len(task_paths), errors
    if not changed_tasks:
        return len(task_paths), errors

    task_path = changed_tasks[0]
    task = tasks.get(task_path)
    if task is None:
        errors.append(f"Changed Task must exist at explicit head {head_sha}: {task_path}")
        return len(task_paths), errors
    old_task = yaml_at_ref(repo_root, base_sha, task_path)
    errors.extend(validate_consistency(task, files, old_task))
    errors.extend(validate_contract_semantics(task, old_task))

    task_id = str(task.get("id"))
    status = task.get("status")
    old_status = old_task.get("status") if old_task is not None else None
    base_is_authorized = (
        old_status in MAIN_STATES and MAIN_STATES.index(old_status) >= MERGE_READY_INDEX
    )
    substantive = any(not is_task_recording_path(path, task_id) for path in files)
    if substantive and status != "MERGE_READY":
        errors.append(
            "Implementation-substantive pull requests require Task Contract status "
            f"MERGE_READY; found {status}"
        )
    if status == "MERGE_READY":
        errors.extend(
            validate_merge_ready_freshness(repo_root, task_path, task, base_sha, head_sha)
        )
    elif base_is_authorized or (
        status in MAIN_STATES and MAIN_STATES.index(status) >= MERGED_INDEX
    ):
        unexpected = [path for path in files if not is_lifecycle_path(path, task_id)]
        if unexpected:
            errors.append(
                "Lifecycle pull requests may change only the same Task status and HANDOFF: "
                + ", ".join(unexpected)
            )
        errors.extend(
            validate_lifecycle_inheritance(
                repo_root, task_path, task, old_task, base_sha, head_sha
            )
        )
    return len(task_paths), errors


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
        errors: list[str] = []
        if args.base_ref:
            task_count, errors = validate_pull_request(
                repo_root,
                args.base_ref,
                args.head_ref,
                risk_rules,
                gate_policy,
            )
        else:
            tasks = task_files(repo_root)
            task_count = len(tasks)
            for path in tasks:
                task = load_yaml(path)
                errors.extend(
                    f"{path.name}: {error}"
                    for error in validate_task(task, risk_rules, gate_policy, repo_root)
                )
    except EngineeringOSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"PASS: validated {task_count} formal task contract(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
