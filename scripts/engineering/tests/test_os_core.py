from __future__ import annotations

import json
import io
import subprocess
import sys
import tempfile
import tomllib
import unittest
from copy import deepcopy
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

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
from ci_check import main as ci_main  # noqa: E402


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


class CiEntryPointTests(unittest.TestCase):
    def git(self, repo: Path, *args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=repo,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=True,
        )
        return result.stdout.strip()

    def commit(self, repo: Path, message: str) -> str:
        self.git(repo, "add", ".")
        self.git(repo, "commit", "-m", message)
        return self.git(repo, "rev-parse", "HEAD")

    def write_task(self, repo: Path, task: dict) -> None:
        path = repo / "docs/engineering/tasks/T001.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(task, indent=2), encoding="utf-8")

    def recording_task(self, base_sha: str) -> dict:
        task = valid_task()
        task["kind"] = "governance"
        task["git"]["base_sha"] = base_sha
        task["scope"] = {
            "allowed": [
                "src/**",
                "tests/**",
                ".github/**",
                "governance/**",
                "docs/engineering/tasks/T001.yaml",
                "docs/engineering/evidence/T001/**",
                "docs/engineering/HANDOFF.md",
            ],
            "forbidden": [],
        }
        return task

    def write_evidence(self, repo: Path, task: dict) -> None:
        evidence_dir = repo / "docs/engineering/evidence/T001"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        for ref in task["evidence_refs"]:
            (repo / ref["path"]).write_text(
                json.dumps(
                    {
                        "task": "T001",
                        "contract_version": task["contract_version"],
                        "subject_sha": ref["subject_sha"],
                    }
                ),
                encoding="utf-8",
            )

    def create_merge_ready_repo(
        self,
        *,
        descendant_files: dict[str, str] | None = None,
        subject_mutator=None,
        final_mutator=None,
        subject_present: bool = True,
        final_version: int = 1,
    ) -> tuple[tempfile.TemporaryDirectory, Path, str, str, str]:
        temporary = tempfile.TemporaryDirectory()
        repo = Path(temporary.name)
        (repo / "governance").mkdir()
        for name in ("RISK_RULES.yaml", "GATE_POLICY.yaml"):
            (repo / "governance" / name).write_text(
                (REPO_ROOT / "governance" / name).read_text(encoding="utf-8"),
                encoding="utf-8",
            )

        self.git(repo, "init", "-b", "main")
        self.git(repo, "config", "user.name", "test")
        self.git(repo, "config", "user.email", "test@example.invalid")
        base_sha = self.commit(repo, "base")

        subject_task = self.recording_task(base_sha)
        if subject_mutator:
            subject_mutator(subject_task)
        if subject_present:
            self.write_task(repo, subject_task)
        (repo / "src").mkdir()
        (repo / "src/app.py").write_text("VALUE = 1\n", encoding="utf-8")
        subject_sha = self.commit(repo, "authorization subject")

        if descendant_files:
            for relative, content in descendant_files.items():
                path = repo / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            self.commit(repo, "later change")

        final_task = deepcopy(subject_task)
        final_task["contract_version"] = final_version
        final_task["status"] = "MERGE_READY"
        final_task["git"]["implementation_sha"] = subject_sha
        final_task["git"]["integration_candidate_sha"] = subject_sha
        final_task["approvals"]["review"] = approval()
        final_task["approvals"]["acceptance"] = approval()
        final_task["evidence_refs"] = [
            {
                "type": evidence_type,
                "path": f"docs/engineering/evidence/T001/{evidence_type}.yaml",
                "subject_sha": subject_sha,
                "valid": True,
            }
            for evidence_type in ("implementation", "review", "acceptance", "integration")
        ]
        if final_mutator:
            final_mutator(final_task)
        self.write_task(repo, final_task)
        self.write_evidence(repo, final_task)
        head_sha = self.commit(repo, "record authorization")
        return temporary, repo, base_sha, subject_sha, head_sha

    def create_lifecycle_repo(
        self,
        *,
        task_mutator=None,
        manifest_mutator=None,
        descendant_files: dict[str, str] | None = None,
    ) -> tuple[tempfile.TemporaryDirectory, Path, str, str]:
        temporary, repo, _, _, _ = self.create_merge_ready_repo()
        task = json.loads((repo / "docs/engineering/tasks/T001.yaml").read_text(encoding="utf-8"))
        pre_squash_sha = "a" * 40
        task["git"]["implementation_sha"] = pre_squash_sha
        task["git"]["integration_candidate_sha"] = pre_squash_sha
        for ref in task["evidence_refs"]:
            ref["subject_sha"] = pre_squash_sha
        self.write_task(repo, task)
        self.write_evidence(repo, task)
        merge_ready_sha = self.commit(repo, "squash-merged authorization snapshot")

        task = json.loads((repo / "docs/engineering/tasks/T001.yaml").read_text(encoding="utf-8"))
        task["status"] = "MERGED"
        if task_mutator:
            task_mutator(task)
        self.write_task(repo, task)
        handoff = repo / "docs/engineering/HANDOFF.md"
        handoff.write_text("T001 merged\n", encoding="utf-8")
        if manifest_mutator:
            manifest_mutator(repo)
        if descendant_files:
            for relative, content in descendant_files.items():
                path = repo / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
        head_sha = self.commit(repo, "lifecycle")
        return temporary, repo, merge_ready_sha, head_sha

    def create_ready_update_repo(
        self,
        *,
        base_status: str,
        substantive: bool,
        rewrite_acceptance: bool,
    ) -> tuple[tempfile.TemporaryDirectory, Path, str, str]:
        temporary, repo, original_base, _, _ = self.create_merge_ready_repo()
        task = self.recording_task(original_base)
        task["status"] = base_status
        self.write_task(repo, task)
        base_sha = self.commit(repo, "ready-state base")

        task["status"] = "READY"
        if rewrite_acceptance:
            task["acceptance_criteria"] = ["Rewritten acceptance semantics."]
        self.write_task(repo, task)
        if substantive:
            (repo / "src/late.py").write_text("VALUE = 2\n", encoding="utf-8")
        head_sha = self.commit(repo, "ready-state head")
        return temporary, repo, base_sha, head_sha

    def create_authorized_blocked_repo(
        self,
        *,
        base_status: str,
        tamper: str | None = None,
    ) -> tuple[tempfile.TemporaryDirectory, Path, str, str]:
        if base_status == "MERGE_READY":
            temporary, repo, _, _, base_sha = self.create_merge_ready_repo()
        else:
            temporary, repo, _, base_sha = self.create_lifecycle_repo()

        task = json.loads((repo / "docs/engineering/tasks/T001.yaml").read_text(encoding="utf-8"))
        task["status"] = "BLOCKED"
        if tamper == "candidate":
            task["git"]["integration_candidate_sha"] = "b" * 40
        elif tamper == "approval":
            task["approvals"]["review"] = {
                "by": "replacement",
                "at": "2026-09-01T00:00:00Z",
                "source_uri": "https://example.invalid/replacement",
            }
        elif tamper == "ref":
            task["evidence_refs"][0]["source_uri"] = "https://example.invalid/rewrite"
        self.write_task(repo, task)
        if tamper == "manifest":
            path = repo / "docs/engineering/evidence/T001/review.yaml"
            evidence = json.loads(path.read_text(encoding="utf-8"))
            evidence["note"] = "rewritten"
            path.write_text(json.dumps(evidence), encoding="utf-8")
        head_sha = self.commit(repo, f"{base_status.lower()} to blocked")
        return temporary, repo, base_sha, head_sha

    def advance_blocked_repo(
        self,
        repo: Path,
        *,
        tamper: bool,
    ) -> str:
        task = json.loads((repo / "docs/engineering/tasks/T001.yaml").read_text(encoding="utf-8"))
        task["status"] = "IMPLEMENTING"
        if tamper:
            task["git"]["integration_candidate_sha"] = "b" * 40
            task["approvals"]["review"] = {
                "by": "replacement",
                "at": "2026-09-01T00:00:00Z",
                "source_uri": "https://example.invalid/replacement",
            }
            task["evidence_refs"] = []
        self.write_task(repo, task)
        return self.commit(repo, "blocked to implementing")

    def run_ci(
        self,
        repo: Path,
        base_sha: str | None,
        head_ref: str = "HEAD",
    ) -> tuple[int, str]:
        arguments = ["ci_check.py", "--repo-root", str(repo)]
        if base_sha:
            arguments.extend(["--base-ref", base_sha, "--head-ref", head_ref])
        output = io.StringIO()
        with patch.object(sys, "argv", arguments), redirect_stdout(output), redirect_stderr(output):
            result = ci_main()
        return result, output.getvalue()

    def test_recording_descendant_is_accepted(self) -> None:
        temporary, repo, base_sha, _, _ = self.create_merge_ready_repo()
        with temporary:
            result, output = self.run_ci(repo, base_sha)
        self.assertEqual((result, output), (0, "PASS: validated 1 formal task contract(s)\n"))

    def test_substantive_ready_is_rejected(self) -> None:
        temporary, repo, base_sha, head_sha = self.create_ready_update_repo(
            base_status="DESIGNING",
            substantive=True,
            rewrite_acceptance=False,
        )
        with temporary:
            result, output = self.run_ci(repo, base_sha, head_sha)
        self.assertEqual(result, 1)
        self.assertIn("require Task Contract status MERGE_READY; found READY", output)

    def test_substantive_merge_ready_is_accepted(self) -> None:
        temporary, repo, base_sha, _, head_sha = self.create_merge_ready_repo()
        with temporary:
            result, output = self.run_ci(repo, base_sha, head_sha)
        self.assertEqual((result, output), (0, "PASS: validated 1 formal task contract(s)\n"))

    def test_substantive_merged_is_rejected(self) -> None:
        temporary, repo, base_sha, head_sha = self.create_lifecycle_repo(
            descendant_files={"src/late.py": "VALUE = 2\n"}
        )
        with temporary:
            result, output = self.run_ci(repo, base_sha, head_sha)
        self.assertEqual(result, 1)
        self.assertIn("require Task Contract status MERGE_READY; found MERGED", output)

    def test_lifecycle_only_merge_transition_is_accepted(self) -> None:
        temporary, repo, base_sha, head_sha = self.create_lifecycle_repo()
        with temporary:
            result, output = self.run_ci(repo, base_sha, head_sha)
        self.assertEqual((result, output), (0, "PASS: validated 1 formal task contract(s)\n"))

    def test_ready_contract_semantics_cannot_change_without_new_version(self) -> None:
        temporary, repo, base_sha, head_sha = self.create_ready_update_repo(
            base_status="READY",
            substantive=False,
            rewrite_acceptance=True,
        )
        with temporary:
            result, output = self.run_ci(repo, base_sha, head_sha)
        self.assertEqual(result, 1)
        self.assertIn(
            "Contract semantics changed without incrementing contract_version: acceptance_criteria",
            output,
        )

    def test_merge_ready_contract_semantics_cannot_change_without_new_version(self) -> None:
        temporary, repo, _, _, merge_ready_sha = self.create_merge_ready_repo()
        with temporary:
            task = json.loads((repo / "docs/engineering/tasks/T001.yaml").read_text(encoding="utf-8"))
            task["acceptance_criteria"] = ["Rewritten acceptance semantics."]
            self.write_task(repo, task)
            rewritten_sha = self.commit(repo, "rewrite merge-ready semantics")
            result, output = self.run_ci(repo, merge_ready_sha, rewritten_sha)
        self.assertEqual(result, 1)
        self.assertIn(
            "Contract semantics changed without incrementing contract_version: acceptance_criteria",
            output,
        )

    def test_pre_ready_authorization_subject_is_rejected(self) -> None:
        def mutate(task: dict) -> None:
            task["status"] = "DESIGNING"

        temporary, repo, base_sha, _, _ = self.create_merge_ready_repo(
            subject_mutator=mutate
        )
        with temporary:
            result, output = self.run_ci(repo, base_sha)
        self.assertEqual(result, 1)
        self.assertIn("not monotonic", output)
        self.assertIn("DESIGNING -> MERGE_READY", output)

    def test_merge_ready_to_blocked_status_only_is_accepted(self) -> None:
        temporary, repo, base_sha, head_sha = self.create_authorized_blocked_repo(
            base_status="MERGE_READY"
        )
        with temporary:
            result, output = self.run_ci(repo, base_sha, head_sha)
        self.assertEqual((result, output), (0, "PASS: validated 1 formal task contract(s)\n"))

    def test_merged_to_blocked_status_only_is_accepted(self) -> None:
        temporary, repo, base_sha, head_sha = self.create_authorized_blocked_repo(
            base_status="MERGED"
        )
        with temporary:
            result, output = self.run_ci(repo, base_sha, head_sha)
        self.assertEqual((result, output), (0, "PASS: validated 1 formal task contract(s)\n"))

    def test_merge_ready_to_blocked_authorization_tampering_is_rejected(self) -> None:
        for tamper in ("candidate", "approval", "ref", "manifest"):
            with self.subTest(tamper=tamper):
                temporary, repo, base_sha, head_sha = self.create_authorized_blocked_repo(
                    base_status="MERGE_READY",
                    tamper=tamper,
                )
                with temporary:
                    result, output = self.run_ci(repo, base_sha, head_sha)
                self.assertEqual(result, 1)
                self.assertTrue(
                    "changed Task fields other than status" in output
                    or "rewrote inherited Evidence manifest" in output
                )

    def test_merged_to_blocked_authorization_tampering_is_rejected(self) -> None:
        for tamper in ("candidate", "approval", "ref", "manifest"):
            with self.subTest(tamper=tamper):
                temporary, repo, base_sha, head_sha = self.create_authorized_blocked_repo(
                    base_status="MERGED",
                    tamper=tamper,
                )
                with temporary:
                    result, output = self.run_ci(repo, base_sha, head_sha)
                self.assertEqual(result, 1)
                self.assertTrue(
                    "changed Task fields other than status" in output
                    or "rewrote inherited Evidence manifest" in output
                )

    def test_merged_blocked_then_implementing_tampering_is_rejected(self) -> None:
        temporary, repo, _, blocked_sha = self.create_authorized_blocked_repo(
            base_status="MERGED"
        )
        with temporary:
            implementing_sha = self.advance_blocked_repo(repo, tamper=True)
            result, output = self.run_ci(repo, blocked_sha, implementing_sha)
        self.assertEqual(result, 1)
        self.assertIn("changed Task fields other than status", output)

    def test_merge_ready_blocked_then_implementing_tampering_is_rejected(self) -> None:
        temporary, repo, _, blocked_sha = self.create_authorized_blocked_repo(
            base_status="MERGE_READY"
        )
        with temporary:
            implementing_sha = self.advance_blocked_repo(repo, tamper=True)
            result, output = self.run_ci(repo, blocked_sha, implementing_sha)
        self.assertEqual(result, 1)
        self.assertIn("changed Task fields other than status", output)

    def test_authorized_blocked_to_implementing_status_only_is_accepted(self) -> None:
        temporary, repo, _, blocked_sha = self.create_authorized_blocked_repo(
            base_status="MERGED"
        )
        with temporary:
            implementing_sha = self.advance_blocked_repo(repo, tamper=False)
            result, output = self.run_ci(repo, blocked_sha, implementing_sha)
        self.assertEqual((result, output), (0, "PASS: validated 1 formal task contract(s)\n"))

    def test_merge_dag_subject_on_different_parent_chain_is_rejected(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        repo = Path(temporary.name)
        with temporary:
            (repo / "governance").mkdir()
            for name in ("RISK_RULES.yaml", "GATE_POLICY.yaml"):
                (repo / "governance" / name).write_text(
                    (REPO_ROOT / "governance" / name).read_text(encoding="utf-8"),
                    encoding="utf-8",
                )
            self.git(repo, "init", "-b", "main")
            self.git(repo, "config", "user.name", "test")
            self.git(repo, "config", "user.email", "test@example.invalid")
            root_sha = self.commit(repo, "root")
            self.git(repo, "branch", "side", root_sha)
            (repo / "main.txt").write_text("base\n", encoding="utf-8")
            base_sha = self.commit(repo, "explicit base")

            self.git(repo, "switch", "side")
            subject_task = self.recording_task(base_sha)
            self.write_task(repo, subject_task)
            (repo / "src").mkdir()
            (repo / "src/app.py").write_text("VALUE = 1\n", encoding="utf-8")
            subject_sha = self.commit(repo, "side authorization subject")

            self.git(repo, "switch", "main")
            self.git(repo, "merge", "--no-ff", "side", "-m", "merge side")
            final_task = deepcopy(subject_task)
            final_task["status"] = "MERGE_READY"
            final_task["git"]["implementation_sha"] = subject_sha
            final_task["git"]["integration_candidate_sha"] = subject_sha
            final_task["approvals"]["review"] = approval()
            final_task["approvals"]["acceptance"] = approval()
            final_task["evidence_refs"] = [
                {
                    "type": evidence_type,
                    "path": f"docs/engineering/evidence/T001/{evidence_type}.yaml",
                    "subject_sha": subject_sha,
                    "valid": True,
                }
                for evidence_type in ("implementation", "review", "acceptance", "integration")
            ]
            self.write_task(repo, final_task)
            self.write_evidence(repo, final_task)
            head_sha = self.commit(repo, "record merged authorization")
            result, output = self.run_ci(repo, base_sha, head_sha)
        self.assertEqual(result, 1)
        self.assertIn("is not an ancestor of implementation_sha", output)

    def test_source_test_workflow_and_governance_descendants_are_rejected(self) -> None:
        cases = {
            "src/late.py": "VALUE = 2\n",
            "tests/test_late.py": "def test_late(): pass\n",
            ".github/workflows/late.yml": "name: late\n",
            "governance/late.txt": "late\n",
        }
        for path, content in cases.items():
            with self.subTest(path=path):
                temporary, repo, base_sha, _, _ = self.create_merge_ready_repo(
                    descendant_files={path: content}
                )
                with temporary:
                    result, output = self.run_ci(repo, base_sha)
                self.assertEqual(result, 1)
                self.assertIn("Substantive or unrelated changes follow", output)
                self.assertIn(path, output)

    def test_unrelated_task_bookkeeping_is_rejected(self) -> None:
        temporary, repo, base_sha, _, _ = self.create_merge_ready_repo(
            descendant_files={"docs/engineering/evidence/T999/review.yaml": "task: T999\n"}
        )
        with temporary:
            result, output = self.run_ci(repo, base_sha)
        self.assertEqual(result, 1)
        self.assertIn("docs/engineering/evidence/T999/review.yaml", output)

    def test_missing_authorization_sha_fails_closed(self) -> None:
        missing = "f" * 40

        def mutate(task: dict) -> None:
            task["git"]["implementation_sha"] = missing
            task["git"]["integration_candidate_sha"] = missing
            for ref in task["evidence_refs"]:
                ref["subject_sha"] = missing

        temporary, repo, base_sha, _, _ = self.create_merge_ready_repo(final_mutator=mutate)
        with temporary:
            result, output = self.run_ci(repo, base_sha)
        self.assertEqual(result, 1)
        self.assertIn("commit is unavailable", output)

    def test_non_ancestor_authorization_sha_is_rejected(self) -> None:
        temporary, repo, base_sha, _, head_sha = self.create_merge_ready_repo()
        with temporary:
            self.git(repo, "switch", "-c", "side", base_sha)
            side_task = self.recording_task(base_sha)
            self.write_task(repo, side_task)
            side_sha = self.commit(repo, "side authorization")
            self.git(repo, "switch", "main")
            task = json.loads((repo / "docs/engineering/tasks/T001.yaml").read_text(encoding="utf-8"))
            task["git"]["implementation_sha"] = side_sha
            task["git"]["integration_candidate_sha"] = side_sha
            for ref in task["evidence_refs"]:
                ref["subject_sha"] = side_sha
            self.write_task(repo, task)
            self.write_evidence(repo, task)
            head_sha = self.commit(repo, "point to side")
            result, output = self.run_ci(repo, base_sha, head_sha)
        self.assertEqual(result, 1)
        self.assertIn("not an ancestor of explicit PR head", output)

    def test_stale_declared_base_is_rejected(self) -> None:
        def mutate(task: dict) -> None:
            task["git"]["base_sha"] = task["git"]["implementation_sha"]

        temporary, repo, base_sha, _, _ = self.create_merge_ready_repo(final_mutator=mutate)
        with temporary:
            result, output = self.run_ci(repo, base_sha)
        self.assertEqual(result, 1)
        self.assertIn("does not identify explicit PR base", output)

    def test_authorization_subject_must_contain_task(self) -> None:
        temporary, repo, base_sha, _, _ = self.create_merge_ready_repo(subject_present=False)
        with temporary:
            result, output = self.run_ci(repo, base_sha)
        self.assertEqual(result, 1)
        self.assertIn("does not contain docs/engineering/tasks/T001.yaml", output)

    def test_authorization_subject_contract_version_is_frozen(self) -> None:
        temporary, repo, base_sha, _, _ = self.create_merge_ready_repo(final_version=2)
        with temporary:
            result, output = self.run_ci(repo, base_sha)
        self.assertEqual(result, 1)
        self.assertIn("uses a different contract version", output)

    def test_authorization_semantics_are_frozen(self) -> None:
        def mutate(task: dict) -> None:
            task["acceptance_criteria"] = ["Rewritten acceptance semantics."]

        temporary, repo, base_sha, _, _ = self.create_merge_ready_repo(final_mutator=mutate)
        with temporary:
            result, output = self.run_ci(repo, base_sha)
        self.assertEqual(result, 1)
        self.assertIn("changed frozen fields: acceptance_criteria", output)

    def test_recording_fields_must_be_monotonic(self) -> None:
        def subject_mutator(task: dict) -> None:
            task["git"]["implementation_sha"] = task["git"]["base_sha"]
            task["approvals"]["review"] = {
                "by": "old-reviewer",
                "at": "2026-08-30T00:00:00Z",
                "source_uri": "https://example.invalid/old",
            }

        temporary, repo, base_sha, _, _ = self.create_merge_ready_repo(
            subject_mutator=subject_mutator
        )
        with temporary:
            result, output = self.run_ci(repo, base_sha)
        self.assertEqual(result, 1)
        self.assertIn("implementation_sha changed non-monotonically", output)
        self.assertIn("review approval changed non-monotonically", output)

    def test_evidence_refs_cannot_be_rewritten(self) -> None:
        def subject_mutator(task: dict) -> None:
            task["evidence_refs"] = [
                {
                    "type": "implementation",
                    "path": "docs/engineering/evidence/T001/old.yaml",
                    "subject_sha": task["git"]["base_sha"],
                    "valid": False,
                }
            ]

        temporary, repo, base_sha, _, _ = self.create_merge_ready_repo(
            subject_mutator=subject_mutator
        )
        with temporary:
            result, output = self.run_ci(repo, base_sha)
        self.assertEqual(result, 1)
        self.assertIn("Evidence references were rewritten", output)

    def test_squash_lifecycle_inherits_pre_squash_authorization(self) -> None:
        temporary, repo, base_sha, _ = self.create_lifecycle_repo()
        with temporary:
            result, output = self.run_ci(repo, base_sha)
        self.assertEqual((result, output), (0, "PASS: validated 1 formal task contract(s)\n"))

    def test_lifecycle_candidate_and_approval_are_frozen(self) -> None:
        def mutate(task: dict) -> None:
            task["git"]["integration_candidate_sha"] = "b" * 40
            task["approvals"]["review"] = {
                "by": "replacement",
                "at": "2026-09-01T00:00:00Z",
                "source_uri": "https://example.invalid/replacement",
            }

        temporary, repo, base_sha, _ = self.create_lifecycle_repo(task_mutator=mutate)
        with temporary:
            result, output = self.run_ci(repo, base_sha)
        self.assertEqual(result, 1)
        self.assertIn("changed Task fields other than status", output)

    def test_lifecycle_existing_evidence_ref_is_frozen(self) -> None:
        def mutate(task: dict) -> None:
            task["evidence_refs"][0]["source_uri"] = "https://example.invalid/rewrite"

        temporary, repo, base_sha, _ = self.create_lifecycle_repo(task_mutator=mutate)
        with temporary:
            result, output = self.run_ci(repo, base_sha)
        self.assertEqual(result, 1)
        self.assertIn("changed Task fields other than status", output)

    def test_lifecycle_existing_manifest_is_frozen(self) -> None:
        def mutate(repo: Path) -> None:
            path = repo / "docs/engineering/evidence/T001/review.yaml"
            evidence = json.loads(path.read_text(encoding="utf-8"))
            evidence["note"] = "rewritten"
            path.write_text(json.dumps(evidence), encoding="utf-8")

        temporary, repo, base_sha, _ = self.create_lifecycle_repo(manifest_mutator=mutate)
        with temporary:
            result, output = self.run_ci(repo, base_sha)
        self.assertEqual(result, 1)
        self.assertIn("rewrote inherited Evidence manifest", output)

    def test_explicit_head_is_used_when_checkout_head_differs(self) -> None:
        temporary, repo, base_sha, _, explicit_head = self.create_merge_ready_repo()
        with temporary:
            self.git(repo, "checkout", "--detach", base_sha)
            result, output = self.run_ci(repo, base_sha, explicit_head)
        self.assertEqual((result, output), (0, "PASS: validated 1 formal task contract(s)\n"))

    def test_missing_history_fails_closed(self) -> None:
        temporary, repo, _, _, _ = self.create_merge_ready_repo()
        with temporary:
            result, output = self.run_ci(repo, "deadbeef")
        self.assertEqual(result, 2)
        self.assertIn("commit is unavailable", output)
        self.assertIn("non-shallow history", output)

    def test_repository_validation_without_base_ref_is_accepted(self) -> None:
        temporary, repo, _, _, _ = self.create_merge_ready_repo()
        with temporary:
            result, output = self.run_ci(repo, None)
        self.assertEqual((result, output), (0, "PASS: validated 1 formal task contract(s)\n"))


if __name__ == "__main__":
    unittest.main()
