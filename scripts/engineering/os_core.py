from __future__ import annotations

import fnmatch
import hashlib
import re
import subprocess
from pathlib import Path
from typing import Any, Iterable

import yaml


RISK_LEVELS = ("R0", "R1", "R2", "R3")
MAIN_STATES = (
    "CLARIFYING",
    "DESIGNING",
    "READY",
    "IMPLEMENTING",
    "VERIFYING",
    "REVIEWING",
    "ACCEPTING",
    "INTEGRATION_PREPARING",
    "INTEGRATION_VERIFYING",
    "MERGE_READY",
    "MERGED",
    "POST_MERGE_VERIFYING",
    "DEVELOPMENT_COMPLETE",
)
EXCEPTION_STATES = (
    "BLOCKED",
    "CHANGES_REQUESTED",
    "CONTRACT_CHANGE",
    "REASSESSING",
    "CANCELLED",
)
ALL_STATES = MAIN_STATES + EXCEPTION_STATES
SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{7,40}$")
TASK_ID_PATTERN = re.compile(r"^T[0-9]{3,}$")

PROTECTED_PATTERNS = (
    "AGENTS.md",
    "governance/**",
    ".github/**",
    ".codex/**",
    "scripts/engineering/**",
)

ALLOWED_TRANSITIONS = {
    state: {MAIN_STATES[index + 1], "BLOCKED", "CONTRACT_CHANGE", "CANCELLED"}
    for index, state in enumerate(MAIN_STATES[:-1])
}
ALLOWED_TRANSITIONS["DEVELOPMENT_COMPLETE"] = set()
ALLOWED_TRANSITIONS.update(
    {
        "BLOCKED": {"CLARIFYING", "DESIGNING", "READY", "IMPLEMENTING", "CANCELLED"},
        "CHANGES_REQUESTED": {"DESIGNING", "IMPLEMENTING", "VERIFYING", "CANCELLED"},
        "CONTRACT_CHANGE": {"CLARIFYING", "CANCELLED"},
        "REASSESSING": {"CLARIFYING", "DESIGNING", "READY", "CANCELLED"},
        "CANCELLED": set(),
    }
)


class EngineeringOSError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise EngineeringOSError(f"File not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise EngineeringOSError(f"Invalid YAML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise EngineeringOSError(f"Expected a YAML mapping in {path}")
    return data


def normalize_path(path: str | Path) -> str:
    return str(path).replace("\\", "/").removeprefix("./")


def matches_any(path: str, patterns: Iterable[str]) -> bool:
    normalized = normalize_path(path)
    return any(fnmatch.fnmatchcase(normalized, normalize_path(pattern)) for pattern in patterns)


def is_protected_path(path: str) -> bool:
    return matches_any(path, PROTECTED_PATTERNS)


def git(repo_root: Path, *args: str, check: bool = True) -> str:
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
    return result.stdout.strip()


def changed_files(repo_root: Path, base_ref: str, head_ref: str) -> list[str]:
    output = git(repo_root, "diff", "--name-only", f"{base_ref}...{head_ref}")
    return [normalize_path(line) for line in output.splitlines() if line.strip()]


def yaml_at_ref(repo_root: Path, ref: str, relative_path: str) -> dict[str, Any] | None:
    result = subprocess.run(
        ["git", "show", f"{ref}:{normalize_path(relative_path)}"],
        cwd=repo_root,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    try:
        data = yaml.safe_load(result.stdout)
    except yaml.YAMLError as exc:
        raise EngineeringOSError(f"Invalid YAML at {ref}:{relative_path}: {exc}") from exc
    return data if isinstance(data, dict) else None


def governance_digest(repo_root: Path) -> str:
    hasher = hashlib.sha256()
    files: list[Path] = []
    for path in repo_root.rglob("*"):
        if not path.is_file() or ".git" in path.parts or "__pycache__" in path.parts:
            continue
        relative = normalize_path(path.relative_to(repo_root))
        if is_protected_path(relative):
            files.append(path)
    for path in sorted(files, key=lambda item: normalize_path(item.relative_to(repo_root))):
        relative = normalize_path(path.relative_to(repo_root))
        hasher.update(relative.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
        hasher.update(b"\0")
    return f"sha256:{hasher.hexdigest()}"


def _mapping(value: Any, name: str, errors: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        errors.append(f"{name} must be a mapping")
        return {}
    return value


def _list(value: Any, name: str, errors: list[str]) -> list[Any]:
    if not isinstance(value, list):
        errors.append(f"{name} must be a list")
        return []
    return value


def _required_text(task: dict[str, Any], field: str, errors: list[str]) -> None:
    value = task.get(field)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{field} must be non-empty text")


def _valid_sha(value: Any) -> bool:
    return isinstance(value, str) and bool(SHA_PATTERN.fullmatch(value))


def compute_risk_floor(triggers: list[str], risk_rules: dict[str, Any], errors: list[str]) -> str:
    ranks = risk_rules.get("ranks", {})
    floors = risk_rules.get("floors", {})
    floor = "R0"
    for trigger in triggers:
        if trigger not in floors:
            errors.append(f"Unknown risk trigger: {trigger}")
            continue
        candidate = floors[trigger]
        if candidate not in ranks:
            errors.append(f"Risk rule for {trigger} has invalid level: {candidate}")
            continue
        if ranks[candidate] > ranks[floor]:
            floor = candidate
    return floor


def required_gates_for(risk: str, gate_policy: dict[str, Any]) -> set[str]:
    lane = gate_policy.get("risk_lanes", {}).get(risk, {})
    required = lane.get("required", [])
    return {str(item) for item in required}


def validate_task(
    task: dict[str, Any],
    risk_rules: dict[str, Any],
    gate_policy: dict[str, Any],
    repo_root: Path | None = None,
) -> list[str]:
    errors: list[str] = []

    task_id = task.get("id")
    if not isinstance(task_id, str) or not TASK_ID_PATTERN.fullmatch(task_id):
        errors.append("id must match T followed by at least three digits")
    if task.get("kind") not in {"standard", "governance"}:
        errors.append("kind must be standard or governance")
    if not isinstance(task.get("contract_version"), int) or task["contract_version"] < 1:
        errors.append("contract_version must be a positive integer")

    status = task.get("status")
    if status not in ALL_STATES:
        errors.append(f"Unknown status: {status}")

    _required_text(task, "goal", errors)
    _required_text(task, "expected_behavior", errors)
    for field in ("non_goals", "invariants", "acceptance_criteria", "open_questions", "execution_plan", "proposed_state_changes", "evidence_refs"):
        _list(task.get(field), field, errors)

    scope = _mapping(task.get("scope"), "scope", errors)
    allowed = _list(scope.get("allowed"), "scope.allowed", errors)
    forbidden = _list(scope.get("forbidden"), "scope.forbidden", errors)
    if any(not isinstance(item, str) or not item for item in allowed + forbidden):
        errors.append("scope patterns must be non-empty strings")

    change_impact = _mapping(task.get("change_impact"), "change_impact", errors)
    for field in ("spec", "architecture", "project", "adr", "tests", "runtime"):
        if not isinstance(change_impact.get(field), bool):
            errors.append(f"change_impact.{field} must be boolean")

    risk = _mapping(task.get("risk"), "risk", errors)
    classified = risk.get("classified")
    declared_floor = risk.get("floor")
    triggers = _list(risk.get("triggers"), "risk.triggers", errors)
    if classified not in RISK_LEVELS:
        errors.append(f"Invalid classified risk: {classified}")
    if declared_floor not in RISK_LEVELS:
        errors.append(f"Invalid declared risk floor: {declared_floor}")
    computed_floor = compute_risk_floor([item for item in triggers if isinstance(item, str)], risk_rules, errors)
    if declared_floor in RISK_LEVELS and declared_floor != computed_floor:
        errors.append(f"Declared risk floor {declared_floor} does not match governance floor {computed_floor}")
    ranks = risk_rules.get("ranks", {})
    if classified in ranks and computed_floor in ranks and ranks[classified] < ranks[computed_floor]:
        errors.append(f"Classified risk {classified} is below governance floor {computed_floor}")

    dispatch = _mapping(task.get("dispatch"), "dispatch", errors)
    required_gates = {str(item) for item in _list(dispatch.get("required_gates"), "dispatch.required_gates", errors)}
    if dispatch.get("mode") not in {"worktree", "local-read-only", "local"}:
        errors.append("dispatch.mode must be worktree, local-read-only, or local")
    if not isinstance(dispatch.get("profile"), str) or not dispatch.get("profile"):
        errors.append("dispatch.profile must be non-empty text")
    _list(dispatch.get("required_environment"), "dispatch.required_environment", errors)

    git_data = _mapping(task.get("git"), "git", errors)
    approvals = _mapping(task.get("approvals"), "approvals", errors)
    baseline = _mapping(task.get("governance_baseline"), "governance_baseline", errors)

    if status in MAIN_STATES and MAIN_STATES.index(status) >= MAIN_STATES.index("READY"):
        acceptance = task.get("acceptance_criteria", [])
        if not acceptance:
            errors.append("READY and later states require acceptance_criteria")
        if task.get("open_questions"):
            errors.append("READY and later states require open_questions to be empty")
        if approvals.get("requirement") is None:
            errors.append("READY and later states require requirement approval")
        if not _valid_sha(git_data.get("base_sha")):
            errors.append("READY and later states require a valid git.base_sha")
        if not _valid_sha(baseline.get("commit")):
            errors.append("READY and later states require a valid governance baseline commit")
        digest = baseline.get("digest")
        if not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
            errors.append("READY and later states require a valid governance baseline digest")
        if classified in RISK_LEVELS:
            missing = required_gates_for(classified, gate_policy) - required_gates
            if missing:
                errors.append(f"Missing required gates for {classified}: {', '.join(sorted(missing))}")
        if classified in {"R2", "R3"} and approvals.get("architecture") is None:
            errors.append(f"{classified} requires architecture challenge approval before READY")
        if classified == "R3" and approvals.get("risk") is None:
            errors.append("R3 requires explicit human risk approval")

    if status in MAIN_STATES and MAIN_STATES.index(status) >= MAIN_STATES.index("VERIFYING"):
        if not _valid_sha(git_data.get("implementation_sha")):
            errors.append("VERIFYING and later states require a valid implementation SHA")

    evidence_refs = task.get("evidence_refs", []) if isinstance(task.get("evidence_refs"), list) else []
    evidence_types = {
        ref.get("type") for ref in evidence_refs if isinstance(ref, dict) and ref.get("valid") is True
    }
    if status in MAIN_STATES and MAIN_STATES.index(status) >= MAIN_STATES.index("REVIEWING"):
        if "implementation" not in evidence_types:
            errors.append("REVIEWING and later states require valid implementation evidence")
    if status in MAIN_STATES and MAIN_STATES.index(status) >= MAIN_STATES.index("ACCEPTING"):
        if approvals.get("review") is None or "review" not in evidence_types:
            errors.append("ACCEPTING and later states require approved review evidence")
    if status in MAIN_STATES and MAIN_STATES.index(status) >= MAIN_STATES.index("INTEGRATION_PREPARING"):
        if approvals.get("acceptance") is None or "acceptance" not in evidence_types:
            errors.append("Integration and later states require approved acceptance evidence")
    if status in MAIN_STATES and MAIN_STATES.index(status) >= MAIN_STATES.index("MERGE_READY"):
        if not _valid_sha(git_data.get("integration_candidate_sha")):
            errors.append("MERGE_READY and later states require a valid integration candidate SHA")
        if "integration" not in evidence_types:
            errors.append("MERGE_READY and later states require valid integration evidence")

    if repo_root is not None:
        errors.extend(validate_evidence_refs(task, repo_root))
    return errors


def validate_evidence_refs(task: dict[str, Any], repo_root: Path) -> list[str]:
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
        evidence_path = repo_root / path
        if not evidence_path.is_file():
            errors.append(f"Evidence file does not exist: {path}")
            continue
        evidence = load_yaml(evidence_path)
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


def validate_transition(old_task: dict[str, Any], new_task: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    old_version = old_task.get("contract_version")
    new_version = new_task.get("contract_version")
    old_status = old_task.get("status")
    new_status = new_task.get("status")

    if not isinstance(old_version, int) or not isinstance(new_version, int):
        return ["Cannot validate transition without integer contract versions"]
    if new_version < old_version:
        errors.append("Contract version cannot decrease")
    elif new_version > old_version:
        if new_version != old_version + 1:
            errors.append("Contract version must increase exactly one version at a time")
        if new_status not in {"CLARIFYING", "CONTRACT_CHANGE"}:
            errors.append("A new contract version must restart at CLARIFYING or CONTRACT_CHANGE")
    elif old_status != new_status:
        allowed = ALLOWED_TRANSITIONS.get(old_status, set())
        if new_status not in allowed:
            errors.append(f"Illegal state transition: {old_status} -> {new_status}")
    return errors


def validate_consistency(
    task: dict[str, Any],
    files: list[str],
    old_task: dict[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []
    scope = task.get("scope", {})
    allowed = scope.get("allowed", []) if isinstance(scope, dict) else []
    forbidden = scope.get("forbidden", []) if isinstance(scope, dict) else []

    for path in files:
        if matches_any(path, forbidden):
            errors.append(f"Changed forbidden path: {path}")
        if not matches_any(path, allowed):
            errors.append(f"Changed path outside allowed scope: {path}")

    protected = [path for path in files if is_protected_path(path)]
    if protected and task.get("kind") != "governance":
        errors.append("Protected governance files changed by a non-governance task")

    impact = task.get("change_impact", {})
    impact_paths = {
        "spec": "docs/engineering/SPEC.md",
        "architecture": "docs/engineering/ARCHITECTURE.md",
        "project": "docs/engineering/PROJECT.md",
    }
    for field, expected_path in impact_paths.items():
        declared = impact.get(field) is True if isinstance(impact, dict) else False
        actually_changed = expected_path in files
        if declared and not actually_changed:
            errors.append(f"change_impact.{field} is true but {expected_path} was not changed")
        if actually_changed and not declared:
            errors.append(f"{expected_path} changed but change_impact.{field} is false")

    if isinstance(impact, dict) and impact.get("adr") is True:
        if not any(path.startswith("docs/engineering/decisions/ADR-") for path in files):
            errors.append("change_impact.adr is true but no ADR changed")
    if old_task is not None:
        errors.extend(validate_transition(old_task, task))
    return errors
