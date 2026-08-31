from __future__ import annotations

import argparse
import hashlib
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from os_core import EngineeringOSError, load_yaml


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one governance-defined command and emit evidence.")
    parser.add_argument("gate_id")
    parser.add_argument("--task", required=True)
    parser.add_argument("--contract-version", required=True, type=int)
    parser.add_argument("--subject-sha", required=True)
    parser.add_argument("--provenance", choices=("worker", "reviewer", "verifier", "ci", "human"), required=True)
    parser.add_argument("--source-uri")
    parser.add_argument("--repo-root", type=Path)
    args = parser.parse_args()

    repo_root = (args.repo_root or Path(__file__).resolve().parents[2]).resolve()
    try:
        policy = load_yaml(repo_root / "governance/GATE_POLICY.yaml")
        command = policy.get("commands", {}).get(args.gate_id)
        if not isinstance(command, dict) or not isinstance(command.get("argv"), list):
            raise EngineeringOSError(f"Unknown or invalid gate command: {args.gate_id}")
        argv = [sys.executable if item == "{python}" else str(item) for item in command["argv"]]
    except EngineeringOSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    artifact_dir = repo_root / ".engineering-artifacts" / args.task
    artifact_dir.mkdir(parents=True, exist_ok=True)
    log_path = artifact_dir / f"{args.gate_id}.log"
    started_at = datetime.now(timezone.utc).isoformat()
    result = subprocess.run(
        argv,
        cwd=repo_root,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    log_text = f"$ {' '.join(argv)}\n\nSTDOUT\n{result.stdout}\nSTDERR\n{result.stderr}"
    log_path.write_text(log_text, encoding="utf-8")
    digest = hashlib.sha256(log_path.read_bytes()).hexdigest()
    evidence = {
        "task": args.task,
        "contract_version": args.contract_version,
        "subject_sha": args.subject_sha,
        "generated_at": started_at,
        "checks": [
            {
                "gate_id": args.gate_id,
                "provenance": args.provenance,
                "runner": f"{platform.system()} {platform.release()} / Python {platform.python_version()}",
                "command": argv,
                "timestamp": started_at,
                "exit_code": result.returncode,
                "artifact_digest": f"sha256:{digest}",
                "source_uri": args.source_uri,
                "unverified": [],
            }
        ],
    }
    evidence_path = artifact_dir / f"{args.gate_id}.yaml"
    evidence_path.write_text(yaml.safe_dump(evidence, sort_keys=False, allow_unicode=True), encoding="utf-8")
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    print(f"Evidence: {evidence_path}")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
