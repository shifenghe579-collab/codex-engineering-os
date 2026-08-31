from __future__ import annotations

import json
import sys
import tomllib
import unittest
from copy import deepcopy
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from os_core import (  # noqa: E402
    governance_digest,
    is_protected_path,
    load_yaml,
    matches_any,
    validate_consistency,
    validate_task,
    validate_transition,
)


def approval() -> dict[str, str]:
    return {"by": "product-authority", "at": "2026-08-31T00:00:00Z", "source_uri": "https://example.invalid/approval"}


def valid_task() -> dict:
    required = ["contract", "scope", "implementation_verify", "review", "ci"]
    return {
        "id": "T001",
        "kind": "standard",
        "contract_version": 1,
        "status": "READY",
        "goal": "Deliver one bounded behavior.",
        "current_behavior": "The behavior is absent.",
        "expected_behavior": "The behavior is present.",
        "non_goals": [],
        "invariants": ["Existing behavior remains stable."],
        "acceptance_criteria": ["The confirmed behavior is observable."],
        "open_questions": [],
        "scope": {"allowed": ["src/**", "tests/**", "docs/engineering/tasks/T001.yaml"], "forbidden": ["governance/**"]},
        "change_impact": {"spec": False, "architecture": False, "project": False, "adr": False, "tests": True, "runtime": False},
        "risk": {"classified": "R1", "floor": "R0", "triggers": []},
        "technical_direction": "Keep the change local.",
        "execution_plan": ["Implement", "Verify"],
        "dispatch": {"profile": "worker-standard", "mode": "worktree", "required_environment": [], "required_gates": required},
        "git": {"base_sha": "a" * 40, "implementation_sha": None, "integration_candidate_sha": None},
        "approvals": {"requirement": approval(), "architecture": None, "review": None, "acceptance": None, "risk": None},
        "proposed_state_changes": [],
        "governance_baseline": {"commit": "b" * 40, "digest": "sha256:" + "c" * 64},
        "evidence_refs": [],
    }


class TaskValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.risk_rules = load_yaml(REPO_ROOT / "governance/RISK_RULES.yaml")
        cls.gate_policy = load_yaml(REPO_ROOT / "governance/GATE_POLICY.yaml")

    def test_valid_ready_r1_contract(self) -> None:
        self.assertEqual(validate_task(valid_task(), self.risk_rules, self.gate_policy), [])

    def test_risk_floor_cannot_be_lowered(self) -> None:
        task = valid_task()
        task["risk"] = {"classified": "R1", "floor": "R2", "triggers": ["authentication"]}
        errors = validate_task(task, self.risk_rules, self.gate_policy)
        self.assertTrue(any("below governance floor R2" in error for error in errors))

    def test_declared_floor_must_match_rules(self) -> None:
        task = valid_task()
        task["risk"]["floor"] = "R1"
        errors = validate_task(task, self.risk_rules, self.gate_policy)
        self.assertTrue(any("does not match governance floor R0" in error for error in errors))

    def test_r2_requires_challenge_and_gates(self) -> None:
        task = valid_task()
        task["risk"] = {"classified": "R2", "floor": "R2", "triggers": ["public_api"]}
        errors = validate_task(task, self.risk_rules, self.gate_policy)
        self.assertTrue(any("Missing required gates for R2" in error for error in errors))
        self.assertTrue(any("architecture challenge approval" in error for error in errors))

    def test_ready_requires_closed_questions(self) -> None:
        task = valid_task()
        task["open_questions"] = ["What should happen?"]
        errors = validate_task(task, self.risk_rules, self.gate_policy)
        self.assertTrue(any("open_questions" in error for error in errors))


class TransitionAndScopeTests(unittest.TestCase):
    def test_cannot_skip_main_state(self) -> None:
        old = valid_task()
        new = deepcopy(old)
        new["status"] = "VERIFYING"
        errors = validate_transition(old, new)
        self.assertTrue(any("Illegal state transition" in error for error in errors))

    def test_contract_change_restarts_clarification(self) -> None:
        old = valid_task()
        new = deepcopy(old)
        new["contract_version"] = 2
        new["status"] = "CLARIFYING"
        self.assertEqual(validate_transition(old, new), [])

    def test_scope_rejects_outside_path(self) -> None:
        errors = validate_consistency(valid_task(), ["src/app.py", "README.md"])
        self.assertTrue(any("README.md" in error for error in errors))

    def test_standard_task_cannot_change_governance(self) -> None:
        task = valid_task()
        task["scope"]["allowed"].append("AGENTS.md")
        errors = validate_consistency(task, ["AGENTS.md"])
        self.assertTrue(any("non-governance task" in error for error in errors))

    def test_path_helpers(self) -> None:
        self.assertTrue(matches_any("src/a/b.py", ["src/**"]))
        self.assertTrue(is_protected_path(".github/workflows/engineering-os.yml"))
        self.assertFalse(is_protected_path("src/app.py"))


class RepositoryArtifactTests(unittest.TestCase):
    def test_json_schemas_are_valid_json(self) -> None:
        for path in (REPO_ROOT / "governance/schemas").glob("*.json"):
            with self.subTest(path=path.name):
                self.assertIsInstance(json.loads(path.read_text(encoding="utf-8")), dict)

    def test_codex_configuration_is_valid_toml(self) -> None:
        for path in (REPO_ROOT / ".codex").rglob("*.toml"):
            with self.subTest(path=path.name):
                self.assertIsInstance(tomllib.loads(path.read_text(encoding="utf-8")), dict)

    def test_governance_digest_is_stable_shape(self) -> None:
        digest = governance_digest(REPO_ROOT)
        self.assertRegex(digest, r"^sha256:[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
